# Agent Module

FastAPI backend and LangGraph-based conversational AI agent for legal case management.

## Overview

The agent processes legal documents, extracts structured case data (FactSheet), and provides context-aware responses through a stateful conversational interface. It streams responses via Server-Sent Events (SSE) and persists state to Supabase PostgreSQL.

## Structure

```
agent/
├── main.py                        # FastAPI app, lifespan, router registration
└── src/
    ├── agent/
    │   ├── agent.py               # Agent class — conversational LangGraph StateGraph
    │   ├── pipelines.py           # ProjectPipeline — init/update project LangGraph pipelines
    │   ├── clean.py               # ProjectClean — cleanup/dedup LangGraph pipelines
    │   ├── agent_modules.py       # Summarizer, ToolManager
    │   ├── context_manager.py     # ContextManager (document analysis, extraction, cleanup)
    │   ├── tools.py               # LangChain tools (TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS)
    │   └── utils.py               # System prompts, LLM factory (pick_llm), to_thread_config
    ├── api/
    │   └── routers/
    │       ├── agent.py           # /ask-agent endpoint
    │       ├── project.py         # /init-project, /update-project endpoints
    │       ├── clean.py           # /cleanup-* endpoints
    │       └── vectorstore.py     # /delete-vectorstore-* endpoints
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

### Agent (SSE)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Chat with agent (question + optional attachments) |

### Project (SSE)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/project/init-project` | Initialize project from attachments (parallel pipeline) |
| POST | `/project/update-project` | Add new attachments to existing project |
| POST | `/project/update-project-from-session` | Update project from current session context |

### Cleanup (SSE)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/project/clean-project-elements` | Clean/deduplicate multiple element types |
| POST | `/project/clean-all-metadata` | Clean title and background fields |

### Vector Store

| Method | Path | Description |
|--------|------|-------------|
| DELETE | `/vectorstore/delete-vectorstore-project/{project_id}` | Remove all project documents from BigQuery |
| DELETE | `/vectorstore/delete-vectorstore-file/{file_id}` | Remove a single file from the vector store |

## Agent Architecture

The system is split into three separate LangGraph components:

### `Agent` (conversational)

`agent.py` — two-node graph for conversation:

1. **`init`** — Injects system prompt on first turn.
2. **`call_llm`** — Builds payload (system prompt + FactSheet context + conversation history) and calls LLM.
3. **`call_tool`** — Executes tool calls returned by the LLM.

Conditional edge: if LLM returns tool calls → `call_tool` → back to `call_llm`, else → END. Rolling summarization triggers every 8 messages.

### `ProjectPipeline` (project init/update)

`pipelines.py` — parallel LangGraph pipelines for document processing:

**Init pipeline** (`compile_init_pipeline`): `collapse_emails` + `initialize_input` + `storage` (parallel) → `parsing` → `embedding` + `analyze` → `update_metadata` → `save`

**Update pipeline** (`compile_update_pipeline`): `load_project_data` + `collapse_emails` + `storage` (parallel) → `parsing` → `embedding` + `analyze` → `update_metadata` → `save`

### `ProjectClean` (cleanup/dedup)

`clean.py` — pipelines for factsheet cleanup:

**Elements pipeline** (`compile_clean_elements`): load → clean (LLM dedup per element type) → save

**Metadata pipeline** (`compile_clean_metadata`): load → clean (LLM rewrites title/background) → save

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

`POST /project/init-project` runs a parallel LangGraph pipeline:

- **Parallel start**: email thread collapsing, initial input extraction (LLM), file storage upload
- **Parsing**: text extraction from PDF/DOCX/PPTX/EML (with OCR)
- **Parallel**: vector store embedding + document/email analysis (LLM, batched)
- **Metadata update**: update title, background, parties from extracted events
- **Save**: persist FactSheet and all elements to Supabase

All stages stream `status` events via SSE. The final `save` node streams a `result` event with the full FactSheet.

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
