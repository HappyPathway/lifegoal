"""
Plugin Manager for LifeGoal Assistant

This module handles loading and managing plugins for the assistant.
It provides functionality to discover plugins, load them dynamically,
and track their usage and dependencies.
"""
import os
import importlib.util
import json
import inspect
from typing import List, Dict, Any, Optional
import logging

from core.base_plugin import AssistantPlugin

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manages discovery, loading, and execution of assistant plugins.
    """
    
    def __init__(self, plugins_dir: str = "plugins/user_generated"):
        """
        Initialize the plugin manager.
        
        Args:
            plugins_dir: Directory containing plugin modules
        """
        self.plugins_dir = plugins_dir
        self.plugins = {}
        self.registry_path = os.path.join("plugins", "registry.json")
    
    def discover_plugins(self) -> Dict[str, AssistantPlugin]:
        """
        Scan the plugins directory and load all available plugins.
        
        Returns:
            Dictionary mapping plugin IDs to plugin instances
        """
        plugins = {}
        registry = self._load_registry()
        
        # First, check the registry for active plugins
        for plugin_id, metadata in registry.items():
            if metadata.get("is_active", True):
                plugin_instance = self._load_plugin_from_registry(plugin_id, metadata)
                if plugin_instance:
                    plugins[plugin_id] = plugin_instance
        
        # Scan directories for any plugins not in registry
        for plugin_dir in self._get_plugin_directories():
            plugin_id = os.path.basename(plugin_dir)
            if plugin_id not in plugins:
                latest_version = self._get_latest_version(plugin_dir)
                if latest_version:
                    plugin_instance = self._load_plugin_from_path(
                        os.path.join(plugin_dir, latest_version)
                    )
                    if plugin_instance:
                        plugins[plugin_id] = plugin_instance
        
        self.plugins = plugins
        return plugins
    
    def _get_plugin_directories(self) -> List[str]:
        """
        Get all plugin directories within the plugins directory.
        
        Returns:
            List of directory paths
        """
        if not os.path.exists(self.plugins_dir):
            return []
            
        plugin_dirs = []
        for item in os.listdir(self.plugins_dir):
            item_path = os.path.join(self.plugins_dir, item)
            if os.path.isdir(item_path) and not item.startswith("__"):
                plugin_dirs.append(item_path)
        return plugin_dirs
    
    def _get_latest_version(self, plugin_dir: str) -> Optional[str]:
        """
        Get the latest version file from a plugin directory.
        
        Args:
            plugin_dir: Path to the plugin directory
            
        Returns:
            Filename of the latest version, or None if no versions are found
        """
        versions = []
        for item in os.listdir(plugin_dir):
            if item.endswith(".py") and item.startswith("v") and not item.startswith("__"):
                versions.append(item)
        
        if not versions:
            return None
            
        # Sort versions (assuming naming convention like v1.py, v2.py, etc.)
        versions.sort(key=lambda v: int(v[1:-3]))
        return versions[-1]
    
    def _load_plugin_from_registry(self, plugin_id: str, metadata: Dict[str, Any]) -> Optional[AssistantPlugin]:
        """
        Load a plugin based on registry metadata.
        
        Args:
            plugin_id: The plugin's identifier
            metadata: Registry metadata for the plugin
            
        Returns:
            Plugin instance or None if loading fails
        """
        version = metadata.get("version", "v1.py")
        if not version.endswith(".py"):
            version += ".py"
            
        module_path = os.path.join(self.plugins_dir, plugin_id, version)
        return self._load_plugin_from_path(module_path)
    
    def _load_plugin_from_path(self, module_path: str) -> Optional[AssistantPlugin]:
        """
        Load a plugin from a file path.
        
        Args:
            module_path: Path to the plugin module
            
        Returns:
            Plugin instance or None if loading fails
        """
        try:
            module_name = os.path.basename(module_path)[:-3]  # Remove .py
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if not spec or not spec.loader:
                logger.error(f"Failed to load spec for plugin: {module_path}")
                return None
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find the plugin class (subclass of AssistantPlugin)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (inspect.isclass(attr) and 
                    issubclass(attr, AssistantPlugin) and 
                    attr != AssistantPlugin):
                    return attr()
            
            logger.error(f"No valid plugin class found in {module_path}")
            return None
            
        except Exception as e:
            logger.error(f"Error loading plugin from {module_path}: {e}")
            return None
    
    def _load_registry(self) -> Dict[str, Any]:
        """
        Load the plugin registry from the JSON file.
        
        Returns:
            Dictionary containing plugin registry data
        """
        if not os.path.exists(self.registry_path):
            return {}
        
        try:
            with open(self.registry_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load plugin registry: {e}")
            return {}
    
    def _update_registry(self) -> None:
        """
        Update the plugin registry with the current plugins.
        """
        registry = self._load_registry()
        
        for plugin_id, plugin in self.plugins.items():
            registry[plugin_id] = {
                "plugin_id": plugin_id,
                "description": getattr(plugin, "description", ""),
                "version": getattr(plugin, "__version__", "v1.py"),
                "is_active": True,
            }
        
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        
        with open(self.registry_path, "w") as f:
            json.dump(registry, f, indent=2)
    
    def get_plugin_by_id(self, plugin_id: str) -> Optional[AssistantPlugin]:
        """
        Get a plugin by its ID.
        
        Args:
            plugin_id: The plugin's identifier
            
        Returns:
            Plugin instance or None if not found
        """
        return self.plugins.get(plugin_id)
    
    def match_plugins_to_context(self, context: Dict[str, Any]) -> List[AssistantPlugin]:
        """
        Find all plugins that match the given context.
        
        Args:
            context: User context dictionary
            
        Returns:
            List of plugin instances that match the context
        """
        matching_plugins = []
        
        for plugin in self.plugins.values():
            try:
                if plugin.match_context(context):
                    matching_plugins.append(plugin)
            except Exception as e:
                logger.error(f"Error in plugin {plugin.plugin_id} match_context: {e}")
        
        return matching_plugins