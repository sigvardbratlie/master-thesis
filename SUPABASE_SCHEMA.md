# Supabase Database Schema Design

## Hvorfor ikke alt i én tabell?

En enkelt `chat_history` tabell med alt ville gi:
- ❌ Massive duplisering av data (hver rad må ha all metadata)
- ❌ Vanskelig å oppdatere (må oppdatere mange rader når noe endres)
- ❌ Ineffektive queries (må scanne store mengder data)
- ❌ Data inkonsistens (samme info lagres flere steder)
- ❌ Vanskelig å skalere

## Anbefalt Normalisert Struktur

### 1. `users` - Brukere
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_user_id TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    name TEXT,
    picture TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_google_id ON users(google_user_id);
```

### 2. `projects` - Prosjekter/Saker
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    factsheet JSONB NOT NULL, -- Lagrer hele FactSheet objektet
    agent_type TEXT CHECK (agent_type IN ('fast', 'expert')),
    llm_provider TEXT CHECK (llm_provider IN ('google', 'openai', 'claude')),
    last_updated_session_id UUID, -- FK til sessions
    last_updated_query_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_projects_updated_at ON projects(updated_at DESC);
```

### 3. `sessions` - Chat-sesjoner
```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT 'Ny samtale',
    agent_type TEXT CHECK (agent_type IN ('fast', 'expert')),
    llm_provider TEXT CHECK (llm_provider IN ('google', 'openai', 'claude')),
    last_query_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_project_id ON sessions(project_id);
CREATE INDEX idx_sessions_updated_at ON sessions(updated_at DESC);
```

### 4. `events` - Chat events/meldinger
```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('human', 'ai', 'system', 'tool')),
    data JSONB NOT NULL, -- LangChain message objektet
    sequence_number INTEGER NOT NULL, -- For å beholde rekkefølge
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, sequence_number)
);

CREATE INDEX idx_events_session_id ON events(session_id);
CREATE INDEX idx_events_session_sequence ON events(session_id, sequence_number);
```

### 5. `attachments` - Vedlegg metadata
```sql
CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL UNIQUE, -- Brukes for referanse i factsheet
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    storage_path TEXT NOT NULL, -- Path i Supabase Storage
    extracted_data JSONB, -- AttachmentExtracted objektet
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_attachments_session_id ON attachments(session_id);
CREATE INDEX idx_attachments_project_id ON attachments(project_id);
CREATE INDEX idx_attachments_file_id ON attachments(file_id);
```

### 6. `checkpoints` - LangGraph checkpoints
```sql
CREATE TABLE checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id UUID NOT NULL, -- Session ID
    checkpoint_id TEXT NOT NULL,
    checkpoint_data JSONB NOT NULL,
    checkpoint_type TEXT NOT NULL,
    metadata JSONB,
    parent_checkpoint_id TEXT,
    custom_project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, thread_id, checkpoint_id)
);

CREATE INDEX idx_checkpoints_user_thread ON checkpoints(user_id, thread_id);
CREATE INDEX idx_checkpoints_thread_id ON checkpoints(thread_id);
```

### 7. `checkpoint_writes` - LangGraph pending writes
```sql
CREATE TABLE checkpoint_writes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id UUID NOT NULL,
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    value_data JSONB NOT NULL,
    value_type TEXT NOT NULL,
    idx INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_writes_user_thread_checkpoint ON checkpoint_writes(user_id, thread_id, checkpoint_id);
CREATE INDEX idx_writes_task ON checkpoint_writes(task_id);
```

### 8. `vector_embeddings` - For RAG (Supabase pgvector)
```sql
-- Må installere pgvector extension først
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE vector_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id TEXT NOT NULL REFERENCES attachments(file_id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    query_id TEXT,
    content TEXT NOT NULL,
    embedding vector(768), -- Dimensjon avhengig av embedding model
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_vector_embeddings_file_id ON vector_embeddings(file_id);
CREATE INDEX idx_vector_embeddings_session_id ON vector_embeddings(session_id);
-- Vector similarity search index
CREATE INDEX idx_vector_embeddings_embedding ON vector_embeddings 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

## Storage (Supabase Storage)

For faktiske filer (PDF, DOCX, etc.):
- **Bucket**: `attachments`
- **Path structure**: `{user_id}/{session_id}/{file_id}` eller `{user_id}/{project_id}/{file_id}`
- Bruk Supabase Storage API for upload/download

## Fordeler med denne strukturen

✅ **Normalisert**: Ingen duplisering, data lagres kun én gang  
✅ **Effektive queries**: Indexer på vanlige søkefelt  
✅ **Referential integrity**: Foreign keys sikrer konsistens  
✅ **Skalerbar**: Enkelt å legge til nye felter/tabeller  
✅ **Fleksibel**: JSONB for komplekse strukturer (factsheet, events)  
✅ **Vector search**: pgvector for embeddings i samme database  
✅ **Alt på ett sted**: Ingen behov for GCS eller separate services  

## Migrasjon fra Firestore

1. **Eksporter data** fra Firestore til JSON
2. **Transform** data til relasjonell struktur
3. **Import** til Supabase med riktige foreign keys
4. **Migrer filer** fra GCS til Supabase Storage
5. **Oppdater kode** til å bruke Supabase client

## Eksempel queries

```sql
-- Hent alle sessions for en bruker
SELECT s.*, COUNT(e.id) as event_count
FROM sessions s
LEFT JOIN events e ON e.session_id = s.id
WHERE s.user_id = $1
GROUP BY s.id
ORDER BY s.updated_at DESC;

-- Hent full session med events
SELECT 
    s.*,
    json_agg(e.data ORDER BY e.sequence_number) as events,
    json_agg(a.*) FILTER (WHERE a.id IS NOT NULL) as attachments
FROM sessions s
LEFT JOIN events e ON e.session_id = s.id
LEFT JOIN attachments a ON a.session_id = s.id
WHERE s.id = $1
GROUP BY s.id;

-- Vector similarity search
SELECT 
    ve.content,
    ve.metadata,
    1 - (ve.embedding <=> $1::vector) as similarity
FROM vector_embeddings ve
WHERE ve.session_id = $2
ORDER BY ve.embedding <=> $1::vector
LIMIT 5;
```
