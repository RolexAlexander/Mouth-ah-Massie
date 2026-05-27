# Deep Research ADK

A multi-agent deep research system built on Google ADK. Designed to compete with OpenAI Deep Research and Gemini Deep Research on the axes those products are weak: **structured auditable state**, **explicit termination contracts**, **source-quality stratification**, and a **two-layer report** that separates evidence from interpretation.

## What's different from a typical Manager/Planner/Researcher/Writer setup

1. **No `/tmp` markdown handoffs.** Agents communicate through a typed SQLite-backed workspace. The Manager never has to remember a directory path.
2. **Parallel-ready Researchers.** Each Researcher handles one sub-question with an isolated tool loop. The Manager delegates them through `AgentTool`, so adding parallelism is a config knob away.
3. **Critic as a continuous signal.** Every Finding gets scored as it lands, not at the end. Bad findings trigger re-research before the Writer ever sees them.
4. **Explicit termination rubric.** "Until satisfied" is replaced with a numeric contract: every sub-question has ≥N sources of tier ≤T, or budget exhausted. No vibe-based stopping.
5. **Source-quality stratification.** URLs are auto-classified into tiers (peer-reviewed → official → major news → industry → unverified). The Critic rejects findings that rest entirely on weak sources.
6. **Two-layer report.** Evidence Layer (verbatim claims + citations) is separate from Interpretation Layer (analyst voice). Auditable.
7. **Strong models where it counts.** Manager/Planner/Writer = `gemini-2.5-pro`. Researcher/Critic = `gemini-2.5-flash`. The previous setup had Flash-Lite making the hardest decisions; this inverts that.

## Architecture

```
                 ┌─────────────────┐
   user input    │     Manager     │  termination rubric, gap detection
   ─────────────▶│   (gemini-pro)  │
                 └────────┬────────┘
                          │ delegates via AgentTool
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
  ┌─────────┐       ┌───────────┐      ┌─────────┐
  │ Planner │       │Researcher │      │ Writer  │
  │ (pro)   │       │ (flash)   │      │ (pro)   │
  └────┬────┘       └─────┬─────┘      └────┬────┘
       │                  │                  │
       │                  ▼                  │
       │            ┌──────────┐             │
       │            │  Critic  │             │
       │            │ (flash)  │             │
       │            └────┬─────┘             │
       │                 │                   │
       ▼                 ▼                   ▼
  ┌────────────────────────────────────────────────┐
  │           Workspace (SQLite, typed)            │
  │  brief | plan | findings | critiques | report  │
  └────────────────────────────────────────────────┘

         ┌──────────────────────────────────┐
         │      Tools (native, not MCP)      │
         │  SearXNG search │ trafilatura     │
         └──────────────────────────────────┘
```

## Prerequisites

1. **Python 3.11+**
2. **A Google AI Studio API key** — https://aistudio.google.com/app/apikey
3. **A running SearXNG instance** for web search. Quick start:

   ```bash
   docker run -d --name searxng -p 8081:8080 searxng/searxng
   ```

   Then enable the JSON format in SearXNG's settings — see [SearXNG docs](https://docs.searxng.org/). On most images you edit `/etc/searxng/settings.yml` (inside the container) and add `json` to `search.formats`.

## Setup

```bash
# 1. Get the project
cd deep_research_adk

# 2. Create venv and install
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

# 3. Configure
cp .env.example .env
# Edit .env — at minimum set GOOGLE_API_KEY and confirm SEARXNG_BASE_URL
```

## Run it

### Option A — terminal CLI (recommended for first run)

```bash
python run_local.py "What are the regulatory implications of Guyana's first-oil revenue for the Bank of Guyana's monetary policy stance?"
```

You'll see streaming tool-call lines as the Manager delegates to the team, then the final report.

### Option B — ADK web UI

```bash
adk web
```

This opens the ADK web inspector. Pick the `deep_research` app and chat with the Manager directly.

### Option C — live workspace UI (browser)

Watch the workspace fill in as the agents run. Read-only, auto-refreshes every 2s.

```bash
python dr_ui.py
# open http://localhost:8765
```

Left pane lists every project in the SQLite DB (title, round, finding/critique counts, draft/final badges). Right pane shows the brief, plan, every sub-question with status color-coding, the latest finding (answer, key facts, sources with tier pills + links, confidence), the latest critique verdict, and the draft or final report when present. Run this in one terminal and `run_local.py` in another.

### Option D — inspect a past project from the CLI

Every run leaves a persistent workspace. To re-read it without the UI:

```bash
python run_local.py --inspect <project_id>
```

You'll see the printed `project_id` in the streaming logs when the Manager calls `create_project`.

## What to try first

Start with a question that has a clear answer and decent web coverage so you can sanity-check quality:

- *"What did the IMF Article IV consultation say about Guyana in 2024 and what risks did it flag?"*
- *"Compare ERPNext and Odoo for a 200-employee manufacturing deployment — feature parity, total cost of ownership, and hosting trade-offs."*
- *"What is the current state of CARICOM caselaw on data protection, and how does it compare to GDPR's main provisions?"*

Then try a harder one where the structured workspace earns its keep:

- *"Build a comparative analysis of Guyana's tax treaty network against five peer petrostates. Identify gaps that affect inbound investment from the EU."*

## Tuning knobs (in `.env`)

| Variable | Default | Notes |
|---|---|---|
| `DR_MAX_SUBQUESTIONS` | 8 | Planner is capped here. Bigger = more thorough, slower. |
| `DR_MAX_RESEARCH_ROUNDS` | 3 | Hard ceiling on critique-rework loops. |
| `DR_MAX_PARALLEL_RESEARCHERS` | 4 | Currently a soft hint to the Manager; true parallelism is a v2 improvement. |
| `DR_MAX_SEARCHES_PER_SUBQUESTION` | 6 | Per-Researcher search budget. |
| `DR_MIN_SOURCES_PER_SUBQUESTION` | 2 | Critic rejects findings below this. |
| `DR_MIN_SOURCE_TIER` | 3 | Tier ceiling for "majority of sources." |

## File map

```
deep_research_adk/
├── deep_research/
│   ├── agent.py            ← root_agent for `adk run` / `adk web`
│   ├── config.py           ← env-loaded settings
│   ├── workspace.py        ← SQLite store, typed accessors
│   ├── schemas.py          ← pydantic models (Plan, Finding, Critique...)
│   ├── source_quality.py   ← URL → SourceTier heuristic
│   ├── prompts.py          ← all agent instructions in one place
│   └── agents/
│       ├── manager.py      ← orchestrator with termination rubric
│       ├── planner.py
│       ├── researcher.py
│       ├── critic.py
│       └── writer.py
├── tools/
│   ├── search_tools.py     ← SearXNG + trafilatura
│   └── workspace_tools.py  ← typed ADK-callable workspace ops
├── run_local.py            ← CLI runner
├── dr_ui.py                ← FastAPI live workspace UI (read-only)
├── pyproject.toml
├── .env.example
├── .gitignore              ← ignores __pycache__, .env, *.db, venvs, IDE junk
└── README.md
```

## Known sharp edges

- **Parallel researcher execution.** The current Manager delegates Researchers sequentially via `AgentTool` because that's the simplest reliable pattern in ADK. To run true parallel Researchers (the Anthropic pattern that gives the big quality jump), the next iteration should use ADK's `ParallelAgent` or a custom orchestration loop that fans out `runner.run_async` calls on worker sub-questions.
- **Source classification is heuristic.** Add domain patterns in `source_quality.py` for your regional/industry sources (the file already has stubs for Guyanese outlets — extend it).
- **No private corpus connector yet.** The schema has `private_corpus_paths` and the brief supports it; wiring this to a local vector store (Chroma / Qdrant) is the natural next addition and would be your strongest differentiator vs OpenAI/Google.
- **SearXNG JSON format must be explicitly enabled** in the container's settings. If you get empty search results, that's the first thing to check.

## License

MIT.
