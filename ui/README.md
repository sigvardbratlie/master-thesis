# UI Module

Streamlit-based web interface for the legal case management agent.

## Overview

The UI provides a chat interface where lawyers interact with the agent, upload legal documents, and view structured case data (FactSheet). It connects to the FastAPI backend via REST/SSE and to Supabase for authentication.

## Structure

```
ui/
├── main.py                    # App entry point, auth flow, layout
├── pages/
│   ├── project_view.py        # Project/FactSheet view
│   └── user_details.py        # User profile page
└── src/ui/
    ├── services/
    │   ├── auth_service.py        # Supabase auth (login, session restore)
    │   ├── database_service.py    # API calls to agent backend
    │   ├── session_service.py     # Session state management
    │   └── streaming_service.py   # SSE stream consumption
    ├── ui_components/
    │   ├── attachments.py         # File upload dialog and display
    │   ├── renders.py             # Chat interface and sidebar
    │   └── tool_results.py        # Tool result formatting and display
    ├── models.py                  # UI-side Pydantic models
    └── utils.py                   # Session state initialization helpers
```

## Key Components

### Auth (`auth_service.py`)
- `SupabaseAuthService`: Email/password login via Supabase
- Restores sessions from refresh token stored in URL query params

### Chat (`renders.py`)
- `get_chat_component()`: Main chat interface with streaming responses
- `get_sidebar_component()`: Project and session navigation
- Handles first-question flow and conversation history display

### Attachments (`attachments.py`)
- `get_attachment_component()`: File upload dialog
- Supports PDF, DOCX, PPTX, EML formats
- Files are uploaded as base64 to the backend

### Streaming (`streaming_service.py`)
- Consumes SSE events from `/ask-agent` and `/init-project` endpoints
- Renders partial responses in real time

## Running

```bash
uv run --package ui streamlit run ui/main.py
```

Requires the agent backend to be running on `http://localhost:8080`.

## Environment Variables

```bash
AGENT_URL=http://localhost:8080   # Backend API URL
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
```
