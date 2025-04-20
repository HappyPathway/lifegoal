# LifeGoal - AI Wellness Assistant Project Prompt

## Project Vision
Create an intelligent, adaptable wellness assistant that helps users maintain their wellbeing through AI-driven check-ins, personalized insights, and dynamic recommendations. The system should learn from user interactions and self-extend to better serve changing needs.

## Core Requirements

### Intelligent Check-ins
- Send random wellness check-ins throughout the day
- Process natural language responses with AI
- Extract structured data about mood, sleep, nutrition, exercise, etc.
- Adapt frequency and timing based on user patterns

### Adaptive Learning
- Automatically identify wellbeing concerns from user interactions
- Create personalized wellness "pillars" based on recurring themes
- Evolve the assistant's persona over time
- Utilize the most appropriate AI model for each task

### Smart Planning
- Integrate with calendar and email systems
- Suggest optimal times for wellness activities
- Provide intelligent day structuring based on goals and meetings
- Balance productivity with wellbeing needs

### Self-extending Architecture
- Use AI to generate Python plugin modules 
- Map user goals to required plugins automatically
- Version and track plugin evolution
- Manage required secrets securely

## Technical Specifications

### Core Architecture
- Implement as a monorepo with clear component separation
- Use Google Cloud Platform for infrastructure
  - Cloud Functions for real-time processing
  - GitHub Actions for scheduled jobs
  - Cloud Storage with versioning for SQLite database
  - Secret Manager for credentials

### Data Model
- Store all state in SQLite database
- Track user interactions, goals, and wellbeing metrics
- Version assistant persona configurations
- Maintain plugin registry and mappings

### AI Integration
- Implement dynamic LLM selection based on task requirements
- Use structured prompts for consistent data extraction
- Apply function calling for structured outputs
- Maintain a feedback loop for continuous improvement

### Plugin System
- Create a standardized AssistantPlugin interface
- Support automatic generation of plugins from user needs
- Version control all AI-generated code
- Implement a secure plugin loading and execution system

### Interaction Channels
- Primary interface through Slack bot
- Support for interactive clarification flows
- Optional lightweight web dashboard for visualization

## Development Guidelines
- Focus on serverless, event-driven architecture
- Enforce strict security practices for AI-generated code
- Maintain clear documentation for all components
- Implement comprehensive testing for core functionality
- Design for easy scaling and migration to multi-repo if needed

## User Experience Goals
- Minimal friction in daily use
- Progressive adaptation to user preferences
- Transparent handling of data and recommendations
- Balanced interaction (helpful without being intrusive)

## Implementation Priorities
1. Core check-in and response parsing system
2. Basic plugin architecture
3. Slack bot integration
4. Calendar and email connectivity
5. Advanced plugin generation and management