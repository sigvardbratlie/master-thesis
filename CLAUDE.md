# Repository Guidelines

## General Instructions

Always write all documentation, variable names and code in english.
Keep everything neat and tidy. Do not produce more than asked.
Do not write code unless explicitly asked.

## Persona Selection

**FIRST STEP**: Read the relevant brief in `promptx/personas/` and commit to a role:

1. **Developer Agent** – Implement features and fix bugs (`promptx/personas/agent-developer.md`)
2. **Code Reviewer Agent** – Review code quality and patterns (`promptx/personas/agent-code-reviewer.md`)
3. **Rebaser Agent** – Clean commit history and resolve conflicts (`promptx/personas/agent-rebaser.md`)
4. **Merger Agent** – Handle branch merges and releases (`promptx/personas/agent-merger.md`)
5. **Multiplan Manager Agent** – Orchestrate complex multi-step tasks (`promptx/personas/agent-multiplan-manager.md`)

## Project Context

**Mission**: Build an LLM-powered legal case management agent that helps lawyers analyze cases, manage factsheets, and process legal documents.

This repository provides:
- **Agent**: LangGraph-based conversational agent with tool-calling (`agent/`)
- **Database**: Supabase (PostgreSQL + Storage + Auth)
- **UI**: Streamlit interface for chat and factsheet display (`ui/`)
- **Evals**: Evaluation framework for benchmarking agent performance (`evals/`)
- **Data Viewer**: Streamlit app for browsing GCS datasets (`data-viewer/`)

### Key Concepts
- **FactSheet**: Structured legal case summary (parties, claims, damages, timeline, governing law)
- **Attachments**: PDF/DOCX/PPTX/EML documents parsed and stored in vector store for RAG
- **Multi-LLM**: Supports Google Gemini (primary) and OpenAI GPT (secondary)

```
├── agent/
│   ├── main.py                    # FastAPI app, endpoints, SSE streaming
│   └── src/
│       ├── agent/                 # Core agent logic (LangGraph)
│       │   ├── agent.py           # Main Agent class (LangGraph StateGraph)
│       │   ├── agent_modules.py   # Summarizer, ToolManager
│       │   ├── context_manager.py # ContextManager (extraction, cleanup)
│       │   ├── tools.py           # Agent tools (TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS)
│       │   └── utils.py           # PROMPT constants, LLM initialization
│       ├── auth/                  # Supabase JWT auth (google_auth.py is legacy)
│       ├── database/              # SupabaseManager, BQVectorStore, SupabaseStorageManager
│       ├── documents/             # DocumentProcessor, EmailHandler (PDF/DOCX/PPTX/EML + OCR)
│       └── models/                # Pydantic models (project_models, agent_models, api_request_models)
├── ui/
│   ├── main.py                    # Streamlit app entry
│   ├── pages/                     # project_view.py, user_details.py
│   └── src/ui/                    # Services, UI components, models
├── evals/
│   ├── collect.py                 # CLI: run agent against test datasets
│   ├── evaluate.py                # CLI: run DeepEval metrics
│   └── src/evals/                 # dataset_module, evaluate_module, models, utils
├── data-viewer/
│   └── main.py                    # Streamlit app for browsing GCS datasets
├── promptx/
│   └── personas/                  # Agent persona definitions
└── factsheet.md                   # FactSheet template
```

## Core Principles

1. **STUDY FIRST**: Review existing code, recent commits, and related modules before making changes.
2. **FOLLOW PATTERNS**: Reuse existing patterns from `agent_modules.py` and `database_modules.py`.
3. **KEEP IT SIMPLE**: Prefer minimal changes over complex abstractions.
4. **TEST CHANGES**: Verify changes work before committing.
5. **COMMIT WITH CONTEXT**: Clear commit messages describing what and why.

## Technical Notes

- **Python 3.13** with uv for dependency management (workspace: agent, ui, evals, data-viewer)
- **Secrets**: Environment variables in `.env` (never commit)
- **LangChain/LangGraph**: For agent orchestration and streaming
- **Auth**: Supabase JWT (Bearer token). `supabase_auth.py` is primary; `google_auth.py` is legacy
- **Database**: Supabase PostgreSQL (primary). FirestoreManager is legacy
- **Checkpointer**: `AsyncPostgresSaver` (LangGraph state via Supabase PostgreSQL)
