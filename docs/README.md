# EvidentFit Documentation

Welcome to the EvidentFit docs. This index helps you find the right guide quickly and keeps scope clear across public vs. internal docs.

## Getting started
- Quick start: see the root `README.md` for local dev and repo layout
- API quick start: `api/README.md`
- Web quick start: `web/evidentfit-web/README.md`

## What EvidentFit is
- Platform blueprint: `docs/EvidentFit_Platform_Blueprint.md`
- Methodology (internal): `docs/METHODOLOGY.md`
- Methodology (public site): `docs/METHODOLOGY_PUBLIC.md`
  - Note: The public doc is audience-facing and higher-level; the internal doc covers process, data, and limitations for maintainers.

## Architecture, models, and costs
- Model selection: `docs/MODEL_SELECTION.md`
- Cost management (detailed): `docs/COST_MANAGEMENT.md`
- Cost summary (exec): `docs/COST_SUMMARY.md`

## Deployment & operations
- Docker & Azure Container Apps: `docs/DOCKER_DEPLOYMENT.md`
- Key Vault migration (secrets): `docs/KEYVAULT_MIGRATION.md`
- Container App config: `deploy/container-app-config.yaml`
- Deployment script: `deploy/deploy-to-aca.ps1`

## Agents (research pipeline & banking)
- Ingest overview: `agents/ingest/README.md`
  - get_papers (technical): `agents/ingest/get_papers/README.md`
- Paper processor (Agent B): `agents/paper_processor/README.md`
- Banking (Agent C): Level1/Level2/Level3
  - Initialize (L1/L2): `agents/banking/run.py`
  - Compile L3 rules: `agents/banking/level3/run.py`
  - CLI: `agents/banking/cli.py` (level1 | level2 | level3)
- Summarizer (Agent D): `agents/summarize/run.py` (reads Level 1 grades)

## API and web
- API service: `api/README.md`
- Web app: `web/evidentfit-web/README.md`

## Testing
- Tests overview and usage: `tests/README.md`

## Data directories (local)
- Ingest runs: `data/ingest/runs/`
- Full text store: `data/fulltext_store/`
- Paper processor outputs: `data/paper_processor/`

## Conventions
- Secrets: use Azure Key Vault or env vars; never commit secrets
- LLM usage: Azure AI Foundry Project endpoint only; use header `api-key` and append `?api-version=2024-05-01-preview`
- Evidence and citations: cite-only-retrieved sources; never invent identifiers

## Documentation style guide
- Use H1 once per file; start sections with H2/H3
- Add a short “Scope note” at top when similar docs exist (public vs internal)
- Prefer linking to an existing doc over duplicating content
- Include a “Quick start” section in service READMEs (API, Web, Agents)
- Keep commands copy-pasteable; avoid machine-specific paths

If something’s missing or duplicated, prefer consolidating into the nearest guide above and link to it here rather than creating a new standalone doc.
