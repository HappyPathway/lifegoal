"""
SQLAlchemy Models for LifeGoal Assistant

This module defines the SQLAlchemy ORM models that represent the core data structures
of the LifeGoal wellness assistant. These models map to tables in the SQLite database
and provide a structured way to interact with application data.
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Boolean, Text,
    create_engine, JSON, inspect
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class User(Base):
    """
    Model representing a user of the wellness assistant.
    """
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    checkins = relationship("CheckIn", back_populates="user")
    goals = relationship("Goal", back_populates="user")
    
    @classmethod
    def create(cls, name: Optional[str] = None, email: Optional[str] = None) -> "User":
        """Create a new user with a generated UUID."""
        return cls(id=str(uuid.uuid4()), name=name, email=email)


class CheckIn(Base):
    """
    Model representing a user wellness check-in.
    Contains both raw input and structured parsed data.
    """
    __tablename__ = "checkins"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    raw_input = Column(Text, nullable=True)
    structured_data = Column(Text, nullable=True)  # Stored as JSON string
    
    # Relationships
    user = relationship("User", back_populates="checkins")
    
    @classmethod
    def create(cls, user_id: str, raw_input: str, structured_data: Dict[str, Any]) -> "CheckIn":
        """Create a new check-in with a generated UUID and structured data as JSON."""
        import json
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            raw_input=raw_input,
            structured_data=json.dumps(structured_data)
        )
    
    @property
    def parsed_data(self) -> Dict[str, Any]:
        """Parse and return the structured data as a dictionary."""
        import json
        if self.structured_data:
            return json.loads(self.structured_data)
        return {}


class Goal(Base):
    """
    Model representing a user's wellness goal.
    """
    __tablename__ = "goals"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    achieved_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="goals")
    
    @classmethod
    def create(cls, user_id: str, name: str, description: Optional[str] = None) -> "Goal":
        """Create a new goal with a generated UUID."""
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            description=description
        )
    
    def mark_achieved(self) -> None:
        """Mark this goal as achieved."""
        self.achieved_at = datetime.utcnow()
    
    @property
    def is_achieved(self) -> bool:
        """Check if the goal has been achieved."""
        return self.achieved_at is not None


class PersonaVersion(Base):
    """
    Model representing a version of the assistant's persona.
    """
    __tablename__ = "persona_versions"
    
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    name = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    user_behavior_summary = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)
    
    @classmethod
    def create(cls, name: str, system_prompt: str, 
             user_behavior_summary: Optional[str] = None, 
             is_active: bool = False) -> "PersonaVersion":
        """Create a new persona version with a generated UUID."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            system_prompt=system_prompt,
            user_behavior_summary=user_behavior_summary,
            is_active=is_active
        )
    
    def activate(self) -> None:
        """Set this persona version as active."""
        self.is_active = True


class PluginRegistry(Base):
    """
    Model representing a plugin registered in the system.
    """
    __tablename__ = "plugin_registry"
    
    plugin_id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    @classmethod
    def create(cls, plugin_id: str, version: str, description: Optional[str] = None) -> "PluginRegistry":
        """Create a new plugin registry entry."""
        return cls(
            plugin_id=plugin_id,
            version=version,
            description=description
        )
    
    def update_version(self, new_version: str) -> None:
        """Update the plugin version."""
        self.version = new_version
        self.last_updated = datetime.utcnow()


class Secret(Base):
    """
    Model representing a secret required by plugins.
    Note: Actual secrets are stored in Google Secret Manager.
    This just tracks which secrets are needed and their status.
    """
    __tablename__ = "secrets"
    
    name = Column(String, primary_key=True)
    status = Column(String, nullable=False)  # 'missing' or 'present'
    used_by = Column(Text, nullable=True)  # Comma-separated plugin names
    created_at = Column(DateTime, default=datetime.utcnow)
    
    @classmethod
    def create(cls, name: str, used_by: Optional[List[str]] = None) -> "Secret":
        """Create a new secret entry with 'missing' status."""
        used_by_str = ",".join(used_by) if used_by else ""
        return cls(
            name=name,
            status="missing",
            used_by=used_by_str
        )
    
    def mark_present(self) -> None:
        """Mark this secret as present in Secret Manager."""
        self.status = "present"
    
    def add_plugin(self, plugin_id: str) -> None:
        """Add a plugin that uses this secret."""
        plugin_ids = self.plugin_ids
        if plugin_id not in plugin_ids:
            plugin_ids.append(plugin_id)
            self.used_by = ",".join(plugin_ids)
    
    @property
    def plugin_ids(self) -> List[str]:
        """Get list of plugin IDs using this secret."""
        if not self.used_by:
            return []
        return self.used_by.split(",")


class Summary(Base):
    """
    Model representing a generated wellness summary.
    """
    __tablename__ = "summaries"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    summary_data = Column(Text, nullable=True)  # Stored as JSON string
    
    # Relationships
    user = relationship("User")
    
    @classmethod
    def create(cls, user_id: str, summary_data: Dict[str, Any]) -> "Summary":
        """Create a new summary with a generated UUID and summary data as JSON."""
        import json
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            summary_data=json.dumps(summary_data)
        )
    
    @property
    def parsed_data(self) -> Dict[str, Any]:
        """Parse and return the summary data as a dictionary."""
        import json
        if self.summary_data:
            return json.loads(self.summary_data)
        return {}


class OAuthToken(Base):
    """
    Model representing OAuth tokens for external service integrations.
    Note: This stores encrypted token data, with the encryption key in Secret Manager.
    """
    __tablename__ = "oauth_tokens"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # e.g., 'google', 'microsoft'
    token_data = Column(Text, nullable=False)  # Encrypted token JSON
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    
    @classmethod
    def create(cls, user_id: str, provider: str, token_data: Dict[str, Any], 
              expires_at: Optional[datetime] = None) -> "OAuthToken":
        """
        Create a new OAuth token entry with encrypted token data.
        
        Args:
            user_id: ID of the user the token belongs to
            provider: Name of the service provider (google, microsoft, etc.)
            token_data: Dictionary containing token information
            expires_at: Optional expiration datetime
            
        Returns:
            New OAuthToken instance
        """
        import json
        from cryptography.fernet import Fernet
        
        # In production, this key would be retrieved from Secret Manager
        # Here we're using a placeholder approach for development
        def get_encryption_key():
            import os
            from google.cloud import secretmanager
            
            project_id = os.environ.get("PROJECT_ID", "")
            
            try:
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/oauth_encryption_key/versions/latest"
                response = client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                print(f"Error retrieving encryption key: {e}")
                # Development fallback - NEVER use in production
                return "kZxL8QOzrb2wrlISPVVjZ5tcl7IkB5uF2Y4lxTaradE="
        
        # Encrypt token data
        key = get_encryption_key()
        f = Fernet(key.encode())
        encrypted_data = f.encrypt(json.dumps(token_data).encode())
        
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            provider=provider,
            token_data=encrypted_data.decode(),
            expires_at=expires_at
        )
    
    @property
    def tokens(self) -> Dict[str, Any]:
        """
        Decrypt and return the token data.
        
        Returns:
            Dictionary with token information
        """
        import json
        from cryptography.fernet import Fernet
        
        # In production, this key would be retrieved from Secret Manager
        # Here we're using a placeholder approach for development
        def get_encryption_key():
            import os
            from google.cloud import secretmanager
            
            project_id = os.environ.get("PROJECT_ID", "")
            
            try:
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/oauth_encryption_key/versions/latest"
                response = client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                print(f"Error retrieving encryption key: {e}")
                # Development fallback - NEVER use in production
                return "kZxL8QOzrb2wrlISPVVjZ5tcl7IkB5uF2Y4lxTaradE="
        
        # Decrypt token data
        key = get_encryption_key()
        f = Fernet(key.encode())
        decrypted_data = f.decrypt(self.token_data.encode())
        
        return json.loads(decrypted_data)
    
    def update_tokens(self, new_token_data: Dict[str, Any], 
                     expires_at: Optional[datetime] = None) -> None:
        """
        Update the stored token data with new values.
        
        Args:
            new_token_data: New token dictionary to store
            expires_at: Optional new expiration time
        """
        import json
        from cryptography.fernet import Fernet
        
        # Get encryption key (same as in create method)
        def get_encryption_key():
            import os
            from google.cloud import secretmanager
            
            project_id = os.environ.get("PROJECT_ID", "")
            
            try:
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/oauth_encryption_key/versions/latest"
                response = client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                print(f"Error retrieving encryption key: {e}")
                # Development fallback - NEVER use in production
                return "kZxL8QOzrb2wrlISPVVjZ5tcl7IkB5uF2Y4lxTaradE="
        
        # Encrypt new token data
        key = get_encryption_key()
        f = Fernet(key.encode())
        encrypted_data = f.encrypt(json.dumps(new_token_data).encode())
        
        # Update instance
        self.token_data = encrypted_data.decode()
        if expires_at:
            self.expires_at = expires_at
        self.last_updated = datetime.utcnow()
    
    @property
    def is_expired(self) -> bool:
        """
        Check if the token has expired.
        
        Returns:
            True if token has expired, False otherwise
        """
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at


def init_db_engine(db_path: str):
    """
    Initialize the SQLAlchemy engine with the given database path.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        SQLAlchemy engine instance
    """
    return create_engine(f"sqlite:///{db_path}")


def create_session(engine):
    """
    Create a new SQLAlchemy session.
    
    Args:
        engine: SQLAlchemy engine instance
        
    Returns:
        SQLAlchemy session maker
    """
    Session = sessionmaker(bind=engine)
    return Session()


def create_tables(engine):
    """
    Create all tables defined by the models if they don't exist.
    
    Args:
        engine: SQLAlchemy engine instance
    """
    Base.metadata.create_all(engine)


def initialize_db(db_path: str):
    """
    Initialize the database with the SQLAlchemy models.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        SQLAlchemy engine instance
    """
    engine = init_db_engine(db_path)
    create_tables(engine)
    
    # Create initial persona if needed
    session = create_session(engine)
    if not session.query(PersonaVersion).filter_by(is_active=True).first():
        initial_persona = PersonaVersion.create(
            name="Friendly Wellness Guide",
            system_prompt="You are a friendly wellness assistant who helps users maintain their wellbeing through thoughtful check-ins and guidance.",
            is_active=True
        )
        session.add(initial_persona)
        session.commit()
    session.close()
    
    return engine