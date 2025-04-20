# GitHub Copilot Instructions for LifeGoal Project

This document provides guidance for AI coding assistants working on the LifeGoal wellness assistant project.

## Project Overview

LifeGoal is an AI-powered wellness assistant that uses intelligent check-ins and adaptive learning to help users maintain their wellbeing. The system uses:

- Cloud Functions for real-time interactions (Slack, SMS)
- GitHub Actions for scheduled tasks
- SQLite + GCS for state storage
- Dynamic plugin architecture that self-extends based on user needs

## Architecture Guidelines

When assisting with this codebase, please follow these principles:

### 1. Serverless First

- Prefer stateless Cloud Functions for real-time interactions
- Use GitHub Actions for scheduled jobs and background processing
- Avoid suggesting traditional server architectures

### 2. State Management

- All state should be stored in the SQLite database in GCS
- Functions should download the latest DB, make changes, and re-upload
- Ensure proper versioning and atomic operations

### 3. Plugin System

- All functional extensions should be implemented as plugins
- Plugins are Python modules with a standard interface
- New plugins should be generated through AI, not written manually
- Plugin code must be safe, sandboxed, and follow security best practices

### 4. AI Integration

- Use the appropriate LLM for each task via the LLMRegistry
- Structure all prompts clearly with examples
- Parse responses into structured data
- Implement dynamic model selection based on task requirements

### 5. Security Practices

- All secrets should be stored in Google Secret Manager
- No secrets in code, environment variables, or logs
- Use least privilege principle for all service accounts
- Validate all AI-generated code before execution

## Code Patterns

### Plugin Interface

```python
class AssistantPlugin:
    plugin_id: str
    description: str
    required_secrets: list[str]

    def match_context(self, user_context: dict) -> bool:
        """Return True if plugin is useful for current context"""
        pass

    def execute(self, context: dict, llm_registry) -> dict:
        """Run plugin logic, return data"""
        pass
```

### Database Access

```python
# Download latest DB
db_path = download_db_from_gcs()

# Use it
with sqlite3.connect(db_path) as conn:
    # Make changes

# Upload back
upload_db_to_gcs(db_path)
```

### LLM Selection

```python
llm = llm_registry.select_model(task_type)
result = llm.generate(prompt)
```

## Areas to Improve

When suggesting improvements, focus on:

1. Simplifying the plugin generation and loading process
2. Enhancing the user interaction flows in Slack
3. Improving the structured data extraction from natural language
4. Optimizing the SQLite schema for tracking wellbeing metrics
5. Enhancing calendar and email integration capabilities