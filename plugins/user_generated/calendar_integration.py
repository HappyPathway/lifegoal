"""
Google Calendar Integration Plugin for LifeGoal Assistant

This plugin provides integration with Google Calendar, allowing the assistant to
read events, suggest optimal scheduling times for wellness activities, and create
calendar events for wellness-related tasks.
"""
import os
import json
import datetime
from typing import Dict, List, Any, Optional
import tempfile

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.cloud import secretmanager

from core.base_plugin import AssistantPlugin


class CalendarIntegrationPlugin(AssistantPlugin):
    """
    Plugin for integrating with Google Calendar.
    
    This plugin connects to a user's Google Calendar to read events, find available time slots,
    and create events for wellness activities.
    """
    plugin_id: str = "calendar_integration"
    description: str = "Integrates with Google Calendar for wellness scheduling and planning"
    required_secrets: List[str] = ["google_client_secret", "google_client_id"]
    
    # If modifying these scopes, delete the file token.json.
    SCOPES = [
        'https://www.googleapis.com/auth/calendar.readonly',
        'https://www.googleapis.com/auth/calendar.events'
    ]
    
    def __init__(self):
        """Initialize the calendar integration plugin."""
        self._service = None
    
    def match_context(self, user_context: Dict[str, Any]) -> bool:
        """
        Determine if this plugin should be triggered based on the user context.
        
        Args:
            user_context: User data and context
            
        Returns:
            True if the plugin should be used
        """
        # Check if there are any calendar-related keywords in the user's message
        current_data = user_context.get("current_data", {})
        raw_input = current_data.get("raw_text", "").lower()
        
        calendar_keywords = [
            "schedule", "calendar", "appointment", "meeting", "event", 
            "plan", "organize", "free time", "availability", "busy",
            "book", "when am i free", "when am i available", "upcoming events"
        ]
        
        # Check if any calendar keywords are in the raw input
        if any(keyword in raw_input for keyword in calendar_keywords):
            return True
        
        # Check if there's a specific calendar intent
        if "calendar_lookup" in current_data.get("intentions", []):
            return True
            
        # Check if there's a need for scheduling a wellness activity
        if "schedule_activity" in current_data.get("needs", []):
            return True
            
        return False
    
    def get_secret(self, secret_name: str) -> str:
        """
        Get a secret from Google Secret Manager.
        
        Args:
            secret_name: Name of the secret to retrieve
            
        Returns:
            The secret value as a string
        """
        project_id = os.environ.get("PROJECT_ID", "")
        
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Error retrieving secret {secret_name}: {e}")
            return ""
    
    def _get_credentials(self, user_id: str) -> Optional[Credentials]:
        """
        Get the Google Calendar API credentials for a user.
        
        Args:
            user_id: Unique identifier for the user
            
        Returns:
            Credentials object or None if not available
        """
        # First, check if we have stored credentials for this user
        try:
            # Get client configuration from Secret Manager
            client_id = self.get_secret("google_client_id")
            client_secret = self.get_secret("google_client_secret")
            
            if not client_id or not client_secret:
                print("Missing Google API credentials")
                return None
                
            # In a real implementation, we'd retrieve the user's OAuth tokens from the database
            # and create credentials from them. For now, we'll assume we have the tokens.
            # This part would be connected to an OAuth flow in the Slack UI.
            
            # Example of how this could look once implemented:
            # tokens = db_manager.get_user_oauth_tokens(user_id, "google_calendar")
            # if tokens:
            #     return Credentials.from_authorized_user_info(tokens)
            
            # For development/testing purposes only
            # In production, a proper OAuth flow would be implemented
            return None
            
        except Exception as e:
            print(f"Error getting calendar credentials: {e}")
            return None
    
    def _build_service(self, credentials: Credentials) -> Optional[Any]:
        """
        Build the Google Calendar API service.
        
        Args:
            credentials: Google API credentials
            
        Returns:
            Calendar API service or None if failed
        """
        try:
            return build('calendar', 'v3', credentials=credentials)
        except Exception as e:
            print(f"Error building Calendar service: {e}")
            return None
    
    def get_upcoming_events(self, service, max_results=10) -> List[Dict[str, Any]]:
        """
        Get upcoming calendar events.
        
        Args:
            service: Google Calendar API service
            max_results: Maximum number of events to return
            
        Returns:
            List of upcoming events as dictionaries
        """
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        try:
            events_result = service.events().list(
                calendarId='primary',
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                formatted_events.append({
                    'summary': event['summary'],
                    'start': start,
                    'id': event.get('id', ''),
                    'description': event.get('description', ''),
                    'location': event.get('location', '')
                })
                
            return formatted_events
        except HttpError as error:
            print(f"Error retrieving events: {error}")
            return []
    
    def find_free_time_slots(self, service, start_date, end_date, min_duration_minutes=30) -> List[Dict[str, Any]]:
        """
        Find free time slots in a user's calendar.
        
        Args:
            service: Google Calendar API service
            start_date: Start date for the search
            end_date: End date for the search
            min_duration_minutes: Minimum duration in minutes for a slot to be considered
            
        Returns:
            List of free time slots
        """
        try:
            # Get busy times
            body = {
                "timeMin": start_date,
                "timeMax": end_date,
                "items": [{"id": "primary"}]
            }
            
            freebusy = service.freebusy().query(body=body).execute()
            busy_periods = freebusy['calendars']['primary']['busy']
            
            # Convert to datetime objects for easier manipulation
            busy_periods_dt = []
            for period in busy_periods:
                start = datetime.datetime.fromisoformat(period['start'].replace('Z', '+00:00'))
                end = datetime.datetime.fromisoformat(period['end'].replace('Z', '+00:00'))
                busy_periods_dt.append((start, end))
            
            # Find free periods
            free_periods = []
            # Sort busy periods by start time
            busy_periods_dt.sort(key=lambda x: x[0])
            
            # Convert string dates to datetime
            start_dt = datetime.datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_dt = datetime.datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            # Add the start time as the initial free period start
            if not busy_periods_dt or start_dt < busy_periods_dt[0][0]:
                free_start = start_dt
            else:
                free_start = None
                
            # Check each busy period for gaps
            for busy_start, busy_end in busy_periods_dt:
                if free_start and busy_start > free_start:
                    duration = (busy_start - free_start).total_seconds() / 60
                    if duration >= min_duration_minutes:
                        free_periods.append({
                            'start': free_start.isoformat(),
                            'end': busy_start.isoformat(),
                            'duration_minutes': duration
                        })
                free_start = busy_end
            
            # Check for free time after the last busy period
            if free_start and free_start < end_dt:
                duration = (end_dt - free_start).total_seconds() / 60
                if duration >= min_duration_minutes:
                    free_periods.append({
                        'start': free_start.isoformat(),
                        'end': end_dt.isoformat(),
                        'duration_minutes': duration
                    })
                    
            return free_periods
            
        except HttpError as error:
            print(f"Error finding free time: {error}")
            return []
    
    def create_event(self, service, summary, description, start_time, end_time, location="") -> Dict[str, Any]:
        """
        Create a new calendar event.
        
        Args:
            service: Google Calendar API service
            summary: Event title
            description: Event description
            start_time: Start time in ISO format
            end_time: End time in ISO format
            location: Event location
            
        Returns:
            The created event or error information
        """
        try:
            event = {
                'summary': summary,
                'location': location,
                'description': description,
                'start': {
                    'dateTime': start_time,
                    'timeZone': 'UTC'
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': 'UTC'
                }
            }
            
            event = service.events().insert(calendarId='primary', body=event).execute()
            return {'success': True, 'event_id': event.get('id', ''), 'html_link': event.get('htmlLink', '')}
            
        except HttpError as error:
            print(f"Error creating event: {error}")
            return {'success': False, 'error': str(error)}
    
    def execute(self, context: Dict[str, Any], llm_registry: Any) -> Dict[str, Any]:
        """
        Execute the calendar integration plugin.
        
        Args:
            context: User context and data
            llm_registry: Registry of language models
            
        Returns:
            Results of the calendar operation
        """
        user_id = context.get("user_id", "")
        current_data = context.get("current_data", {})
        raw_text = current_data.get("raw_text", "")
        
        # Get credentials and build service
        credentials = self._get_credentials(user_id)
        if not credentials:
            return {
                "message": "To access your calendar, please connect your Google account first. You can do this from the settings menu.",
                "requires_auth": True
            }
            
        service = self._build_service(credentials)
        if not service:
            return {
                "message": "There was an issue connecting to your calendar. Please try again later.",
                "error": "Service initialization failed"
            }
        
        # Use LLM to determine the user's intent regarding calendar
        model = llm_registry.select_model("structured_data")
        
        prompt = f"""
        Analyze this user message about their calendar or schedule:
        
        "{raw_text}"
        
        Identify what the user wants to do with their calendar. Extract the following information:
        
        1. Action: What action does the user want to perform? Options:
           - view_events: User wants to see upcoming events
           - find_free_time: User wants to find available time slots
           - schedule_event: User wants to create a new calendar event
           - general_question: User has a general question about their schedule
        
        2. If action is schedule_event, extract these event details:
           - title: The title for the event
           - start_time: When the event should start (extract date and time if specified)
           - duration: How long the event should last
           - description: Additional details about the event
        
        3. If action is find_free_time:
           - start_date: Beginning of period to check (today if not specified)
           - end_date: End of period to check (default 7 days from start)
           - duration_needed: Minimum length of free time slot needed
           
        4. If action is view_events:
           - time_period: What time period user wants to see (today, this week, etc.)
           - filter: Any specific types of events user is looking for
        
        Return the extracted information as a JSON object.
        """
        
        try:
            intent_data = model.extract_structured_data(prompt, {})
        except Exception as e:
            print(f"Error extracting calendar intent: {e}")
            intent_data = {"action": "view_events"}  # Default action
        
        # Handle different calendar-related actions based on intent
        action = intent_data.get("action", "view_events")
        
        if action == "view_events":
            # Get upcoming events
            events = self.get_upcoming_events(service)
            
            if not events:
                return {"message": "You don't have any upcoming events on your calendar."}
            
            # Format events for display
            events_text = "Here are your upcoming events:\n\n"
            for i, event in enumerate(events[:5], 1):
                event_time = datetime.datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                formatted_time = event_time.strftime("%A, %B %d at %I:%M %p")
                events_text += f"{i}. {event['summary']} - {formatted_time}\n"
                
            if len(events) > 5:
                events_text += f"\n...and {len(events) - 5} more events."
                
            return {"message": events_text, "events": events}
            
        elif action == "find_free_time":
            # Calculate the start and end dates for the search
            start_date = datetime.datetime.now()
            end_date = start_date + datetime.timedelta(days=7)
            
            # Override with user-specified dates if available
            if "start_date" in intent_data and intent_data["start_date"]:
                try:
                    # This is simplified - would need better date parsing in production
                    start_date = datetime.datetime.fromisoformat(intent_data["start_date"])
                except (ValueError, TypeError):
                    pass
                    
            if "end_date" in intent_data and intent_data["end_date"]:
                try:
                    end_date = datetime.datetime.fromisoformat(intent_data["end_date"])
                except (ValueError, TypeError):
                    pass
            
            # Convert to ISO format for API
            start_date_iso = start_date.isoformat() + 'Z'
            end_date_iso = end_date.isoformat() + 'Z'
            
            # Get free time slots
            min_duration = int(intent_data.get("duration_needed", 30))
            free_slots = self.find_free_time_slots(service, start_date_iso, end_date_iso, min_duration)
            
            if not free_slots:
                return {"message": "I couldn't find any free time slots in that period that meet your requirements."}
                
            # Format free slots for display
            slots_text = "Here are available time slots:\n\n"
            for i, slot in enumerate(free_slots[:5], 1):
                start_time = datetime.datetime.fromisoformat(slot['start'])
                end_time = datetime.datetime.fromisoformat(slot['end'])
                start_formatted = start_time.strftime("%A, %B %d at %I:%M %p")
                end_formatted = end_time.strftime("%I:%M %p")
                duration = slot['duration_minutes']
                slots_text += f"{i}. {start_formatted} to {end_formatted} ({duration:.0f} minutes)\n"
                
            if len(free_slots) > 5:
                slots_text += f"\n...and {len(free_slots) - 5} more available slots."
                
            return {"message": slots_text, "free_slots": free_slots}
            
        elif action == "schedule_event":
            # Get event details
            title = intent_data.get("title", "Wellness Activity")
            description = intent_data.get("description", "")
            
            # This is simplified - in production we would use a more robust
            # datetime parsing system that handles natural language time expressions
            try:
                start_time_str = intent_data.get("start_time", "")
                if start_time_str:
                    start_time = datetime.datetime.fromisoformat(start_time_str)
                else:
                    # Default to next hour
                    start_time = datetime.datetime.now().replace(minute=0, second=0) + datetime.timedelta(hours=1)
                    
                duration_minutes = int(intent_data.get("duration", "60"))
                end_time = start_time + datetime.timedelta(minutes=duration_minutes)
                
                # Format for API
                start_iso = start_time.isoformat()
                end_iso = end_time.isoformat()
                
                # Create the event
                result = self.create_event(service, title, description, start_iso, end_iso)
                
                if result.get("success"):
                    return {
                        "message": f"Great! I've scheduled '{title}' on your calendar. You can view it here: {result.get('html_link', '')}",
                        "event_created": True,
                        "event_link": result.get("html_link", "")
                    }
                else:
                    return {
                        "message": "I wasn't able to create that calendar event. Please try again later.",
                        "error": result.get("error", "Unknown error")
                    }
                    
            except Exception as e:
                print(f"Error scheduling event: {e}")
                return {
                    "message": "I had trouble understanding when to schedule this event. Could you provide a clearer date and time?",
                    "error": str(e)
                }
        
        # Default response for other actions
        return {
            "message": "I can help you with your calendar. Try asking me to show your upcoming events, find free time, or schedule a new activity."
        }