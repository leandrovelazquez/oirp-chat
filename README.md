# OIRP-chat

A semantic-layer-grounded chat agent for institutional-research questions about Carleton University. Portfolio demo.

The bot answers questions about student engagement, retention, and enrolment using **only** verified values from a curated semantic layer — every numerical claim is traced to a specific source PDF and page, and the bot **refuses to answer** when a value isn't in its verified store. No hallucinated percentages.

> **Disclaimer.** Unaffiliated portfolio project. Not endorsed by Carleton University or its Office of Institutional Research and Planning (OIRP). All data is extracted from publicly published OIRP and Carleton sources, with citations.

---

## Two views, one backend

The project ships with two web UIs sharing the same agent:

- **`/`** — engineering view. Shows confidence badges, tool-call traces, and the loaded-semantic-layer table. For technical demos and debugging.
- **`/oirp`** — institutional view. OIRP-styled mock page with the chat as a side panel. For pitching what this could look like in production.

Both call the same `OIRPAgent.chat()`, the same Claude model, and the same verified store.

---

## What's in the box

| Layer | What it is | Built? |
|---|---|---|
| **Semantic layer** | 6 KPI markdown files with frontmatter, prose, and verified-value JSON blocks | ✅ 73 records across 6 KPIs |
| **Agent** | Manual tool-use loop with prompt caching against Claude Sonnet 4.6 | ✅ |
| **Tools** | `get_kpi_value`, `search_methodology`, `list_kpis` | ✅ |
| **Confidence tracking** | Per-turn classification: HIGH (verified lookup), MEDIUM (methodology/synthesis), LOW (refused) | ✅ |
| **Web server** | FastAPI + uvicorn serving both UIs | ✅ |
| **Data pipeline** | TOML-driven download → pdfplumber extraction → LLM-assisted KPI drafter | ✅ |
| **Eval suite** | 25 hand-written questions across confidence tiers | ✅ scaffold; runner pending |

---

## Why it's interesting (the architecture story)

Most "RAG over PDFs" demos fail in the same way: the LLM gets handed source documents at query time and produces plausible-looking answers that are subtly wrong. Schema is not the same thing as business context. "First-year retention" has at least four definitions at OIRP. "Enrolment" has at least six counting bases. A naive bot picks one and confidently misleads.

This project takes a different shape. Three layers, each with a clear role:

```
                 ┌──────────────────────────────────────┐
                 │  semantic_layer/kpis/*.md            │
                 │   • KPI definitions, calculations    │
                 │   • Synonyms & disambiguation        │
                 │   • Verified values + page citations │
                 │   • Per-KPI confidence guidance      │
                 └──────────────┬───────────────────────┘
                                │  (loaded once at startup)
                                ▼
                 ┌──────────────────────────────────────┐
                 │  Claude Sonnet 4.6 (agent loop)      │
                 │   tools: get_kpi_value,              │
                 │          search_methodology,         │
                 │          list_kpis                   │
                 │   prompt-cached (~22k tokens)        │
                 └──────────────┬───────────────────────┘
                                │
                                ▼
                 ┌──────────────────────────────────────┐
                 │  FastAPI ⇄ web UIs (/  and  /oirp)   │
                 │   confidence badges, tool traces     │
                 └──────────────────────────────────────┘
```

The agent never sees raw PDFs. It queries a structured store of human-curated, source-cited records via tools. When `get_kpi_value` returns nothing for a specific year/cohort/dimension, the agent **refuses to guess** and points the user to the correct OIRP source. That refusal behavior is the actual product.

### Closing the loop: the LLM drafter

Hand-curating verified-value blocks doesn't scale past a handful of KPIs. So the project includes a `scripts/draft_kpi_values.py` drafter that reads extracted PDF text + tables, calls Claude with the existing KPI schemas as context, and proposes new verified-value records — each grounded in a verbatim quote from the source page. After the proposals come back, a post-hoc validator string-matches every quote against the page's extracted text, flagging hallucinated quotes loudly.

Pipeline:

```
sources.toml                                  ← editable manifest
   │
   ▼
download_sources.py        →  data/pdfs/      ← gitignored binaries
   │
   ▼
extract_pdfs.py            →  data/extracted/ ← committed JSON
   │
   ▼
draft_kpi_values.py        →  data/proposed/  ← LLM proposals
   │                                            with quote validation
   ▼  (human review + copy-paste)
semantic_layer/kpis/       ← canonical store
   │
   ▼
oirp_agent (chat)          ← cited answers,
                             refuses on gaps
```

This split — deterministic extraction below, LLM drafting in the middle, human review at the top — is the part recruiters notice. The expensive judgment (which numbers to trust, when to refuse, how to interpret cohort definitions) lives in human-reviewed markdown. The cheap mechanical work is automated.

**Measured outcome:** the drafter run on the 2023 NSSE Summary produced 10 proposals, all 10 with verbatim-quote-validated grounding (100% citation accuracy). Across 4 PDFs the drafter expanded the verified store from 60 to 73 records, ~16 minutes of human review per PDF.

---

## What's in the semantic layer (today)

| KPI | Source | Records | Status |
|---|---|---|---|
| `overall_experience_rating` | NSSE 2023 Figure 1 | 8 | ✅ verified |
| `would_choose_same_institution` | NSSE 2023 Figure 4 | 8 | ✅ verified |
| `nsse_engagement_indicators` | NSSE 2023 Table 3 + breakouts | 15 | ✅ verified |
| `nsse_high_impact_practices` | NSSE 2023 Tables 4–6 | 26 | ✅ verified |
| `first_year_retention_rate` | OIRP Databook + Annual Report + Operating Budgets | 6 | ⚠ partial |
| `undergraduate_enrolment_by_faculty` | NSSE-derived mix + Annual Report + Operating Budgets | 10 | ⚠ partial |

**Total: 73 verified records, 6 KPIs, 4 source PDFs.**

The two ⚠ partial files explicitly flag the values they don't yet have (recent year-over-year retention numbers, faculty-level headcounts) and instruct the agent to refuse and route users to CUDO Section E or the OIRP Databook rather than fabricate. That refusal *is* part of the product, not a limitation to apologize for.

---

## Quick demo

```bash
# Setup
git clone https://github.com/leandrovelazquez/oirp-chat
cd oirp-chat
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Run
uvicorn oirp_agent.web:app --reload
```

Open `http://localhost:8000/oirp` in your browser. Try:

- *"What percentage of first-year Carleton students rated their experience as good or excellent in 2023?"* → answers **74%** with source citation, HIGH confidence.
- *"Compare HIPs participation between 3-year and 4-year programs in 2023."* → answers with the cross-tab from Table 5, HIGH confidence.
- *"What was Carleton's first-year retention rate in 2022?"* → **refuses** and points you to CUDO Section E. LOW confidence by design.
- *"What's projected for international undergraduate intake by Fall 2025?"* → answers with the Operating Budget projection (86% drop from 2018 peak), MEDIUM confidence with appropriate framing.

Visit `http://localhost:8000/` for the engineering view that exposes tool-call tracing.

---

## Project layout

```
oirp-chat/
├── README.md                          this file
├── pyproject.toml
├── .gitignore
├── .env                               API key (gitignored)
│
├── semantic_layer/
│   ├── base_prompt.md                 system prompt with {{KPI_DOCUMENTS}} placeholder
│   └── kpis/                          ── the actual ground truth ──
│       ├── overall_experience_rating.md
│       ├── would_choose_same_institution.md
│       ├── nsse_engagement_indicators.md
│       ├── nsse_high_impact_practices.md
│       ├── first_year_retention_rate.md
│       └── undergraduate_enrolment_by_faculty.md
│
├── src/oirp_agent/
│   ├── __init__.py
│   ├── __main__.py                    CLI entry point
│   ├── web.py                         FastAPI server, /  and /oirp routes
│   ├── prompt_loader.py               markdown → KPIDocument parser
│   ├── kpi_store.py                   in-memory store with filter queries
│   ├── tools.py                       3 tool schemas + dispatcher
│   ├── confidence.py                  per-turn HIGH/MEDIUM/LOW classifier
│   └── agent.py                       manual tool-use loop with prompt caching
│
├── static/
│   ├── index.html                     /  — engineering view
│   └── oirp.html                      /oirp — OIRP-styled mock page
│
├── scripts/                           ── data pipeline ──
│   ├── sources.toml                   editable PDF manifest
│   ├── download_sources.py            fetch + sha256
│   ├── extract_pdfs.py                pdfplumber + pypdfium2
│   └── draft_kpi_values.py            LLM-assisted drafter with quote validation
│
├── data/
│   ├── pdfs/                          gitignored binaries + manifest.json
│   ├── extracted/                     committed JSON: pages, tables, meta
│   └── proposed/                      drafter review files (markdown)
│
└── evals/
    └── questions.yaml                 25-question eval scaffold
```

---

## Production-architecture story (the tier-3 swap)

The current demo is **tier 1 + 2** of a notional tier-3 architecture:

- **Tier 1 (done)**: hand-verified values from public PDFs, in JSON blocks within the KPI markdown files.
- **Tier 2 (done)**: prose methodology, definitions, and caveats searchable via keyword over the markdown files.
- **Tier 3 (architecture-ready)**: live connections to OIRP's warehouse and Data Cubes via a read-only role, swapping the static JSON store for parameterized SQL queries against the same schema. **The agent layer doesn't change.**

The boundary is the `KPIStore` interface in `src/oirp_agent/kpi_store.py`. Replace its implementation with SQL queries or HTTP calls to OIRP's Data Cubes API; everything above it stays identical. Same with `search_methodology` — swap the keyword scoring for pgvector + Voyage embeddings without touching `tools.py` or `agent.py`.

This separation is what would make the system shippable inside Carleton: the chat layer is institution-agnostic, the semantic layer encodes Carleton-specific business logic, and the data layer plugs into Carleton's warehouse. Three concerns, three swappable parts.

---

## Engineering decisions worth flagging

**Manual tool-use loop, not the SDK auto-runner.** `src/oirp_agent/agent.py` implements the tool-call loop by hand. More lines of code, but for a portfolio project the explicitness is the point — the architecture is visible to anyone reading the file.

**Prompt caching is enabled for the system prompt.** Without it, every chat turn would re-submit ~22k tokens of system prompt against the rate-limit budget. With cache_control on the system block, the prefix is written once per session and read on every subsequent turn — which keeps the project comfortably within Tier 1 ITPM limits and bills cached reads at 10% of normal cost.

**Two models, two jobs.** The chat agent uses Sonnet 4.6 (better judgment for open-ended user questions). The drafter uses Haiku 4.5 by default (cheaper, fine for structured tool-call drafting), with Sonnet as an override for harder PDFs. Mixing models per task is a deliberate cost-management choice, documented in the relevant files.

**JSON-in-markdown for verified values.** Each KPI file mixes human-readable prose, frontmatter metadata, and `​```json` fenced blocks of verified records. The prompt loader extracts the JSON for tool queries; the prose stays in the system prompt for the LLM to reason over. Single file per KPI, readable as a document, machine-queryable as a store.

**Quote-anchor validation in the drafter.** Every drafter-proposed value carries a verbatim ≥10-word excerpt from the source page. After Claude returns, a post-hoc validator string-matches every quote against the page's extracted text. Mismatches get flagged in bold red in the review file. This is the safety net: even if the LLM hallucinates, the validator catches it before any value reaches the verified store.

---

## Limitations (deliberate, named)

- **No live OIRP data connection.** The verified store is hand-extracted from public PDFs at a point in time. Recent absolute headcount and FTE values are flagged as "not yet extracted" and the agent refuses rather than guesses.
- **No PII concerns.** Public aggregate data only. A real OIRP integration would need column-level masking and small-cell suppression rules.
- **No conversation memory across sessions.** Each browser session has its own conversation history; nothing persists.
- **Methodology search is keyword-based, not semantic.** Production would use pgvector with Voyage or Cohere embeddings.
- **6 KPIs, not 60.** Coverage is intentionally narrow to demonstrate pattern depth over breadth. The structural typology — simple percentages, composite scores, multi-dimensional cross-tabs, behavioural rates with multi-variant disambiguation, headcount with counting-base ambiguity — is fully exercised.

---

## Cost & rate-limit notes

Running the full demo against your own Anthropic API key costs roughly:

- **Chat session (10 questions):** ~$0.05 against Sonnet 4.6 with prompt caching.
- **Single drafter run on a fresh PDF:** ~$0.02–$0.05 against Haiku 4.5, ~$0.10–$0.20 against Sonnet 4.6.
- **Full pipeline run (4 PDFs):** ~$0.30 against Sonnet 4.6.

A $5 minimum credit purchase on console.anthropic.com is enough to run, demo, and tinker with the project comfortably. Tier 1 rate limits (50k+ ITPM on Sonnet) are necessary for the chat agent's 22k-token system prompt; the free tier won't work.

---

## What inspired the architecture

The semantic-layer-with-verified-queries pattern is drawn directly from Fullscript's [Flurry post](https://builders.fullscript.com/posts/building-flurry-how-we-used-agents-to-democratize-data-access-at-fullscript). Two ideas transferred:

- *Schema is not business context.* An LLM with access to a database schema can write SQL all day, but it can't tell you what specific institutional terms mean — that mapping has to be documented somewhere structured. The OIRP-flavored equivalent: "first-year retention" has four published definitions and a careful semantic layer pins down which one applies.
- *Verified queries / verified values.* Rather than have the LLM regenerate logic on every call, pre-curate the canonical answers and have the agent look them up. Determinism over generation. The OIRP-flavored equivalent: each KPI file's `verified-values` JSON blocks.

What's *not* borrowed from Flurry: their warehouse connection (we don't have one), their PII detection (public data only), their conversation memory (single-session is enough for a demo), their full observability stack (a log file is enough at this scale).

---

## License

MIT. Use freely.
