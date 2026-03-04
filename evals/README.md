# Evals Module

Evaluation framework for benchmarking agent performance across three agent configurations.

## Overview

The evals module runs test datasets against the agent, collects responses with token/time metrics, and scores them using DeepEval (LLM-as-Judge) metrics.

## Structure

```
evals/
├── collect.py                 # CLI: run agent against test datasets
├── evaluate.py                # CLI: run DeepEval metrics on collected results
└── src/evals/
    ├── collect_module.py      # CollectAgentResult: agent initialization and execution
    ├── dataset_module.py      # Dataset: GCS-backed dataset loading and result storage
    ├── evaluate_module.py     # Evaluater: DeepEval metrics runner
    ├── langsmith_module.py    # LangSmith tracing integration
    ├── lovdata_module.py      # Norwegian legal database integration
    ├── models.py              # DatasetPayload, Session, ConversationTurn, GatheredResultPayload
    └── utils.py               # DocumentHandler, ParsedAttachment, ParsedEmail
```

## CLI Usage

### Step 1: Collect results

```bash
uv run --package evals python evals/collect.py \
  -d <dataset> \
  -m <model> \
  -a <agent-type> \
  -n <runs>
```

**Arguments:**

| Flag | Description | Options |
|------|-------------|---------|
| `-d` | Dataset name | `test`, `THRD-2021-163881`, `TOSL-2024-103311`, `TOSL-2024-125319` |
| `-m` | LLM model | `google_gemini-2.5-flash`, `google_gemini-2.5-pro`, `openai_gpt-4.0`, `openai_gpt-4o-mini` |
| `-a` | Agent type | `custom`, `baseline`, `baseline_rag` |
| `-n` | Number of runs | integer (default: 1) |
| `--skip-embedding` | Skip embedding to vector store | flag |
| `--skip-storage` | Skip saving to Supabase Storage | flag |

### Step 2: Evaluate results

```bash
uv run --package evals python evals/evaluate.py \
  -d <dataset> \
  -m <model> \
  -t <throttle> \
  -c <concurrent>
```

**Arguments:**

| Flag | Description | Default |
|------|-------------|---------|
| `-d` | Dataset name | required |
| `-m` | LLM model to evaluate (optional, defaults to all in dataset) | — |
| `-t` | Throttle: max evaluations per minute | `10` |
| `-c` | Max concurrent evaluations | `1` |
| `--threshold` | Metric pass threshold | `0.5` |

## Agent Configurations

Three agent configurations are benchmarked:

| Configuration | Tools |
|---------------|-------|
| `custom` | All tools: web search, file read, project RAG, Norwegian laws, file listing |
| `baseline` | Web search + Norwegian laws only |
| `baseline_rag` | Web search + Norwegian laws + project attachment RAG |

## Metrics

Evaluation uses DeepEval with:
- **Legal Accuracy** (GEval): Domain-specific legal correctness
- **Answer Relevancy**: Response relevance to the question

Results and metrics are stored in Google Cloud Storage (`master-thesis-prod` bucket).

## Environment Variables

```bash
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_APPLICATION_CREDENTIALS=./gcloud-keys.json
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_DB_URL=postgresql://...
GOOGLE_API_KEY=your_google_api_key
OPENAI_API_KEY=your_openai_key
TAVILY_API_KEY=your_tavily_key
```
