"""
Database Manager for LifeGoal Assistant

This module manages SQLite database operations using SQLAlchemy ORM, including
downloading from and uploading to Google Cloud Storage. It ensures atomic state
operations and proper versioning of the database.
"""
import os
import tempfile
import json
import time
import uuid
import socket
from typing import Optional, Any, Dict, List, TypeVar, Type
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from google.cloud import storage
from google.cloud.exceptions import NotFound

from core.models import (
    Base, User, CheckIn, Goal, PersonaVersion, 
    PluginRegistry, Secret, Summary, OAuthToken, initialize_db
)

T = TypeVar('T')

# Maximum lock lifespan in seconds to prevent deadlocks
MAX_LOCK_AGE = 300  # 5 minutes

# Lock retry configuration
LOCK_RETRY_ATTEMPTS = 5
LOCK_RETRY_DELAY = 2  # seconds


class DatabaseLockException(Exception):
    """Exception raised when unable to acquire a database lock."""
    pass


class DatabaseLock:
    """
    Context manager for database locking.
    
    This class provides a convenient way to acquire and release
    database locks using Python's context manager protocol.
    
    Example:
    ```python
    db_manager = DatabaseManager(bucket_name)
    
    # Using the context manager
    with DatabaseLock(db_manager):
        # The lock is automatically acquired here
        db_path = db_manager.download_db()
        # Do operations with the database
        db_manager.upload_db()
        # The lock is automatically released when exiting the with block
    ```
    """
    
    def __init__(self, db_manager: 'DatabaseManager', timeout: int = 60):
        """
        Initialize the context manager.
        
        Args:
            db_manager: The DatabaseManager instance
            timeout: Maximum time in seconds to wait for the lock
        """
        self.db_manager = db_manager
        self.timeout = timeout
    
    def __enter__(self) -> 'DatabaseManager':
        """
        Acquire the database lock when entering the context.
        
        Returns:
            The DatabaseManager instance
        
        Raises:
            DatabaseLockException: If unable to acquire the lock
        """
        self.db_manager.acquire_lock(self.timeout)
        return self.db_manager
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Release the database lock when exiting the context.
        
        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised
        """
        self.db_manager.release_lock()


class DatabaseManager:
    """
    Manages SQLite database operations using SQLAlchemy ORM, including GCS sync.
    """
    
    def __init__(self, 
                bucket_name: str, 
                db_filename: str = "lifegoal.db", 
                local_path: Optional[str] = None,
                lock_timeout: int = MAX_LOCK_AGE):
        """
        Initialize the database manager.
        
        Args:
            bucket_name: Name of the GCS bucket for storing the database
            db_filename: Name of the SQLite database file
            local_path: Optional local path for the database file
            lock_timeout: Maximum time in seconds to hold a lock
        """
        self.bucket_name = bucket_name
        self.db_filename = db_filename
        self.local_path = local_path or os.path.join(tempfile.gettempdir(), db_filename)
        self.engine = None
        self.Session = None
        self.lock_timeout = lock_timeout
        self.lock_id = None
        
        # Initialize GCS client
        try:
            self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(bucket_name)
        except Exception as e:
            print(f"Warning: Failed to initialize GCS client: {e}")
            print("Operating in local-only mode")
            self.storage_client = None
            self.bucket = None
    
    def _generate_lock_id(self) -> str:
        """
        Generate a unique lock ID that identifies this process.
        
        Returns:
            A unique lock identifier
        """
        # Create a unique ID combining hostname, process ID, and a random UUID
        hostname = socket.gethostname()
        pid = os.getpid()
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        
        return f"{hostname}-{pid}-{unique_id}-{timestamp}"
    
    def _get_lock_blob_name(self) -> str:
        """
        Get the name of the lock file in GCS.
        
        Returns:
            The lock file name
        """
        return f"{self.db_filename}.lock"
    
    def _lock_exists(self) -> bool:
        """
        Check if a lock file exists in GCS.
        
        Returns:
            True if a lock exists, False otherwise
        """
        if not self.bucket:
            return False
            
        try:
            lock_blob = self.bucket.blob(self._get_lock_blob_name())
            return lock_blob.exists()
        except Exception as e:
            print(f"Error checking for lock: {e}")
            return False
    
    def _get_lock_info(self) -> Dict[str, Any]:
        """
        Get information about the current lock.
        
        Returns:
            Dictionary with lock information or empty dict if no lock
        """
        if not self.bucket:
            return {}
            
        try:
            lock_blob = self.bucket.blob(self._get_lock_blob_name())
            if not lock_blob.exists():
                return {}
                
            # Download lock info
            lock_data = lock_blob.download_as_text()
            lock_info = json.loads(lock_data)
            return lock_info
        except Exception as e:
            print(f"Error getting lock info: {e}")
            return {}
    
    def _is_lock_expired(self, lock_info: Dict[str, Any]) -> bool:
        """
        Check if the lock has expired based on its timestamp.
        
        Args:
            lock_info: Dictionary with lock information
            
        Returns:
            True if the lock has expired, False otherwise
        """
        if not lock_info or "timestamp" not in lock_info:
            return True
            
        try:
            lock_time = datetime.fromisoformat(lock_info["timestamp"])
            current_time = datetime.utcnow()
            
            # Calculate the age of the lock
            lock_age = (current_time - lock_time).total_seconds()
            
            # If the lock is older than the timeout, it's expired
            return lock_age > self.lock_timeout
        except Exception as e:
            print(f"Error checking lock expiration: {e}")
            return True  # Assume expired if we can't parse the timestamp
    
    def _create_lock(self) -> bool:
        """
        Create a lock file in GCS.
        
        Returns:
            True if the lock was created successfully, False otherwise
        """
        if not self.bucket:
            return True  # In local-only mode, pretend we got the lock
            
        try:
            # Generate a unique lock ID for this process
            self.lock_id = self._generate_lock_id()
            
            # Create lock info
            lock_info = {
                "lock_id": self.lock_id,
                "timestamp": datetime.utcnow().isoformat(),
                "hostname": socket.gethostname(),
                "pid": os.getpid()
            }
            
            # Upload lock file to GCS
            lock_blob = self.bucket.blob(self._get_lock_blob_name())
            lock_blob.upload_from_string(json.dumps(lock_info))
            
            print(f"Created database lock: {self.lock_id}")
            return True
        except Exception as e:
            print(f"Error creating lock: {e}")
            self.lock_id = None
            return False
    
    def _release_lock(self) -> bool:
        """
        Release the database lock by deleting the lock file.
        
        Returns:
            True if the lock was released successfully, False otherwise
        """
        if not self.bucket or not self.lock_id:
            self.lock_id = None
            return True
            
        try:
            # Check if we own the lock
            lock_info = self._get_lock_info()
            if lock_info.get("lock_id") != self.lock_id:
                print("Warning: Not releasing lock as it's owned by another process")
                self.lock_id = None
                return False
                
            # Delete the lock file
            lock_blob = self.bucket.blob(self._get_lock_blob_name())
            lock_blob.delete()
            
            print(f"Released database lock: {self.lock_id}")
            self.lock_id = None
            return True
        except NotFound:
            # Lock already gone
            self.lock_id = None
            return True
        except Exception as e:
            print(f"Error releasing lock: {e}")
            self.lock_id = None
            return False
    
    def _force_release_lock(self) -> bool:
        """
        Force release any existing lock, regardless of ownership.
        Only use in special cases like cleanup scripts.
        
        Returns:
            True if the lock was released, False otherwise
        """
        if not self.bucket:
            return True
            
        try:
            lock_blob = self.bucket.blob(self._get_lock_blob_name())
            if lock_blob.exists():
                lock_blob.delete()
                print("Force-released database lock")
            return True
        except Exception as e:
            print(f"Error force-releasing lock: {e}")
            return False
    
    def acquire_lock(self, timeout: int = 60) -> bool:
        """
        Acquire a lock on the database with timeout.
        
        Args:
            timeout: Maximum time in seconds to wait for the lock
            
        Returns:
            True if the lock was acquired, False otherwise
            
        Raises:
            DatabaseLockException: If unable to acquire the lock
        """
        if not self.bucket:
            return True  # Local-only mode, no locking needed
            
        start_time = time.time()
        attempt = 0
        
        while True:
            # Check if we've exceeded the timeout
            if time.time() - start_time > timeout:
                raise DatabaseLockException(f"Failed to acquire database lock after {timeout} seconds")
            
            # Check if a lock exists
            if not self._lock_exists():
                # No lock exists, try to create one
                if self._create_lock():
                    return True
            else:
                # Lock exists, check if it's expired
                lock_info = self._get_lock_info()
                if self._is_lock_expired(lock_info):
                    print("Found expired lock, replacing it")
                    # Force-release the expired lock
                    self._force_release_lock()
                    # Try to create a new lock
                    if self._create_lock():
                        return True
            
            # Lock exists and is valid, wait and retry
            attempt += 1
            if attempt > LOCK_RETRY_ATTEMPTS:
                owner = self._get_lock_info().get("lock_id", "unknown")
                raise DatabaseLockException(
                    f"Failed to acquire database lock after {attempt} attempts. "
                    f"Currently held by: {owner}"
                )
            
            # Wait before the next attempt
            print(f"Database locked, waiting {LOCK_RETRY_DELAY} seconds (attempt {attempt}/{LOCK_RETRY_ATTEMPTS})")
            time.sleep(LOCK_RETRY_DELAY)
    
    def release_lock(self) -> None:
        """Release the database lock if we hold it."""
        if self.lock_id:
            self._release_lock()
    
    def download_db(self) -> str:
        """
        Download the SQLite database from GCS.
        
        Returns:
            Path to the local SQLite database file
        """
        if self.bucket:
            try:
                blob = self.bucket.blob(self.db_filename)
                if blob.exists():
                    blob.download_to_filename(self.local_path)
                    print(f"Downloaded database from GCS to {self.local_path}")
                else:
                    print(f"No existing database found in GCS bucket. Creating a new one.")
                    self.initialize_db()
            except Exception as e:
                print(f"Error downloading database from GCS: {e}")
                if not os.path.exists(self.local_path):
                    self.initialize_db()
        elif not os.path.exists(self.local_path):
            self.initialize_db()
        
        return self.local_path
    
    def upload_db(self) -> None:
        """
        Upload the SQLite database to GCS with versioning.
        """
        if not self.bucket:
            print("No GCS bucket configured. Skipping upload.")
            return
        
        try:
            # Upload as latest version
            blob = self.bucket.blob(self.db_filename)
            blob.upload_from_filename(self.local_path)
            
            # Also create a timestamped version for backup
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            backup_blob = self.bucket.blob(f"backups/{self.db_filename}.{timestamp}")
            backup_blob.upload_from_filename(self.local_path)
            
            print(f"Uploaded database to GCS: {self.bucket_name}/{self.db_filename}")
            print(f"Created backup: {self.bucket_name}/backups/{self.db_filename}.{timestamp}")
            
        except Exception as e:
            print(f"Error uploading database to GCS: {e}")
    
    def initialize_db(self) -> None:
        """
        Initialize a new SQLite database with the required schema.
        """
        self.engine = initialize_db(self.local_path)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
    
    def get_session(self) -> Session:
        """
        Get a SQLAlchemy session for database operations.
        
        Returns:
            SQLAlchemy session
        """
        if not self.engine:
            self.download_db()
            self.engine = create_engine(f"sqlite:///{self.local_path}")
            self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        return self.Session()
    
    def with_session(self, func, *args, **kwargs):
        """
        Execute a function with a database session, handling download/upload.
        
        This is a context manager that ensures the database is downloaded before
        the operation and uploaded after the operation, with proper locking.
        
        Args:
            func: Function to execute with the session
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function execution
            
        Raises:
            DatabaseLockException: If unable to acquire the database lock
        """
        # Acquire the database lock
        self.acquire_lock()
        
        try:
            # Download the database and create a session
            self.download_db()
            session = self.get_session()
            
            try:
                # Execute the function with the session
                result = func(session, *args, **kwargs)
                # Commit changes
                session.commit()
                # Upload the updated database
                self.upload_db()
                return result
            except Exception as e:
                # Rollback changes on error
                session.rollback()
                print(f"Error in database operation: {e}")
                raise
            finally:
                # Close the session
                session.close()
        finally:
            # Always release the lock
            self.release_lock()
    
    # User operations
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get a user by ID.
        
        Args:
            user_id: The user's unique identifier
            
        Returns:
            User object or None if not found
        """
        def _query(session):
            return session.query(User).filter(User.id == user_id).first()
        
        return self.with_session(_query)
    
    def create_user(self, name: Optional[str] = None, email: Optional[str] = None) -> User:
        """
        Create a new user.
        
        Args:
            name: Optional user name
            email: Optional user email
            
        Returns:
            The created user
        """
        def _create(session):
            user = User.create(name=name, email=email)
            session.add(user)
            return user
        
        return self.with_session(_create)
    
    # CheckIn operations
    def store_checkin(self, user_id: str, raw_input: str, structured_data: Dict[str, Any]) -> CheckIn:
        """
        Store a user check-in with raw input and structured data.
        
        Args:
            user_id: The user's unique identifier
            raw_input: The raw text input from the user
            structured_data: Dictionary containing structured data extracted from input
            
        Returns:
            The created check-in
        """
        def _store(session):
            # Ensure user exists
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id)
                session.add(user)
            
            checkin = CheckIn.create(user_id=user_id, raw_input=raw_input, structured_data=structured_data)
            session.add(checkin)
            return checkin
        
        return self.with_session(_store)
    
    def get_recent_checkins(self, user_id: str, limit: int = 5) -> List[CheckIn]:
        """
        Get recent check-ins for a user.
        
        Args:
            user_id: The user's unique identifier
            limit: Maximum number of check-ins to return
            
        Returns:
            List of CheckIn objects
        """
        def _query(session):
            return session.query(CheckIn) \
                .filter(CheckIn.user_id == user_id) \
                .order_by(CheckIn.timestamp.desc()) \
                .limit(limit) \
                .all()
        
        return self.with_session(_query)
    
    # Goal operations
    def create_goal(self, user_id: str, name: str, description: Optional[str] = None) -> Goal:
        """
        Create a new goal for a user.
        
        Args:
            user_id: The user's unique identifier
            name: Name of the goal
            description: Optional description of the goal
            
        Returns:
            The created goal
        """
        def _create(session):
            # Ensure user exists
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id)
                session.add(user)
            
            goal = Goal.create(user_id=user_id, name=name, description=description)
            session.add(goal)
            return goal
        
        return self.with_session(_create)
    
    def get_user_goals(self, user_id: str) -> List[Goal]:
        """
        Get all goals for a user.
        
        Args:
            user_id: The user's unique identifier
            
        Returns:
            List of Goal objects
        """
        def _query(session):
            return session.query(Goal) \
                .filter(Goal.user_id == user_id) \
                .order_by(Goal.created_at.desc()) \
                .all()
        
        return self.with_session(_query)
    
    def mark_goal_achieved(self, goal_id: str) -> Optional[Goal]:
        """
        Mark a goal as achieved.
        
        Args:
            goal_id: The goal's unique identifier
            
        Returns:
            The updated goal, or None if not found
        """
        def _update(session):
            goal = session.query(Goal).filter(Goal.id == goal_id).first()
            if goal:
                goal.mark_achieved()
            return goal
        
        return self.with_session(_update)
    
    # Persona operations
    def get_active_persona(self) -> Optional[PersonaVersion]:
        """
        Get the currently active persona configuration.
        
        Returns:
            Active PersonaVersion object, or None if not found
        """
        def _query(session):
            return session.query(PersonaVersion) \
                .filter(PersonaVersion.is_active == True) \
                .order_by(PersonaVersion.timestamp.desc()) \
                .first()
        
        return self.with_session(_query)
    
    def create_persona_version(self, 
                             name: str, 
                             system_prompt: str, 
                             user_behavior_summary: Optional[str] = None, 
                             is_active: bool = False) -> PersonaVersion:
        """
        Create a new persona version.
        
        Args:
            name: Name of the persona
            system_prompt: System prompt text
            user_behavior_summary: Optional summary of user behavior
            is_active: Whether this persona should be active
            
        Returns:
            The created persona version
        """
        def _create(session):
            if is_active:
                # Deactivate all existing personas
                existing_personas = session.query(PersonaVersion).filter(PersonaVersion.is_active == True).all()
                for persona in existing_personas:
                    persona.is_active = False
            
            persona = PersonaVersion.create(
                name=name, 
                system_prompt=system_prompt,
                user_behavior_summary=user_behavior_summary,
                is_active=is_active
            )
            session.add(persona)
            return persona
        
        return self.with_session(_create)
    
    # Plugin registry operations
    def register_plugin(self, plugin_id: str, version: str, description: Optional[str] = None) -> PluginRegistry:
        """
        Register a new plugin or update an existing one.
        
        Args:
            plugin_id: The plugin's identifier
            version: Version string (e.g. "v1.py")
            description: Optional description of the plugin
            
        Returns:
            The created or updated plugin registry entry
        """
        def _register(session):
            plugin = session.query(PluginRegistry).filter(PluginRegistry.plugin_id == plugin_id).first()
            if plugin:
                plugin.version = version
                plugin.last_updated = datetime.utcnow()
                if description:
                    plugin.description = description
            else:
                plugin = PluginRegistry.create(
                    plugin_id=plugin_id,
                    version=version,
                    description=description
                )
                session.add(plugin)
            return plugin
        
        return self.with_session(_register)
    
    def get_plugin_registry(self) -> Dict[str, PluginRegistry]:
        """
        Get the entire plugin registry.
        
        Returns:
            Dictionary mapping plugin IDs to PluginRegistry objects
        """
        def _query(session):
            plugins = session.query(PluginRegistry).all()
            return {plugin.plugin_id: plugin for plugin in plugins}
        
        return self.with_session(_query)
    
    # Secret operations
    def track_secret(self, name: str, used_by: Optional[List[str]] = None) -> Secret:
        """
        Track a secret required by plugins.
        
        Args:
            name: Name of the secret
            used_by: List of plugin IDs that use this secret
            
        Returns:
            The created or updated secret
        """
        def _track(session):
            secret = session.query(Secret).filter(Secret.name == name).first()
            if secret:
                if used_by:
                    for plugin_id in used_by:
                        secret.add_plugin(plugin_id)
            else:
                secret = Secret.create(name=name, used_by=used_by)
                session.add(secret)
            return secret
        
        return self.with_session(_track)
    
    def mark_secret_present(self, name: str) -> Optional[Secret]:
        """
        Mark a secret as present in Google Secret Manager.
        
        Args:
            name: Name of the secret
            
        Returns:
            The updated secret, or None if not found
        """
        def _update(session):
            secret = session.query(Secret).filter(Secret.name == name).first()
            if secret:
                secret.mark_present()
            return secret
        
        return self.with_session(_update)
    
    def get_missing_secrets(self) -> List[Secret]:
        """
        Get all secrets with 'missing' status.
        
        Returns:
            List of Secret objects
        """
        def _query(session):
            return session.query(Secret).filter(Secret.status == 'missing').all()
        
        return self.with_session(_query)
    
    # Summary operations
    def save_summary(self, user_id: str, summary_data: Dict[str, Any]) -> Summary:
        """
        Save a summary to the database.
        
        Args:
            user_id: The user's unique identifier
            summary_data: Dictionary containing the summary
            
        Returns:
            The created summary
        """
        def _save(session):
            # Ensure user exists
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id)
                session.add(user)
            
            summary = Summary.create(user_id=user_id, summary_data=summary_data)
            session.add(summary)
            return summary
        
        return self.with_session(_save)
    
    def get_recent_summaries(self, user_id: str, limit: int = 5) -> List[Summary]:
        """
        Get recent summaries for a user.
        
        Args:
            user_id: The user's unique identifier
            limit: Maximum number of summaries to return
            
        Returns:
            List of Summary objects
        """
        def _query(session):
            return session.query(Summary) \
                .filter(Summary.user_id == user_id) \
                .order_by(Summary.timestamp.desc()) \
                .limit(limit) \
                .all()
        
        return self.with_session(_query)
    
    # OAuth token operations
    def store_oauth_token(self, 
                        user_id: str, 
                        provider: str, 
                        token_data: Dict[str, Any], 
                        expires_at: Optional[datetime] = None) -> OAuthToken:
        """
        Store OAuth tokens for a user.
        
        Args:
            user_id: The user's unique identifier
            provider: Service provider name (e.g., 'google', 'microsoft')
            token_data: Dictionary containing token information
            expires_at: Optional expiration datetime
            
        Returns:
            The created or updated OAuth token
        """
        def _store(session):
            # Check if a token already exists
            token = session.query(OAuthToken) \
                .filter(OAuthToken.user_id == user_id) \
                .filter(OAuthToken.provider == provider) \
                .first()
                
            # Ensure user exists
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id)
                session.add(user)
            
            if token:
                # Update existing token
                token.update_tokens(token_data, expires_at)
            else:
                # Create new token
                token = OAuthToken.create(
                    user_id=user_id,
                    provider=provider,
                    token_data=token_data,
                    expires_at=expires_at
                )
                session.add(token)
                
            return token
        
        return self.with_session(_store)
    
    def get_oauth_token(self, user_id: str, provider: str) -> Optional[OAuthToken]:
        """
        Get OAuth tokens for a user and provider.
        
        Args:
            user_id: The user's unique identifier
            provider: Service provider name (e.g., 'google', 'microsoft')
            
        Returns:
            OAuthToken object or None if not found
        """
        def _query(session):
            return session.query(OAuthToken) \
                .filter(OAuthToken.user_id == user_id) \
                .filter(OAuthToken.provider == provider) \
                .first()
        
        return self.with_session(_query)
    
    def get_user_oauth_tokens(self, user_id: str) -> Dict[str, OAuthToken]:
        """
        Get all OAuth tokens for a user.
        
        Args:
            user_id: The user's unique identifier
            
        Returns:
            Dictionary mapping provider names to OAuthToken objects
        """
        def _query(session):
            tokens = session.query(OAuthToken) \
                .filter(OAuthToken.user_id == user_id) \
                .all()
            return {token.provider: token for token in tokens}
        
        return self.with_session(_query)
    
    def delete_oauth_token(self, user_id: str, provider: str) -> bool:
        """
        Delete OAuth tokens for a user and provider.
        
        Args:
            user_id: The user's unique identifier
            provider: Service provider name (e.g., 'google', 'microsoft')
            
        Returns:
            True if a token was deleted, False otherwise
        """
        def _delete(session):
            token = session.query(OAuthToken) \
                .filter(OAuthToken.user_id == user_id) \
                .filter(OAuthToken.provider == provider) \
                .first()
                
            if token:
                session.delete(token)
                return True
            return False
        
        return self.with_session(_delete)