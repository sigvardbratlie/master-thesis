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
- **Database**: Firestore for conversations and vector search (considering migration to Supabase)
- **UI**: Streamlit interface for chat and factsheet display (`ui/`)
- **Auth**: Google authentication (`agent/src/auth/`)

### Key Concepts
- **FactSheet**: Structured legal case summary (parties, claims, damages, timeline, governing law)
- **Attachments**: PDF/text documents parsed and stored in vector store for RAG
- **Multi-LLM**: Supports Google, OpenAI, and Claude as LLM providers

```
├── agent/
│   ├── main.py                    # Agent entry point
│   └── src/
│       ├── agent/                 # Core agent logic (LangGraph)
│       │   ├── agent.py           # Main Agent class
│       │   ├── agent_modules.py   # Summarizer, ContextManager, ToolManager
│       │   ├── basemodels.py      # Pydantic models (FactSheet, AgentState)
│       │   └── tools.py           # Agent tools
│       ├── auth/                  # Google authentication
│       └── database/              # Firestore, vector search, conversation management
├── ui/
│   ├── main.py                    # Streamlit app entry
│   ├── pages/                     # Streamlit pages
│   └── src/ui/                    # UI components and services
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

- **Python 3.13** with uv for dependency management
- **Secrets**: Environment variables in `.env` (never commit)
- **LangChain/LangGraph**: For agent orchestration and streaming
