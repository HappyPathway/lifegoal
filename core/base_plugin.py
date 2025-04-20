"""
Base Plugin Interface for LifeGoal Assistant

This module defines the standard interface that all assistant plugins must implement.
Plugins provide modular functionality for the wellness assistant and are dynamically
loaded and executed based on user context.
"""
from typing import Dict, List, Any


class AssistantPlugin:
    """
    Base class for all assistant plugins.
    
    Plugins are modular extensions that provide specific functionality for the
    wellness assistant. Each plugin declares its purpose, required secrets,
    and implements methods for determining when it should be used and executing
    its logic.
    """
    plugin_id: str = "base"
    description: str = "Base plugin class"
    required_secrets: List[str] = []
    
    def match_context(self, user_context: Dict[str, Any]) -> bool:
        """
        Determine whether this plugin is applicable to the current user context.
        
        Args:
            user_context: A dictionary containing current user data, such as
                        mood, goals, recent interactions, etc.
                        
        Returns:
            True if the plugin should be triggered, False otherwise.
        """
        raise NotImplementedError("Plugin must implement match_context method")
    
    def execute(self, context: Dict[str, Any], llm_registry: Any) -> Dict[str, Any]:
        """
        Execute the plugin's main functionality using the provided context.
        
        Args:
            context: A dictionary containing user data and other relevant information
            llm_registry: A registry of available language models for AI processing
            
        Returns:
            A dictionary containing the plugin's output, such as messages,
            recommendations, or data updates.
        """
        raise NotImplementedError("Plugin must implement execute method")