# Repository Guidelines

## 🚨 MANDATORY ROLE ALIGNMENT

**CRITICAL: Select the persona that matches your assignment before editing.**

Always write all documentation, variable_names and code in english!
Keep everything neat and tidy. Do not produce more than asked.
Do not write code unless explicitly asked.

**FIRST STEP**: Read the relevant brief in `docs/personas/` (author one if it does not exist) and commit to a role:

1. **Pipeline Developer Agent** – Implement ingestion flows and CLI behaviour (`docs/personas/pipeline-developer.md`).
2. **Data Quality Reviewer Agent** – Verify dataset fidelity and regression coverage (`docs/personas/data-quality-reviewer.md`).
3. **Schema Rebaser Agent** – Align SQL/BigQuery contracts and tidy history (`docs/personas/schema-rebaser.md`).
4. **Release Merger Agent** – Resolve integration conflicts and validate release manifests (`docs/personas/release-merger.md`).
5. **Orchestration Planner Agent** – Design batch cadence, rate limits, and agent hand-offs (`docs/personas/orchestration-planner.md`).

## How to Choose Your Persona

- Extending suppliers, refactoring async code, or adding CLI flags → Pipeline Developer Agent.
- Reviewing output quality, schema diffs, or business rules → Data Quality Reviewer Agent.
- Cleaning commit history or updating BigQuery schemas → Schema Rebaser Agent.
- Preparing production releases or merging long-lived branches → Release Merger Agent.
- Planning concurrent backfills or orchestrating multi-agent runs → Orchestration Planner Agent.

## Project Context

Mission: deliver an agent-driven corporate intel platform that surpasses proff.no in freshness and insight.

This repository currently provides:
- **Runtime**: Python 3.11 CLI in `data/` coordinating BRREG and Enin sources via async workers.
- **Data Fabric**: BigQuery datasets (`brreg.*`, `enin.*`) with merge helpers in `modules.py`.
- **Observability**: Supplier logs under `logfiles/` for tracing batch health.
- **Secrets**: Environment variables in `.env`, pointing to local JSON keys (never commit secrets).

```
├── AGENTS.md
├── data
│   ├── DATABASE_STRUCTURE.txt
│   ├── main.py
│   ├── requirements.in
│   ├── requirements.txt
│   └── src
│       └── modules.py
└── ui
    ├── main.py
    ├── pages
    │   └── company_dashboard.py
    └── requirements.in
```

## Core Principles (All Personas)

1. **STUDY FIRST**: Review `modules.py`, recent commits, and `DATABASE STRUCTURE.txt` before altering flows.
2. **OPTIMISE SIGNAL**: Remove stale paths and shrink payloads to keep automation responsive.
3. **FOLLOW PATTERNS**: Reuse `get_items`, `fetch_single`, and BigQuery merge templates.
4. **RUN EVERYTHING**: Execute the relevant CLI scenario or `pytest` suite to verify behaviour.
5. **COMMIT WITH CONTEXT**: State scope, dataset impact, and agent approvals in each commit message.

## File Structure Reference

Treat `data/` as the ingestion layer, `logfiles/` as the operational record, and the repository root as the control plane for configuration. Expand deliberately as new agent workflows come online.
