# Legal Case Management Agent

LLM-powered legal case management agent that helps lawyers analyze cases, manage factsheets, and process legal documents. Built as a master thesis project.

## Architecture Overview

The project is a **uv workspace** with three packages: `agent`, `ui`, and `data`.

```
master-thesis/
├── agent/                         # FastAPI backend + LangGraph agent
│   ├── main.py                    # FastAPI app, endpoints, SSE streaming
│   └── src/
│       ├── agent/
│       │   ├── agent.py           # Main Agent class (LangGraph StateGraph)
│       │   ├── agent_modules.py   # Summarizer, ToolManager
│       │   ├── context_manager.py # ContextManager (structured LLM extraction, cleanup)
│       │   ├── tools.py           # Agent tools (TOOLS list)
│       │   └── utils.py           # PROMPT constant, LLM config
│       ├── auth/
│       │   ├── google_auth.py     # Google OAuth
│       │   └── supabase_auth.py   # Supabase JWT auth
│       ├── database/
│       │   ├── database_modules.py    # FirestoreManager, SupabaseManager (CRUD)
│       │   ├── vectorstore_modules.py # BQVectorStore, ChromaVectorStore (RAG)
│       │   ├── storage_modules.py     # GCSManager, SupabaseStorageManager (file storage)
│       │   ├── document_modules.py    # DocumentProcessor (PDF/DOCX/PPTX/EML parsing + OCR)
│       │   └── langchain_firestore.py # FirestoreSaver (LangGraph checkpointer)
│       └── models/
│           ├── project_models.py      # FactSheet, Party, Event, Claim, Damage, etc.
│           ├── agent_models.py        # AgentState (LangGraph TypedDict)
│           └── api_request_models.py  # AskAgentRequest, StreamEvent, AttachmentModel, etc.
├── ui/                            # Streamlit frontend
│   ├── main.py                    # App entry point
│   ├── pages/
│   │   ├── project_view.py        # Project/factsheet view
│   │   └── user_details.py        # User profile page
│   └── src/ui/
│       ├── services/
│       │   ├── auth_service.py        # Supabase auth integration
│       │   ├── database_service.py    # API calls to backend
│       │   ├── session_service.py     # Session management
│       │   └── streaming_service.py   # SSE stream consumption
│       ├── ui_components/
│       │   ├── attachments.py     # File upload + attachment display
│       │   ├── renders.py         # Chat message rendering
│       │   └── tool_results.py    # Tool result display
│       ├── models.py              # UI-side Pydantic models
│       └── utils.py               # Session state initialization
├── data/                          # Data processing scripts
├── factsheet.md                   # FactSheet template (reference for legal structure)
├── promptx/personas/              # Claude Code persona definitions
├── CLAUDE.md                      # AI assistant instructions
└── pyproject.toml                 # Root workspace config
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Package manager | uv (workspace) |
| Agent framework | LangGraph (StateGraph) |
| LLM orchestration | LangChain (init_chat_model) |
| LLM providers | Google Gemini, OpenAI GPT |
| Backend API | FastAPI + Uvicorn |
| Streaming | Server-Sent Events (SSE) |
| Frontend | Streamlit |
| Auth | Supabase Auth (JWT) |
| Database | Supabase (PostgreSQL) |
| Vector store | BigQuery Vector Store (persistent), ChromaDB (in-memory) |
| File storage | Supabase Storage (previously GCS) |
| Checkpointer | LangGraph AsyncPostgresSaver (Supabase Postgres) |
| Document parsing | PyPDF2, ocrmypdf, python-docx, python-pptx |
| Embeddings | Google Generative AI Embeddings (gemini-embedding-001) |
| Web search | Tavily |

## Key Concepts

### FactSheet
Structured Pydantic model (`FactSheet`) representing a legal case summary. Contains:
- **Parties** (plaintiff, defendant, witnesses, legal reps, etc.)
- **Background** (case narrative)
- **Events** (timeline with dates, categories, significance)
- **Claims** (legal basis, factual basis, relief sought, strength)
- **Damages** (category, amount, supporting evidence)
- **Deadlines** (dates, descriptions)
- **Governing Law** (jurisdiction, key legal areas, procedural law)
- **Disputed / Undisputed Facts**

### Agent Flow (LangGraph)
The agent uses a `StateGraph` with two nodes:
1. `call_llm` - Builds payload (system prompt + factsheet context + conversation history + attachment RAG), calls LLM
2. `call_tool` - Executes tool calls from LLM response

Conditional edge: if LLM returns tool calls -> `call_tool` -> back to `call_llm`, else -> END.

Long conversations are handled with rolling summarization (every 8 messages).

### Project Initialization Pipeline
`POST /init-project` triggers a multi-phase async pipeline:
1. **Phase 1**: Parse documents (PDF/DOCX/PPTX/EML with OCR), store in vector store + file storage, analyze initial input
2. **Phase 2**: Analyze documents and emails in parallel (extract events, claims, damages, deadlines, attachments metadata)
3. **Phase 3**: Analyze factual facts and governing law

All phases stream status events back to the frontend via SSE.

### Tools
The agent has access to these tools (`agent/src/agent/tools.py`):
- `tavily_search` - Web search via Tavily
- `read_attachment` - Read file from Supabase storage
- `read_project_attachments` - RAG query against project documents in BigQuery
- `read_laws` - RAG query against Norwegian law corpus
- `update_project` - Trigger project state update
- `clean_element` - Trigger cleanup of a specific factsheet element

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ask-agent` | Chat with agent (SSE stream) |
| POST | `/init-project` | Initialize project from attachments (SSE stream) |
| POST | `/update-project` | Add new attachments to existing project (SSE stream) |
| POST | `/cleanup-project-element/{type}` | Clean/deduplicate factsheet elements (SSE stream) |
| POST | `/cleanup-project-attr/{type}` | Clean factsheet text attributes (SSE stream) |
| GET | `/load-session-history/{id}` | Load chat history |
| GET | `/load-user-sessions` | List user sessions |
| GET | `/load-project/{id}` | Load project data |
| GET | `/load-projects` | List user projects |
| GET | `/load-project-sessions/{id}` | List sessions for a project |

## Running Locally

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- `.env` file with required environment variables

### Environment Variables
Required in `.env`:
- `GOOGLE_CLOUD_PROJECT` - GCP project ID
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase anon/service key
- `SUPABASE_DB_URL` - Postgres connection string
- `OPENAI_API_KEY` - OpenAI API key
- `TAVILY_API_KEY` - Tavily search API key
- `GOOGLE_API_KEY` - Google AI API key

### Install & Run

```bash
# Install dependencies
uv sync

# Run agent backend
uv run --package agent python agent/main.py

# Run UI (separate terminal)
uv run --package ui streamlit run ui/main.py
```

The agent API runs on `http://localhost:8080` and the UI on `http://localhost:8501`.
