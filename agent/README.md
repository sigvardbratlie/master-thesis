# Agent Module

AI-powered legal document analysis agent built with LangChain and LangGraph. The agent provides intelligent document processing, retrieval-augmented generation (RAG), and structured data extraction for legal case management.

## Overview

This module implements a stateful conversational AI agent that:
- Processes and analyzes legal documents (PDF, text files)
- Extracts structured information (claims, events, parties, deadlines, damages)
- Provides context-aware responses using RAG
- Maintains conversation state with checkpointing
- Integrates with Supabase for data persistence and Google Cloud services

## Architecture

### Core Components

- **Agent** (`agent.py`): Main orchestrator handling conversation flow and tool execution
- **Agent Modules** (`agent_modules.py`): 
  - `Summarizer`: Document summarization
  - `ContextManager`: Retrieval and context management
  - `ToolManager`: Tool execution and validation
- **Tools** (`tools.py`): Custom tools for BigQuery queries, web search (Tavily), and document retrieval
- **Database Modules**: Supabase and Firestore integrations
- **Storage Modules**: Document upload/download via Supabase Storage
- **Vector Store**: ChromaDB and BigQuery Vector Search for semantic retrieval

### State Management

The agent uses LangGraph's checkpointing system with PostgreSQL (via Supabase) to maintain conversation state, enabling:
- Conversation history persistence
- Session resumption
- Multi-turn dialogue context

## Database Structure

### Supabase Schema

#### Core Tables

**projects**
- Primary entity for legal cases/projects
- Links to user accounts
- Tracks creation and update timestamps

**sessions**
- Conversation sessions tied to projects
- Stores LLM model configuration
- Tracks session lifecycle

**session_events**
- Individual events within a session (messages, tool calls)
- Ordered sequence of interactions
- Contains LangChain run IDs for traceability

**session_attachments**
- Files uploaded during sessions
- Links to specific queries and events

#### Project Data Tables

**project_attachments**
- Case documents and files
- Metadata: file type, category, significance
- Key provisions extraction (JSONB)
- Party roles and dates

**project_parties**
- Parties involved in the case
- Legal names, roles, entity types
- Contact information

**project_events**
- Timeline events in the case
- Categorized by significance
- Party involvement tracking
- Disputed vs. undisputed markers

**project_claims**
- Legal claims and counterclaims
- Factual and legal basis
- Relief sought
- Strength assessments
- Defense arguments

**project_damages**
- Damage claims with amounts
- Supporting evidence (JSONB)
- Categorization by type

**project_deadlines**
- Important dates and deadlines
- Party-specific deadlines

**project_legal**
- Governing law references
- Disputed and undisputed facts

#### Checkpoint Tables (LangGraph)

**checkpoints**
- Primary checkpoint storage
- Contains full conversation state (JSONB)
- Hierarchical with namespaces

**checkpoint_writes**
- Pending writes during checkpoint creation
- Task-based organization

**checkpoint_blobs**
- Large binary data associated with checkpoints
- Channel-based versioning

**checkpoint_migrations**
- Schema version tracking for checkpoints

#### User Management

**user_details**
- Extended user profile information
- Company associations
- User roles

### Foreign Key Relationships

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

## Setup

### Prerequisites

- Python 3.13+
- Supabase project with PostgreSQL database
- Google Cloud Project (for BigQuery, Firestore, Cloud Storage)
- OpenAI API key or other LLM provider
- Tavily API key (for web search)

### Environment Variables

Create a `.env` file in the `agent/` directory:

```bash
# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Google Cloud
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_APPLICATION_CREDENTIALS=./gcloud-keys.json

# LLM Provider
OPENAI_API_KEY=your_openai_key
# or
ANTHROPIC_API_KEY=your_anthropic_key

# Tools
TAVILY_API_KEY=your_tavily_key

# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname
```

### Installation

```bash
# Navigate to agent directory
cd agent/

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .
```

### Google Cloud Setup

1. Create a service account with appropriate permissions:
   - BigQuery Data Editor
   - Firestore User
   - Storage Object Admin

2. Download the service account key as `gcloud-keys.json` in the `agent/` directory

### Database Initialization

The Supabase database schema is automatically managed through migrations. Ensure your Supabase project has the checkpoint tables initialized:

```sql
-- Run the LangGraph checkpoint schema initialization
-- (see SUPABASE_SCHEMA.md for full schema)
```

## Usage

### Basic Agent Initialization

```python
from agent.agent import Agent
from agent.tools import tavily_search, list_table_info, run_query
from langgraph.checkpoint.postgres import PostgresSaver

# Initialize checkpointer
checkpointer = PostgresSaver.from_conn_string(
    os.getenv("DATABASE_URL")
)

# Create agent
agent = Agent(
    tools=[tavily_search, list_table_info, run_query],
    prompt="You are a helpful legal assistant...",
    checkpointer=checkpointer
)

# Run agent
config = {"configurable": {"thread_id": "session-123"}}
response = await agent.run(
    user_message="Analyze this document",
    config=config
)
```

### Document Processing

```python
from database import SupabaseStorageManager, DocumentProcessor

# Upload document
storage = SupabaseStorageManager()
file_path = storage.upload_file(
    file_content=pdf_bytes,
    filename="contract.pdf",
    bucket="documents"
)

# Process document
processor = DocumentProcessor()
chunks = processor.process_pdf(pdf_bytes)
```

### Database Operations

```python
from database import SupabaseManager

db = SupabaseManager()

# Create project
project = db.create_project(
    user_id="user-uuid",
    title="Case ABC vs XYZ",
    background="Contract dispute..."
)

# Create session
session = db.create_session(
    user_id="user-uuid",
    project_id=project.project_id,
    llm_model="gpt-4"
)

# Add event
event = db.create_event(
    session_id=session.session_id,
    type="user_message",
    content="What are the key claims?"
)
```

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_agent.py

# Run with coverage
pytest --cov=src tests/
```

### Test Structure

- `test_agent.py`: Agent behavior and state management
- `test_storage.py`: File upload/download operations
- `test_vectorstore.py`: RAG and retrieval functionality
- `test_supabase.py`: Database operations
- `fixtures/`: Test data and mock objects

## Project Structure

```
agent/
├── src/
│   ├── agent/
│   │   ├── agent.py              # Main agent class
│   │   ├── agent_modules.py      # Helper modules (Summarizer, ContextManager, etc.)
│   │   ├── tools.py              # Custom LangChain tools
│   │   ├── basemodels.py         # Pydantic models
│   │   └── utils.py              # Utility functions
│   ├── auth/
│   │   ├── google_auth.py        # Google OAuth integration
│   │   └── supabase_auth.py      # Supabase authentication
│   └── database/
│       ├── database_modules.py   # Supabase + Firestore managers
│       ├── storage_modules.py    # File storage operations
│       ├── vectorstore_modules.py # Vector search implementations
│       └── langchain_firestore.py # LangChain Firestore integration
├── tests/                        # Test suite
├── gcloud-keys.json             # Google Cloud credentials (git-ignored)
├── pyproject.toml               # Project dependencies
└── README.md                    # This file
```

## Key Features

### Document Intelligence
- PDF text extraction with OCR fallback
- Semantic chunking and embedding
- Multi-document context retrieval

### Structured Extraction
- Automated extraction of legal entities (parties, claims, damages)
- Timeline reconstruction from events
- Deadline tracking

### Conversation Management
- Persistent conversation state
- Thread-based session management
- Message streaming support

### Multi-Model Support
- OpenAI (GPT-4, GPT-3.5)
- Anthropic Claude
- Google Gemini
- Configurable per session

## Development

### Adding New Tools

```python
from langchain.tools import tool

@tool
def my_custom_tool(query: str) -> str:
    """Tool description for the LLM"""
    # Implementation
    return result

# Add to agent initialization
agent = Agent(tools=[..., my_custom_tool], ...)
```

### Extending Database Schema

1. Create migration in Supabase dashboard
2. Update `basemodels.py` with new Pydantic models
3. Add methods to `SupabaseManager` in `database_modules.py`
4. Update tests

### Custom Vector Stores

Implement the vector store interface:

```python
class CustomVectorStore:
    def add_documents(self, documents: List[Document]):
        pass
    
    def similarity_search(self, query: str, k: int) -> List[Document]:
        pass
```

## Performance Considerations

- **Token Management**: Text is chunked to fit within model context windows (tracked with tiktoken)
- **Caching**: Vector embeddings are cached to reduce computation
- **Batch Operations**: Document processing supports batch uploads
- **Connection Pooling**: Database connections use Supabase's built-in pooling

## Security

- All file uploads are scoped to user accounts
- Row-level security (RLS) policies on Supabase tables
- Service role keys kept in environment variables
- JWT-based authentication for API access

## Troubleshooting

### Common Issues

**Checkpoint not saving**
- Verify `DATABASE_URL` is correct PostgreSQL connection string
- Check Supabase connection pooler settings (use transaction mode)

**Documents not retrieving**
- Ensure vector store is initialized with correct collection name
- Verify embeddings model matches between indexing and retrieval

**File upload fails**
- Check Supabase storage bucket permissions
- Verify file size limits in Supabase dashboard

## License

[Your License]

## Contributing

[Contributing guidelines]
