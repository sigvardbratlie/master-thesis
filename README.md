# Legal Case Management Agent

LLM-powered legal case management agent that helps lawyers analyze cases, manage factsheets, and process legal documents. Built as a master thesis project.

## Architecture Overview

The project is a **uv workspace** with four packages: `agent`, `ui`, `evals`, and `data-viewer`.

```
master-thesis/
├── agent/                         # FastAPI backend + LangGraph agent
│   ├── main.py                    # FastAPI app, endpoints, SSE streaming
│   └── src/
│       ├── agent/
│       │   ├── agent.py           # Main Agent class (LangGraph StateGraph)
│       │   ├── agent_modules.py   # Summarizer, ToolManager
│       │   ├── context_manager.py # ContextManager (extraction, cleanup)
│       │   ├── tools.py           # Agent tools (TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS)
│       │   └── utils.py           # PROMPT constants, LLM initialization
│       ├── auth/
│       │   ├── supabase_auth.py   # Supabase JWT auth (primary)
│       │   └── google_auth.py     # Google OAuth (legacy, unused)
│       ├── database/
│       │   ├── database_modules.py    # SupabaseManager (CRUD)
│       │   ├── vectorstore_modules.py # BQVectorStore (persistent), ChromaVectorStore (in-memory)
│       │   ├── storage_modules.py     # SupabaseStorageManager, GCSManager (legacy)
│       │   ├── firestore_module.py    # FirestoreManager (legacy, unused)
│       │   └── langchain_firestore.py # Custom Firestore checkpointer (legacy, unused)
│       ├── documents/
│       │   └── document_modules.py    # DocumentProcessor, EmailHandler (PDF/DOCX/PPTX/EML + OCR)
│       └── models/
│           ├── project_models.py      # FactSheet, Party, Event, Claim, Damage, etc.
│           ├── agent_models.py        # AgentState (LangGraph TypedDict)
│           ├── api_request_models.py  # AskAgentRequest, AttachmentModel, CleanupElementsRequest
│           ├── response_models.py     # Response structures
│           └── document_models.py     # Document metadata models
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
├── evals/                         # Evaluation framework
│   ├── collect.py                 # CLI: run agent against test datasets, collect results
│   ├── evaluate.py                # CLI: run DeepEval metrics on collected results
│   └── src/evals/
│       ├── dataset_module.py      # Dataset, CollectAgentResult (GCS operations)
│       ├── evaluate_module.py     # Evaluater (DeepEval metrics)
│       ├── models.py              # ConversationTurn, Session, GatheredResultPayload, EvalOutput
│       ├── langsmith_module.py    # LangSmith tracing integration
│       ├── lovdata_module.py      # Norwegian legal document processing
│       └── utils.py               # DocumentHandler, ParsedAttachment, ParsedEmail
├── data-viewer/                   # Streamlit app for browsing GCS datasets
│   ├── main.py                    # Dataset viewer (browse, compare results, display metrics)
│   └── fix_dataset.py             # Data migration/cleanup utility
├── thesis/                        # LaTeX master thesis source
│   ├── main.tex                   # Root document
│   ├── chapters/                  # Chapter tex files
│   └── figures/                   # Images and diagrams
├── factsheet.md                   # FactSheet template (reference for legal structure)
├── promptx/personas/              # AI assistant persona definitions
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
| LLM providers | Google Gemini 2.5 Flash (primary), OpenAI GPT-4o-mini (secondary) |
| Backend API | FastAPI + Uvicorn |
| Streaming | Server-Sent Events (SSE) |
| Frontend | Streamlit |
| Auth | Supabase Auth (JWT) |
| Database | Supabase (PostgreSQL) |
| Vector store | BigQuery Vector Store (persistent), ChromaDB (in-memory) |
| File storage | Supabase Storage |
| Checkpointer | LangGraph AsyncPostgresSaver (Supabase PostgreSQL) |
| Document parsing | PyPDF2, ocrmypdf, python-docx, python-pptx |
| Embeddings | Google Generative AI Embeddings (gemini-embedding-001) |
| Web search | Tavily |
| Evaluation | DeepEval |

## Key Concepts

### FactSheet
Structured Pydantic model (`FactSheet`) representing a legal case summary. Contains:
- **Parties** (plaintiff, defendant, witnesses, legal reps, etc.)
- **Background** (case narrative)
- **Events** (timeline with dates, categories, significance)
- **Claims** (legal basis, factual basis, relief sought, strength)
- **Damages** (category, amount, supporting evidence)
- **Deadlines** (dates, descriptions)

### Agent Flow (LangGraph)
The agent uses a `StateGraph` with two nodes:
1. `call_llm` - Builds payload (system prompt + factsheet context + conversation history + attachment RAG), calls LLM
2. `call_tool` - Executes tool calls from LLM response

Conditional edge: if LLM returns tool calls -> `call_tool` -> back to `call_llm`, else -> END.

Long conversations are handled with rolling summarization (every 8 messages).

### Project Initialization Pipeline
`POST /init-project` triggers a multi-phase async pipeline:
1. **Phase 1**: Parse documents (PDF/DOCX/PPTX/EML with OCR), store in vector store + file storage, analyze initial input
2. **Phase 2**: Analyze documents and emails in parallel (extract events, claims, damages, deadlines, attachment metadata)
3. **Phase 3**: Analyze factual facts and governing law

All phases stream status events back to the frontend via SSE.

### Tools
The agent has access to these tools (`agent/src/agent/tools.py`):

**Full agent (TOOLS):**
- `web_search` - Web search via Tavily
- `read_attachment` - Read single file from Supabase Storage
- `read_attachments` - Batch read files from Supabase Storage
- `query_project_attachments` - RAG query against project documents in BigQuery
- `query_laws` - Semantic search over Norwegian legal corpus
- `read_specific_law` - Retrieve a specific Norwegian statute by paragraph
- `list_project_files_emails` - List all attachments and emails in a project

**Baseline variants:**
- `BASELINE_TOOLS` — `web_search`, `query_laws`, `read_specific_law`
- `BASELINE_RAG_TOOLS` — `web_search`, `query_laws`, `read_specific_law`, `query_project_attachments`

### Evaluation Framework
Three agent configurations are compared in `evals/`:
1. **Custom Agent** — Full tools: web search, file read, project RAG, Norwegian laws, file listing
2. **Baseline Agent** — Web search + Norwegian laws only
3. **Baseline RAG Agent** — Web search + Norwegian laws + project attachment RAG

Results and metrics are stored in GCS and scored with DeepEval (legal accuracy, answer relevancy).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ask-agent` | Chat with agent (SSE stream) |
| POST | `/init-project` | Initialize project from attachments (SSE stream) |
| POST | `/update-project` | Add new attachments to existing project (SSE stream) |
| POST | `/update-project-from-session` | Update project based on session conversation (SSE stream) |
| POST | `/cleanup-project-element/{type}` | Clean/deduplicate a single factsheet element type (SSE stream) |
| POST | `/cleanup-project-elements` | Clean multiple factsheet element types in one LLM call (SSE stream) |
| POST | `/cleanup-project-attr/{type}` | Clean factsheet text attribute (SSE stream) |
| POST | `/cleanup-all-metadata` | Clean title and background fields (SSE stream) |
| DELETE | `/delete-vectorstore-project/{project_id}` | Delete project from BigQuery vector store |
| DELETE | `/delete-vectorstore-file/{file_id}` | Delete single file from vector store |
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

# Run dataset viewer (separate terminal)
uv run --package data-viewer streamlit run data-viewer/main.py
```

The agent API runs on `http://localhost:8080` and the UI on `http://localhost:8501`.
