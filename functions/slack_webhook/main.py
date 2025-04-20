"""
Slack Webhook Handler for LifeGoal Assistant

This Cloud Function handles incoming webhook events from Slack,
processes user interactions, and generates appropriate responses.
"""
import os
import hmac
import hashlib
import json
import time
import tempfile
from typing import Dict, Any, Optional, Tuple, List, Union

# Core imports 
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.cloud import secretmanager
from google.cloud import storage

from core.db_manager import DatabaseManager
from core.llm_registry import LLMRegistry
from core.plugin_manager import PluginManager
from core.models import User, CheckIn, Goal
from core.db_manager import DatabaseLock


# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID", "")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "lifegoal-data")
DB_NAME = os.environ.get("DB_NAME", "lifegoal.db")

# Secret cache to avoid repeated Secret Manager calls
_secret_cache = {}

# Block Kit UI Builder Functions
def create_header(text: str) -> Dict[str, Any]:
    """
    Creates a header block with the specified text.
    
    Args:
        text: The text to display in the header
        
    Returns:
        A header block
    """
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": text,
            "emoji": True
        }
    }

def create_section(text: str, accessory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Creates a section block with the specified text and optional accessory.
    
    Args:
        text: The text to display in the section
        accessory: Optional accessory to include (button, image, etc.)
        
    Returns:
        A section block
    """
    section = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": text
        }
    }
    
    if accessory:
        section["accessory"] = accessory
    
    return section

def create_divider() -> Dict[str, str]:
    """
    Creates a divider block.
    
    Returns:
        A divider block
    """
    return {"type": "divider"}

def create_context(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Creates a context block with the specified elements.
    
    Args:
        elements: List of context elements (text or images)
        
    Returns:
        A context block
    """
    return {
        "type": "context",
        "elements": elements
    }

def create_button(text: str, action_id: str, value: str, style: str = "primary") -> Dict[str, Any]:
    """
    Creates a button element.
    
    Args:
        text: The text to display on the button
        action_id: The ID to use for the button action
        value: The value to send when the button is clicked
        style: The style of the button (primary, danger, or default)
        
    Returns:
        A button element
    """
    return {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": text,
            "emoji": True
        },
        "action_id": action_id,
        "value": value,
        "style": style
    }

def create_wellness_message(response_text: str, 
                          plugin_messages: List[str] = None,
                          user_data: Dict[str, Any] = None,
                          actions_available: bool = True) -> List[Dict[str, Any]]:
    """
    Creates a rich wellness message with Slack Block Kit components.
    
    Args:
        response_text: The main response text
        plugin_messages: Optional list of plugin-generated messages
        user_data: Optional user data to display
        actions_available: Whether to include action buttons
        
    Returns:
        List of Block Kit blocks for the message
    """
    blocks = []
    
    # Add header
    blocks.append(create_header("LifeGoal Wellness Check-in"))
    
    # Add main response section
    blocks.append(create_section(response_text))
    
    # Add plugin messages if available
    if plugin_messages and len(plugin_messages) > 0:
        blocks.append(create_divider())
        blocks.append(create_section("*Personalized Insights:*"))
        
        for message in plugin_messages:
            blocks.append(create_section(message))
    
    # Add user data summary if available
    if user_data:
        blocks.append(create_divider())
        
        # Format user data into a readable summary
        mood = user_data.get("mood", "Not specified")
        energy = user_data.get("energy_level", "Not specified")
        sleep = user_data.get("sleep_quality", "Not specified")
        
        summary_text = f"*Current Status:* Mood: {mood} | Energy: {energy} | Sleep: {sleep}"
        blocks.append(create_context([{"type": "mrkdwn", "text": summary_text}]))
    
    # Add action buttons if enabled
    if actions_available:
        blocks.append(create_divider())
        
        actions = {
            "type": "actions",
            "elements": [
                create_button("Check In", "checkin_action", "checkin", "primary"),
                create_button("View Goals", "goals_action", "goals", "default"),
                create_button("Get Summary", "summary_action", "summary", "default")
            ]
        }
        
        blocks.append(actions)
    
    return blocks


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


def verify_slack_request(request) -> bool:
    """
    Verify that the request is coming from Slack.
    
    Args:
        request: The HTTP request object
        
    Returns:
        True if the request is valid, False otherwise
    """
    slack_signing_secret = get_secret("slack_signing_secret")
    
    if not slack_signing_secret:
        # For development only - skip verification if no secret is configured
        return True
    
    # Get Slack signature and timestamp
    slack_signature = request.headers.get("X-Slack-Signature", "")
    slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    
    if not slack_signature or not slack_timestamp:
        return False
    
    # Check if the timestamp is too old
    current_timestamp = int(time.time())
    if abs(current_timestamp - int(slack_timestamp)) > 60 * 5:
        # The request is older than 5 minutes
        return False
    
    # Create signature base string
    request_body = request.data.decode("utf-8")
    sig_basestring = f"v0:{slack_timestamp}:{request_body}"
    
    # Generate a signature using the signing secret
    my_signature = "v0=" + hmac.new(
        slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures
    return hmac.compare_digest(my_signature, slack_signature)


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


def extract_user_info(event_data: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Extract user ID, channel ID, and event timestamp from the event data.
    
    Args:
        event_data: The event data from Slack
        
    Returns:
        Tuple of (user_id, channel_id, event_ts)
    """
    event = event_data.get("event", {})
    user_id = event.get("user", "")
    channel_id = event.get("channel", "")
    event_ts = event.get("event_ts", "")
    
    return user_id, channel_id, event_ts


def process_message(raw_text: str) -> Dict[str, Any]:
    """
    Process a message from a user and extract structured data.
    
    Args:
        raw_text: The raw text of the message
        
    Returns:
        Dictionary containing structured data extracted from the message
    """
    # Initialize the LLM registry
    llm_registry = LLMRegistry()
    model = llm_registry.select_model("structured_data")
    
    # Define the data schema we want to extract
    schema = {
        "mood": "The user's current mood or emotional state",
        "energy_level": "High, medium, low, or unknown",
        "sleep_quality": "Good, average, poor, or unknown",
        "hunger": "Yes, no, or unknown",
        "intentions": "List of things the user plans to do",
        "concerns": "List of things the user is worried about",
        "needs": "What the user might need help with right now"
    }
    
    # Use the LLM to extract structured data
    prompt = f"""
    Extract structured wellbeing data from this user message:
    
    "{raw_text}"
    
    Extract the following fields if present: mood, energy_level, sleep_quality, hunger, intentions, concerns, needs.
    """
    
    try:
        structured_data = model.extract_structured_data(prompt, schema)
    except Exception as e:
        print(f"Error extracting structured data: {e}")
        structured_data = {
            "error": str(e),
            "raw_text": raw_text
        }
    
    return structured_data


def generate_response(user_id: str, 
                     structured_data: Dict[str, Any], 
                     db_manager: DatabaseManager) -> str:
    """
    Generate a response to the user based on structured data.
    
    Args:
        user_id: The user's Slack ID
        structured_data: Dictionary containing structured data from the message
        db_manager: The database manager instance
        
    Returns:
        Response text to send to the user
    """
    # Get recent check-ins and active persona
    recent_checkins = db_manager.get_recent_checkins(user_id)
    persona = db_manager.get_active_persona()
    
    # Initialize the LLM registry and select a model for chat
    llm_registry = LLMRegistry()
    model = llm_registry.select_model("chat")
    
    # Format recent check-in data for the prompt
    recent_data = []
    for checkin in recent_checkins:
        recent_data.append(checkin.parsed_data)
    
    # Create a prompt for generating a response
    prompt = f"""
    You are a wellness assistant named LifeGoal. Your persona: {persona.name if persona else 'Friendly Wellness Guide'}
    
    System instructions: {persona.system_prompt if persona else 'You help users maintain wellbeing through friendly check-ins and guidance.'}
    
    User behavioral summary: {persona.user_behavior_summary if persona and persona.user_behavior_summary else ''}
    
    Current user data:
    {json.dumps(structured_data, indent=2)}
    
    Recent interactions:
    {json.dumps(recent_data, indent=2)}
    
    Generate a friendly, helpful response to the user based on their current data and history.
    Keep your response concise (1-2 paragraphs) and conversational.
    """
    
    try:
        response = model.generate(prompt)
    except Exception as e:
        print(f"Error generating response: {e}")
        response = "I'm here to help with your wellbeing. How are you feeling today?"
    
    return response


def process_plugin_recommendations(user_id: str, 
                                  structured_data: Dict[str, Any], 
                                  db_manager: DatabaseManager) -> Dict[str, Any]:
    """
    Process plugins that match the current context.
    
    Args:
        user_id: The user's Slack ID
        structured_data: Dictionary containing structured data from the message
        db_manager: The database manager instance
        
    Returns:
        Dictionary containing plugin results
    """
    # Load plugins
    plugin_manager = PluginManager()
    plugins = plugin_manager.discover_plugins()
    
    # Get user data
    recent_checkins = db_manager.get_recent_checkins(user_id)
    user_goals = db_manager.get_user_goals(user_id)
    
    # Format check-ins and goals for the user context
    recent_data = []
    for checkin in recent_checkins:
        recent_data.append(checkin.parsed_data)
    
    goals_data = []
    for goal in user_goals:
        goals_data.append({
            "id": goal.id,
            "name": goal.name,
            "description": goal.description,
            "achieved": goal.is_achieved
        })
    
    # Create user context
    user_context = {
        "user_id": user_id,
        "current_data": structured_data,
        "goals": goals_data,
        "recent_checkins": recent_data
    }
    
    # Find matching plugins
    matching_plugins = plugin_manager.match_plugins_to_context(user_context)
    
    # Execute matching plugins
    plugin_results = {}
    llm_registry = LLMRegistry()
    
    for plugin in matching_plugins:
        try:
            plugin_id = plugin.plugin_id
            plugin_results[plugin_id] = plugin.execute(user_context, llm_registry)
        except Exception as e:
            print(f"Error executing plugin {plugin.plugin_id}: {e}")
            plugin_results[plugin.plugin_id] = {"error": str(e)}
    
    return plugin_results


def handle_slack_event(request) -> Dict[str, Any]:
    """
    Handle a Slack event.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Dictionary containing the response
    """
    if not verify_slack_request(request):
        return {"statusCode": 403, "body": "Invalid request signature"}
    
    # Parse the event data
    try:
        request_body = request.data.decode("utf-8")
        
        # Check if it's a URL-encoded form (interactive components)
        if request.headers.get("Content-Type") == "application/x-www-form-urlencoded":
            import urllib.parse
            payload = urllib.parse.parse_qs(request_body).get("payload", ["{}"])[0]
            event_data = json.loads(payload)
            
            # Handle interactive components (buttons, etc.)
            return handle_interactive_component(event_data)
        else:
            # Regular event API
            event_data = json.loads(request_body)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON"}
    
    # Handle URL verification challenge
    if event_data.get("type") == "url_verification":
        return {"statusCode": 200, "body": event_data.get("challenge", "")}
    
    # Initialize database manager
    db_path = download_db_from_gcs()
    db_manager = DatabaseManager(GCS_BUCKET_NAME, DB_NAME, db_path)
    
    # Use the database lock context manager
    with DatabaseLock(db_manager):
        # Extract event info
        event = event_data.get("event", {})
        event_type = event.get("type", "")
        
        # Handle message events
        if event_type == "message" and not event.get("bot_id"):
            user_id, channel_id, event_ts = extract_user_info(event_data)
            text = event.get("text", "")
            
            # Process message to extract structured data
            structured_data = process_message(text)
            
            # Store check-in
            db_manager.store_checkin(user_id, text, structured_data)
            
            # Generate response
            response = generate_response(user_id, structured_data, db_manager)
            
            # Process plugins
            plugin_results = process_plugin_recommendations(user_id, structured_data, db_manager)
            
            # Enhance response with plugin recommendations if relevant
            plugin_messages = []
            if plugin_results:
                for plugin_id, result in plugin_results.items():
                    if "message" in result:
                        plugin_messages.append(result["message"])
            
            # Create rich Slack message
            blocks = create_wellness_message(response, plugin_messages, structured_data)
            
            # Send response to Slack (in a real implementation, use Slack's API)
            # Here we're just returning the response for demonstration
            return {
                "statusCode": 200,
                "body": {
                    "response_type": "in_channel",
                    "blocks": blocks,
                    "channel": channel_id,
                }
            }
    
    # Default response for other events
    return {"statusCode": 200, "body": "Event received"}


def slack_webhook(request):
    """
    Main entry point for the Slack webhook Cloud Function.
    
    Args:
        request: The HTTP request object
        
    Returns:
        The HTTP response
    """
    # Handle OAuth routes
    if request.path.startswith('/oauth/'):
        if request.path.endswith('/callback'):
            return handle_oauth_redirect(request)
    
    # Handle regular Slack events
    try:
        response = handle_slack_event(request)
        return response
    except Exception as e:
        print(f"Error handling Slack event: {e}")
        return {"statusCode": 500, "body": "Internal server error"}