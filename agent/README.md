# Agent Module

FastAPI backend and LangGraph-based conversational AI agent for legal case management.

## Overview

The agent processes legal documents, extracts structured case data (FactSheet), and provides context-aware responses through a stateful conversational interface. It streams responses via Server-Sent Events (SSE) and persists state to Supabase PostgreSQL.

## Structure

```
agent/
├── main.py                        # FastAPI app, all endpoints, SSE streaming
└── src/
    ├── agent/
    │   ├── agent.py               # Agent class (LangGraph StateGraph orchestrator)
    │   ├── agent_modules.py       # Summarizer, ToolManager
    │   ├── context_manager.py     # ContextManager (document analysis, extraction, cleanup)
    │   ├── tools.py               # LangChain tools (TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS)
    │   └── utils.py               # System prompts (PROMPT, PROMPT_BASELINE, PROMPT_BASELINE_RAG)
    ├── auth/
    │   ├── supabase_auth.py       # JWT auth via Supabase (primary)
    │   └── google_auth.py         # Google OAuth (legacy, unused)
    ├── database/
    │   ├── database_modules.py    # SupabaseManager (CRUD for all project/session tables)
    │   ├── storage_modules.py     # SupabaseStorageManager, GCSManager (legacy)
    │   ├── vectorstore_modules.py # BQVectorStore (persistent), ChromaVectorStore (in-memory)
    │   ├── firestore_module.py    # FirestoreManager (legacy, unused)
    │   └── langchain_firestore.py # Custom Firestore checkpointer (legacy, unused)
    ├── documents/
    │   └── document_modules.py    # DocumentProcessor (PDF/DOCX/PPTX), EmailHandler (EML)
    └── models/
        ├── project_models.py      # FactSheet, Party, Event, Claim, Damage, Deadline, etc.
        ├── agent_models.py        # AgentState (LangGraph TypedDict)
        ├── api_request_models.py  # AskAgentRequest, AttachmentModel, CleanupElementsRequest
        ├── response_models.py     # Response structures
        └── document_models.py     # Document metadata models
```

## API Endpoints

### Streaming (SSE)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ask-agent` | Chat with agent (question + optional attachments) |
| POST | `/init-project` | Initialize project from attachments (multi-phase pipeline) |
| POST | `/update-project` | Add new attachments to existing project |
| POST | `/update-project-from-session` | Update project from current session context |

### Cleanup (SSE)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/cleanup-project-element/{type}` | Clean/deduplicate a single element type |
| POST | `/cleanup-project-elements` | Clean multiple element types in one LLM call |
| POST | `/cleanup-project-attr/{type}` | Clean a factsheet text attribute |
| POST | `/cleanup-all-metadata` | Clean title and background fields |

### Vector Store

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/delete-vectorstore-project/{project_id}` | Remove all project documents from BigQuery |
| DELETE | `/delete-vectorstore-file/{file_id}` | Remove a single file from the vector store |

### Data Retrieval

| Method | Path | Description |
|--------|------|-------------|
| GET | `/load-session-history/{session_id}` | Load conversation history for a session |
| GET | `/load-user-sessions` | List all sessions for the authenticated user |
| GET | `/load-project/{project_id}` | Load full project data (FactSheet + attachments) |
| GET | `/load-projects` | List all projects for the authenticated user |
| GET | `/load-project-sessions/{project_id}` | List all sessions for a project |

## Agent Architecture

### LangGraph StateGraph

The `Agent` class uses a two-node graph:

1. **`call_llm`** — Builds the payload (system prompt + FactSheet context + conversation history + RAG results) and calls the LLM.
2. **`call_tool`** — Executes tool calls returned by the LLM.

Conditional edge: if LLM returns tool calls → `call_tool` → back to `call_llm`, else → END.

Rolling summarization triggers every 8 messages to manage context window.

### Tools (`tools.py`)

| Tool | Description | Tool Set |
|------|-------------|----------|
| `web_search` | Web search via Tavily | All |
| `read_attachment` | Read single file from Supabase Storage | TOOLS only |
| `read_attachments` | Batch read files from Supabase Storage | TOOLS only |
| `query_project_attachments` | RAG search over project documents in BigQuery | TOOLS + BASELINE_RAG |
| `query_laws` | Semantic search over Norwegian legal corpus | All |
| `read_specific_law` | Retrieve a specific Norwegian statute by paragraph | All |
| `list_project_files_emails` | List all attachments and emails in a project | TOOLS only |

**Tool sets:**
- `TOOLS` — Full agent (all tools above)
- `BASELINE_TOOLS` — `web_search`, `query_laws`, `read_specific_law`
- `BASELINE_RAG_TOOLS` — `web_search`, `query_laws`, `read_specific_law`, `query_project_attachments`

### LLMs

- **Primary**: Google Gemini 2.5 Flash (conversation, analysis, embeddings)
- **Secondary**: OpenAI GPT-4o-mini (summarization, titles)

### Project Initialization Pipeline

`POST /init-project` runs a three-phase async pipeline:

1. **Phase 1** — Parse documents (PDF/DOCX/PPTX/EML with OCR), store in vector store and file storage, analyze initial input
2. **Phase 2** — Analyze documents and emails in parallel (extract events, claims, damages, deadlines, attachment metadata)
3. **Phase 3** — Analyze factual facts and governing law

All phases stream status events back via SSE.

## Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `projects` | Legal cases, linked to users |
| `sessions` | Conversation sessions per project |
| `session_events` | Individual events within a session (messages, tool calls) |
| `session_attachments` | Files uploaded within a session |
| `project_attachments` | Case documents with metadata (type, category, key provisions) |
| `project_parties` | Parties involved (name, role, entity type) |
| `project_events` | Timeline events (date, category, significance) |
| `project_claims` | Legal claims with basis, relief, strength |
| `project_damages` | Damage claims with amounts and evidence |
| `project_deadlines` | Important dates and deadlines |

### Checkpoint Tables (LangGraph)

| Table | Description |
|-------|-------------|
| `checkpoints` | Full conversation state (JSONB) |
| `checkpoint_writes` | Pending writes during checkpoint creation |
| `checkpoint_blobs` | Large binary data for checkpoints |
| `checkpoint_migrations` | Schema version tracking |

### Relationships

```
auth.users
  └── projects (user_id)
      ├── sessions (project_id)
      │   └── session_events (session_id)
      │       └── session_attachments (event_id)
      ├── project_attachments (project_id)
      │   ├── project_claims (file_id)
      │   ├── project_damages (file_id)
      │   ├── project_deadlines (file_id)
      │   └── project_events (file_id)
      ├── project_parties (project_id)
      └── project_legal (project_id)
```

## Running

```bash
uv run --package agent python agent/main.py
```

The API runs on `http://localhost:8080`.

## Environment Variables

```bash
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_DB_URL=postgresql://...
GOOGLE_CLOUD_PROJECT=your_gcp_project_id
GOOGLE_API_KEY=your_google_ai_key
OPENAI_API_KEY=your_openai_key
TAVILY_API_KEY=your_tavily_key
```

## Security

- JWT-based auth: all endpoints require `Authorization: Bearer <token>`
- Row-level security (RLS) on all Supabase tables
- File access scoped to user accounts via Supabase Storage
