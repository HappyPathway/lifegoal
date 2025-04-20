"""
Plugin Generator for LifeGoal Assistant

This script generates new plugin modules based on user interactions and goals.
It uses the appropriate LLM to generate Python code that follows the
AssistantPlugin interface.
"""
import os
import argparse
import json
import re
import ast
from datetime import datetime
from typing import Dict, Any, List, Optional

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_registry import LLMRegistry


# Constants
PLUGIN_DIR = "plugins/user_generated"
REGISTRY_PATH = "plugins/registry.json"


def generate_plugin_code(plugin_id: str, 
                        description: str, 
                        goal_data: Dict[str, Any]) -> str:
    """
    Generate plugin code using an AI model.
    
    Args:
        plugin_id: ID for the plugin
        description: Description of the plugin
        goal_data: Data about the user goal to be addressed by the plugin
        
    Returns:
        Generated Python code for the plugin
    """
    # Initialize the LLM registry and select the code generation model
    llm_registry = LLMRegistry()
    model = llm_registry.select_model("code")
    
    # Format the prompt for plugin generation
    prompt = f"""
    Generate a Python plugin module for a wellness assistant application.
    
    PLUGIN ID: {plugin_id}
    DESCRIPTION: {description}
    GOAL: {goal_data.get('name', 'N/A')}
    GOAL DESCRIPTION: {goal_data.get('description', 'N/A')}
    
    The plugin must:
    1. Import the AssistantPlugin class from core.base_plugin
    2. Define a class that inherits from AssistantPlugin
    3. Set the plugin_id, description, and required_secrets class variables
    4. Implement match_context(self, user_context: Dict[str, Any]) -> bool
    5. Implement execute(self, context: Dict[str, Any], llm_registry: Any) -> Dict[str, Any]
    
    The match_context method should determine if this plugin applies to the current user context.
    The execute method should perform the plugin's logic using the appropriate LLM.
    
    Follow this template:
    ```python
    from typing import Dict, Any, List
    from core.base_plugin import AssistantPlugin
    
    class ExamplePlugin(AssistantPlugin):
        plugin_id = "example_plugin"
        description = "Example plugin that does something"
        required_secrets = []  # List any needed API keys or credentials here
        
        def match_context(self, user_context: Dict[str, Any]) -> bool:
            # Determine if this plugin should be triggered
            return True  # Or some logic based on user_context
        
        def execute(self, context: Dict[str, Any], llm_registry: Any) -> Dict[str, Any]:
            # Use an appropriate LLM
            model = llm_registry.select_model("chat")
            
            # Get data from context
            user_data = context.get("current_data", {})
            
            # Generate response or perform action
            response = model.generate("Create a helpful message")
            
            # Return result
            return {
                "message": response,
                "metadata": {"plugin_id": self.plugin_id, "timestamp": context.get("timestamp")}
            }
    ```
    
    ONLY return the Python code, nothing else.
    """
    
    # Generate the plugin code
    generated_code = model.generate(prompt)
    
    # Clean up the generated code (remove code block markers if present)
    generated_code = re.sub(r'^```python\s*', '', generated_code, flags=re.MULTILINE)
    generated_code = re.sub(r'\s*```$', '', generated_code, flags=re.MULTILINE)
    
    return generated_code


def validate_plugin_code(code: str) -> bool:
    """
    Validate the generated plugin code.
    
    Args:
        code: The generated Python code
        
    Returns:
        True if the code is valid, False otherwise
    """
    try:
        # Parse the code to AST
        tree = ast.parse(code)
        
        # Check for AssistantPlugin import and inheritance
        import_found = False
        class_found = False
        
        for node in ast.walk(tree):
            # Check for import
            if isinstance(node, ast.ImportFrom) and node.module == 'core.base_plugin':
                import_found = True
            
            # Check for class definition
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == 'AssistantPlugin':
                        class_found = True
        
        return import_found and class_found
    
    except SyntaxError:
        print("Generated code has syntax errors.")
        return False


def save_plugin(plugin_id: str, code: str, version_num: int = 1) -> str:
    """
    Save the generated plugin code to a file.
    
    Args:
        plugin_id: ID for the plugin
        code: The generated Python code
        version_num: Version number for the plugin
        
    Returns:
        Path to the saved plugin file
    """
    # Create plugin directory
    plugin_dir = os.path.join(PLUGIN_DIR, plugin_id)
    os.makedirs(plugin_dir, exist_ok=True)
    
    # Create the file path
    file_path = os.path.join(plugin_dir, f"v{version_num}.py")
    
    # Write the code to the file
    with open(file_path, "w") as f:
        f.write(code)
    
    return file_path


def update_registry(plugin_id: str, description: str, version_num: int) -> None:
    """
    Update the plugin registry with the new plugin.
    
    Args:
        plugin_id: ID for the plugin
        description: Description of the plugin
        version_num: Version number for the plugin
    """
    # Ensure registry directory exists
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    
    # Load existing registry or create a new one
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r") as f:
            registry = json.load(f)
    else:
        registry = {}
    
    # Update the registry
    registry[plugin_id] = {
        "plugin_id": plugin_id,
        "description": description,
        "version": f"v{version_num}.py",
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "is_active": True
    }
    
    # Write the updated registry back
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


def get_next_version(plugin_id: str) -> int:
    """
    Get the next version number for a plugin.
    
    Args:
        plugin_id: ID for the plugin
        
    Returns:
        Next version number
    """
    plugin_dir = os.path.join(PLUGIN_DIR, plugin_id)
    
    # If the plugin directory doesn't exist, version 1
    if not os.path.exists(plugin_dir):
        return 1
    
    # Get all version files
    version_files = [f for f in os.listdir(plugin_dir) 
                    if f.startswith("v") and f.endswith(".py")]
    
    if not version_files:
        return 1
    
    # Extract version numbers
    versions = [int(f[1:-3]) for f in version_files]
    
    # Return the next version
    return max(versions) + 1


def main():
    """Main function to run when the script is executed directly."""
    parser = argparse.ArgumentParser(description="Generate a plugin for the LifeGoal assistant.")
    parser.add_argument("plugin_id", help="ID for the plugin (snake_case)")
    parser.add_argument("description", help="Description of the plugin")
    parser.add_argument("--goal-name", help="Name of the goal to address")
    parser.add_argument("--goal-description", help="Description of the goal")
    
    args = parser.parse_args()
    
    # Create goal data dictionary
    goal_data = {
        "name": args.goal_name or args.description,
        "description": args.goal_description or ""
    }
    
    # Get the next version number
    version_num = get_next_version(args.plugin_id)
    
    # Generate plugin code
    print(f"Generating plugin '{args.plugin_id}' (v{version_num})...")
    plugin_code = generate_plugin_code(args.plugin_id, args.description, goal_data)
    
    # Validate the generated code
    if not validate_plugin_code(plugin_code):
        print("Error: Generated plugin code is not valid.")
        return
    
    # Save the plugin
    file_path = save_plugin(args.plugin_id, plugin_code, version_num)
    
    # Update the registry
    update_registry(args.plugin_id, args.description, version_num)
    
    print(f"Plugin generated: {file_path}")
    print(f"Registry updated: {REGISTRY_PATH}")


if __name__ == "__main__":
    main()