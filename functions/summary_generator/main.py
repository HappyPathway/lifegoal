"""
Summary Generator for LifeGoal Assistant

This Cloud Function generates daily and weekly summaries of user wellness data.
It analyzes check-ins, identifies patterns, and provides insights to help the user
improve their wellbeing.
"""
import os
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Core imports 
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.cloud import secretmanager
from google.cloud import storage

from core.db_manager import DatabaseManager, DatabaseLock
from core.llm_registry import LLMRegistry
from core.models import User, CheckIn, Goal, Summary


# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID", "")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "lifegoal-data")
DB_NAME = os.environ.get("DB_NAME", "lifegoal.db")

# Secret cache to avoid repeated Secret Manager calls
_secret_cache = {}


def get_secret(secret_name: str) -> str:
    """
    Get a secret from Google Secret Manager.
    
    Args:
        secret_name: Name of the secret to retrieve
        
    Returns:
        The secret value as a string
    """
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")
        
        # Cache the secret for future use
        _secret_cache[secret_name] = secret_value
        
        return secret_value
    except Exception as e:
        print(f"Error retrieving secret {secret_name}: {e}")
        # In development, fall back to environment variables
        return os.environ.get(secret_name.upper(), "")


def download_db_from_gcs() -> str:
    """
    Download the SQLite database from Google Cloud Storage.
    
    Returns:
        Local path to the downloaded database file
    """
    # Create a temporary file to store the database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, DB_NAME)
    
    try:
        # Download from GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(DB_NAME)
        blob.download_to_filename(db_path)
        print(f"Downloaded database from gs://{GCS_BUCKET_NAME}/{DB_NAME}")
    except Exception as e:
        print(f"Error downloading database: {e}")
        # If download fails, create a new database
        print("Creating new database")
        from core.models import initialize_db
        initialize_db(db_path)
    
    return db_path


def upload_db_to_gcs(db_path: str) -> bool:
    """
    Upload the SQLite database to Google Cloud Storage.
    
    Args:
        db_path: Local path to the database file
        
    Returns:
        True if upload was successful, False otherwise
    """
    try:
        # Upload to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(DB_NAME)
        blob.upload_from_filename(db_path)
        print(f"Uploaded database to gs://{GCS_BUCKET_NAME}/{DB_NAME}")
        return True
    except Exception as e:
        print(f"Error uploading database: {e}")
        return False


def get_user_data(db_manager: DatabaseManager, 
                 user_id: str, 
                 days: int = 7) -> Dict[str, Any]:
    """
    Get user data for the specified time period.
    
    Args:
        db_manager: The database manager instance
        user_id: The user's unique identifier
        days: Number of days to look back
        
    Returns:
        Dictionary containing user data
    """
    # Helper function to query the database with a session
    def _query(session):
        # Calculate the start date for filtering
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get the user
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return {"checkins": [], "goals": []}
        
        # Get check-ins
        checkins_query = session.query(CheckIn) \
            .filter(CheckIn.user_id == user_id) \
            .filter(CheckIn.timestamp >= start_date) \
            .order_by(CheckIn.timestamp.asc())
            
        checkins = []
        for checkin in checkins_query:
            checkins.append({
                "id": checkin.id,
                "timestamp": checkin.timestamp.isoformat(),
                "raw_input": checkin.raw_input,
                "structured_data": checkin.parsed_data
            })
        
        # Get goals
        goals_query = session.query(Goal).filter(Goal.user_id == user_id)
        
        goals = []
        for goal in goals_query:
            goals.append({
                "id": goal.id,
                "name": goal.name,
                "description": goal.description,
                "created_at": goal.created_at.isoformat(),
                "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None
            })
        
        return {"checkins": checkins, "goals": goals}
    
    return db_manager.with_session(_query)


def extract_patterns(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract patterns from user data.
    
    Args:
        user_data: Dictionary containing user data
        
    Returns:
        Dictionary containing patterns
    """
    checkins = user_data.get("checkins", [])
    
    # Extract moods
    moods = []
    for checkin in checkins:
        structured_data = checkin.get("structured_data", {})
        mood = structured_data.get("mood")
        if mood:
            moods.append({
                "timestamp": checkin.get("timestamp"),
                "mood": mood
            })
    
    # Extract sleep quality
    sleep_data = []
    for checkin in checkins:
        structured_data = checkin.get("structured_data", {})
        sleep_quality = structured_data.get("sleep_quality")
        if sleep_quality:
            sleep_data.append({
                "timestamp": checkin.get("timestamp"),
                "sleep_quality": sleep_quality
            })
    
    # Extract energy levels
    energy_data = []
    for checkin in checkins:
        structured_data = checkin.get("structured_data", {})
        energy_level = structured_data.get("energy_level")
        if energy_level:
            energy_data.append({
                "timestamp": checkin.get("timestamp"),
                "energy_level": energy_level
            })
    
    # Extract concerns and needs
    concerns = []
    needs = []
    for checkin in checkins:
        structured_data = checkin.get("structured_data", {})
        
        if "concerns" in structured_data:
            for concern in structured_data["concerns"]:
                concerns.append(concern)
        
        if "needs" in structured_data:
            for need in structured_data["needs"]:
                needs.append(need)
    
    return {
        "moods": moods,
        "sleep_data": sleep_data,
        "energy_data": energy_data,
        "concerns": concerns,
        "needs": needs
    }


def generate_summary(user_data: Dict[str, Any], patterns: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a summary of user wellness data.
    
    Args:
        user_data: Dictionary containing user data
        patterns: Dictionary containing patterns
        
    Returns:
        Dictionary containing the summary
    """
    # Initialize the LLM registry and select a model for summary generation
    llm_registry = LLMRegistry()
    model = llm_registry.select_model("summary")
    
    # Create a prompt for generating a summary
    prompt = f"""
    Generate a wellness summary based on the user's check-in data.
    
    User check-ins:
    {json.dumps(user_data.get('checkins', []), indent=2)}
    
    User goals:
    {json.dumps(user_data.get('goals', []), indent=2)}
    
    Observed patterns:
    {json.dumps(patterns, indent=2)}
    
    Your summary should include:
    1. An overview of the user's wellness over the past week
    2. Patterns or trends in mood, sleep quality, and energy levels
    3. Suggestions based on concerns and needs
    4. Encouragement about progress toward goals
    
    Format the response as a JSON object with these fields:
    - overview: A general overview of the user's wellbeing
    - patterns: Key patterns and trends identified
    - insights: 2-3 meaningful insights derived from the data
    - suggestions: 2-3 actionable suggestions for improvement
    - encouragement: A positive, motivational message
    
    ONLY return valid JSON, nothing else.
    """
    
    try:
        summary_text = model.generate(prompt)
        summary = json.loads(summary_text)
    except Exception as e:
        print(f"Error generating summary: {e}")
        summary = {
            "overview": "We couldn't generate a complete summary at this time.",
            "patterns": [],
            "insights": ["Check back later for insights."],
            "suggestions": ["Continue checking in regularly."],
            "encouragement": "Keep up the good work on your wellness journey!"
        }
    
    return summary


def daily_summary(event, context):
    """
    Cloud Function entry point for generating daily summaries.
    
    Args:
        event: Event payload (user_id or other parameters)
        context: Event context
        
    Returns:
        Dictionary containing the summary or status
    """
    # Extract user_id from event payload
    user_id = event.get("user_id")
    if not user_id:
        return {"error": "Missing user_id parameter"}
    
    # Download database from GCS
    db_path = download_db_from_gcs()
    
    # Initialize database manager
    db_manager = DatabaseManager(GCS_BUCKET_NAME, DB_NAME, db_path)
    
    # Use the database lock context manager
    with DatabaseLock(db_manager):
        # Get user data for the past 7 days
        user_data = get_user_data(db_manager, user_id, days=7)
        
        # Skip if there's no check-in data
        if not user_data.get("checkins"):
            return {"status": "No check-in data available"}
        
        # Extract patterns
        patterns = extract_patterns(user_data)
        
        # Generate summary
        summary = generate_summary(user_data, patterns)
        
        # Save the summary
        db_manager.save_summary(user_id, summary)
        
        # Upload handled automatically when exiting the DatabaseLock context
    
    return {"status": "Summary generated", "summary": summary}


def weekly_summary(event, context):
    """
    Cloud Function entry point for generating weekly summaries.
    
    Args:
        event: Event payload (user_id or other parameters)
        context: Event context
        
    Returns:
        Dictionary containing the summary or status
    """
    # Extract user_id from event payload
    user_id = event.get("user_id")
    if not user_id:
        return {"error": "Missing user_id parameter"}
    
    # Download database from GCS
    db_path = download_db_from_gcs()
    
    # Initialize database manager
    db_manager = DatabaseManager(GCS_BUCKET_NAME, DB_NAME, db_path)
    
    # Use the database lock context manager
    with DatabaseLock(db_manager):
        # Get user data for the past 30 days
        user_data = get_user_data(db_manager, user_id, days=30)
        
        # Skip if there's no check-in data
        if not user_data.get("checkins"):
            return {"status": "No check-in data available"}
        
        # Extract patterns
        patterns = extract_patterns(user_data)
        
        # Generate summary
        summary = generate_summary(user_data, patterns)
        
        # Save the summary
        db_manager.save_summary(user_id, summary)
        
        # Upload handled automatically when exiting the DatabaseLock context
    
    return {"status": "Weekly summary generated", "summary": summary}