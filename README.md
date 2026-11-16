# OIRP-chat

A semantic-layer-grounded chat agent for institutional-research questions about Carleton University. Portfolio demo.

The bot answers questions about student engagement, retention, enrolment, and admissions from two governed sources, and never from memory:

- **Published layer**: real, hand-verified values from Carleton's public PDFs. Every number is traced to a source PDF and page, and the bot **refuses to answer** when a value isn't in the verified store.
- **Synthetic warehouse**: **generated demo data** in a DuckDB warehouse whose tables, columns, grain, measures, and MDX calculated members mirror an institutional-research data warehouse's Retention, Enrolment, and Admissions cubes. The agent asks for measures by dimension through a governed query tool. It cannot write SQL, and every number it reports from here is labelled synthetic.

> **Disclaimer.** Unaffiliated portfolio project. Not endorsed by Carleton University or its Office of Institutional Research and Planning (OIRP). All data is extracted from publicly published OIRP and Carleton sources, with citations.

---

## Two views, one backend

The project ships with two web UIs sharing the same agent:

- **`/`** — engineering view. Shows confidence badges, tool-call traces, and the loaded-semantic-layer table. For technical demos and debugging.
- **`/oirp`** — institutional view. A "What would you like to know?" home page in a calm, frosted-glass style: ask in your own words and each answer arrives as a card labelled with its source (published or synthetic), its confidence, and a "How this was answered" trace. A six-step student journey (Apply → Graduated) across the top starts a question from any step and lights up as answers use it. `/oirp?q=...` asks a question straight from a link.
  - **While it works,** the card lists each step as it happens: the cube and measures it is asking for, how many rows came back and how many were hidden as small cells, then the number check (and a rewrite, if one was needed). The answer's text isn't streamed: it appears whole, once its numbers have passed the check.
  - **When it can't answer,** the card says why (not in the data · about one person · stopped by a rule · needs a choice · couldn't verify a number) and offers one to three questions it *can* answer, as buttons. The assistant marks this with a short `<cannot_answer reason="…">` block the server reads off and never shows; the code adds `unverified`, and `limit` when the tool budget runs out or every cell came back suppressed.
  - **Preliminary numbers** are marked. Each cube model can list members whose numbers can still change (Fall 2026, which has no final count yet; retention outcomes observed in 2026/27). The engine flags the matching rows in the same query, the table tags them and the card shows a "Preliminary" pill.
  - **Charts** sit above the table when the result's shape calls for one: a line for a trend over cohorts, terms or intakes (a preliminary point is hollow, on a dashed segment), bars for a breakdown of up to twelve groups, and the admissions funnel in funnel order. The server picks the chart from the result's shape and the cube's `roles`, and the chart draws the same rows as the table, labelled with the same display strings. One series in the page's red, with a hover and keyboard crosshair on lines.
  - **"Ask next" buttons** follow each warehouse answer: "Break this down by faculty", "Same for the 2023 cohort", "Show the trend over the last five cohorts". They're worked out from the last query and the cube's `roles` ([followups.py](src/oirp_agent/followups.py)), not written by the model, so they always fit the cube.
  - **A guided tour** ("Take the tour", or `/oirp?tour`) asks five questions in a fresh conversation, one capability each: a published figure with its page, a warehouse query with its SQL, a follow-up, small-cell suppression, and a refusal to compare synthetic with published numbers. Each comes with a note on what to look for, and the presenter moves on with Next.

Both call the same `OIRPAgent.chat()`, the same Claude model, and the same verified store.

---

## What's in the box

| Layer | What it is | Built? |
|---|---|---|
| **Semantic layer: published** | 6 KPI markdown files with frontmatter, prose, and verified-value JSON blocks | ✅ 73 records across 6 KPIs |
| **Semantic layer: warehouse** | 3 cube files (Retention, Enrolment, Admissions): grain, answer recipes, and a JSON cube model of measure groups, measures, MDX-ported calculated members, and dimension hierarchies | ✅ |
| **Synthetic warehouse** | Seeded generator → DuckDB: `URET_FACT`, `STDCOUNT`, `STDACADUNIT`, `ADM_FACT`, and ~70 dimension tables; one simulated population across all three stars | ✅ ~4.4M fact rows |
| **Metric engine** | Validates names against the cube model, compiles parameterised SQL, enforces counting rules, suppresses small cells, reports freshness | ✅ 23 tests |
| **Agent** | Manual tool-use loop with prompt caching against Claude Sonnet 5.5 (medium effort) | ✅ |
| **Tools** | `get_kpi_value`, `search_methodology`, `list_kpis`, `query_metric`, `describe_cube` | ✅ |
| **Confidence tracking** | Per-turn classification: HIGH (verified lookup or governed query), MEDIUM (methodology/discovery), LOW (refused/no value), plus per-turn source labels (published / synthetic) | ✅ |
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
                 │  Claude Sonnet 5.5 (agent loop)      │
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

## The synthetic warehouse

The published layer can say what Carleton *published*. It can't answer "first-year retention by entry faculty, international vs domestic, for the last five cohorts", because nobody publishes that. A real institutional-research warehouse can. So the demo carries a fake one.

**What's mirrored from the real warehouse:**

- Table and column names: the full 84-column `URET_FACT`, 26-column `STDCOUNT`, 72-column `ADM_FACT`, and the `URET_*` / `ADM_*` dimension tables.
- Grain:

  | Table | One row per |
  |---|---|
  | `URET_FACT` | student × academic year since entry ("Years After") |
  | `STDCOUNT` | student × term × count date |
  | `ADM_FACT` | application, weighted per applicant |

- Each cube's measures and their aggregations.
- The cubes' MDX calculated members, ported as-is, for example `% Continuing = [Continuing]/[Cohort]` and `% Registered of Confirmed`.

**What's synthetic:** every value. A seeded simulation generates applicants. Registrants become new students in `STDCOUNT` and cohort members in `URET_FACT`, and they progress, switch units, stop out, or graduate year by year. Because all three stars share one population, the numbers reconcile across cubes: 2024's `Registered` = the 2024 `Cohort` at Years After 0 = new undergraduates in Fall 2024.

**What the engine enforces:**

| Guard | Why it exists |
|---|---|
| Names only from the cube model; values are bound parameters | The agent can't reach a column or expression nobody declared |
| Required single-valued dimensions (`Years After`, `Time`, `Count Date`, `Application Year`) | Stops two counting bases being silently summed, e.g. fall + winter headcount, or every year of a cohort |
| Reported defaults (`Count Date` → official count) | The answer can state its counting base |
| Small-cell suppression (< 10 distinct people) | What a real warehouse needs before anyone sees a cross-tab |
| Load-log freshness (`data_as_of`, `stale`) | The retention star is deliberately loaded three weeks behind, so the agent has to caveat it, the way a real star falls behind when its pipeline isn't scheduled |

The warehouse builds automatically on first run (about 1 minute), or explicitly with `python -m oirp_agent.synthetic_warehouse --force`.

---

## The model never supplies a number

Asking the model not to invent numbers isn't enough, so three things in [`numbers.py`](src/oirp_agent/numbers.py) enforce it:

1. **Tools format their own numbers.** Every warehouse value carries a display string (`90.7%`, `1,513`, `fewer than 10`). The model is sent *only* those strings and is told to copy them. It never rounds or converts a value itself.
2. **Every number in an answer is checked.** Before an answer is shown, each number in it must match a number from a tool result in the conversation, the verified published layer in the system prompt, or one the user typed. If one doesn't (typically a difference or gap the model worked out itself), the model gets one rewrite with feedback naming the number. If the rewrite still fails, the answer is flagged on screen with the numbers that couldn't be traced. The failed draft and the feedback are dropped from history.
   - Not checked, because they're context rather than measurements: small whole numbers (0–10), years and year spans, and numbers inside identifiers like `nsse_2023_summary.pdf`.
   - Rounding a tool's number (86.94 → 87) is allowed. Arithmetic is not: a change or a share comes from **`compare_metric`**, which runs the governed queries and works out the difference ("+2.6 pp" for a rate, "−161 / −0.8%" for a count) or each group's share of a separately queried total, as display strings. The model copies them, so the answer is right the first time instead of after a rewrite. Shares of a rate are refused.
3. **The page draws the numbers from the tools, not the prose.** Each `query_metric`, `compare_metric` and `get_kpi_value` result is rendered as a table under the answer, with its filters, defaults, suppression and as-of date. The model writes a short answer and names only the numbers that matter, so a wrong sentence can't change a number on screen.

The card shows the outcome as a pill, for example "✓ 9 numbers checked against the data". The `/api/chat` response carries `tables`, `numbers_checked`, `unverified` and `number_retries`. `/api/chat/stream` returns the same answer as the last line of a newline-delimited JSON stream, after one `progress` line per step (model call, tool call, tool result, number check). Progress lines carry counts and labels, never a measure's value.

---

## Evals

[`evals/questions.yaml`](evals/questions.yaml) holds 38 questions:
- published lookups;
- methodology questions;
- real figures that aren't published, which the agent should route to the source and then answer from the warehouse;
- refusals, each with its expected "can't answer" reason;
- warehouse queries, including preliminary Fall 2026 results;
- one follow-up asked in the same conversation as the question before it.

[`evals.py`](src/oirp_agent/evals.py) runs them through the real agent and scores each question:

| Check | Passes when |
|---|---|
| confidence | the turn gets the expected tier |
| kpi / tool | the expected KPI was looked up, the expected tool called |
| rows | some `query_metric` call returns **the same rows** as the expected query. Rows are compared, not query text, so an equivalent query passes |
| facts | every key fact appears in what the user sees: the answer plus the tables |
| reason | the "can't answer" reason is the expected one (or it answered, when `none`), with at least one suggested question |
| numbers | always: no number that no tool returned |

```powershell
python -m oirp_agent.evals --check                 # free: validates the file, runs every expected query
python -m oirp_agent.evals --max-cost 3            # the full run
python -m oirp_agent.evals --only wh_suppression   # one question
```

The report gives:
- the pass rate for answerable questions and for refusals, against a bar of 90% and 100%;
- answers with unverified numbers (bar: none), and how many number-check rewrites were needed;
- tool calls per question, p50/p95 latency (bar: 45 s), tokens and an estimated cost.

It writes `evals/results/<time>-<model>-<effort>.md`, plus a JSON file with every answer, which is gitignored. `--model` and `--effort` compare settings on the same questions.

**Model comparison, 38 questions (2026-11-14, medium effort):**

| Model | Answerable | Refusals | Unverified | Rewrites | p50 / p95 | Cost per question* |
|---|---|---|---|---|---|---|
| Sonnet 5.5 (default) | 28/29 | 9/9 | 0 | 0 | 4.8 s / 6.4 s | 2.4¢ |
| Haiku 5.5 | 28/29 | 9/9 | 0 | 0 | 4.9 s / 9.7 s | 0.21¢ |

\*With the ~62k-token prompt already cached. Writing the cache costs about 16¢ on Sonnet 5.5 and 1¢ on Haiku 5.5, once per five idle minutes. Sonnet 4.6, the previous default, cost about 5¢ per question at 12 s median.

Both miss the same question: they explain retention versus progression straight from the KPI documents in the prompt instead of looking it up, so no lookup is shown. `low` effort was tried on both and saved under 5% while letting an unverified number through, so `medium` is the setting. Two things got both models here: a guard that drops a "can't answer" label when warehouse numbers are on screen (Haiku added it to correct answers), and counting the system prompt's verified figures as evidence in the number check (quoting them used to cause a rewrite on about four questions in ten).

---

## What's in the published layer (today)

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
- *"What was first-year retention by faculty for the 2024 cohort?"* → queries the synthetic Retention cube (`% Continuing`, Years After = 1, by entry faculty), labels it synthetic, and gives the stale as-of date.
- *"How many undergraduates were enrolled in fall 2025, and what share were international?"* → synthetic Enrolment cube, official count date (reported as an applied default), international = tuition fee status.
- *"Walk me through the admissions funnel for the fall 2025 intake."* → synthetic Admissions cube: applicants → approved → confirmed → registered.

Run the test suite with `pip install -e ".[dev]"` and then `python -m pytest tests -q`.

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
│   ├── base_prompt.md                 system prompt: {{KPI_DOCUMENTS}} + {{WAREHOUSE_DOCUMENTS}}
│   ├── warehouse/                     ── synthetic cube models ──
│   │   ├── retention.md
│   │   ├── enrolment.md
│   │   └── admissions.md
│   └── kpis/                          ── published ground truth ──
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
│   ├── tools.py                       5 tool schemas + dispatcher
│   ├── confidence.py                  per-turn HIGH/MEDIUM/LOW classifier + source labels
│   ├── numbers.py                     display strings, the number check, result tables
│   ├── cannot_answer.py               "can't answer" reasons and suggested questions
│   ├── followups.py                   "ask next" questions worked out from the query
│   ├── evals.py                       eval runner: rows-match scoring, cost and latency report
│   ├── warehouse.py                   cube-model loader + governed metric engine
│   ├── synthetic_warehouse.py         seeded generator for the DuckDB warehouse
│   └── agent.py                       manual tool-use loop with prompt caching
│
├── tests/test_warehouse.py            engine guarantees + cross-cube consistency
│
├── static/
│   ├── index.html                     /  — engineering view
│   └── oirp.html                      /oirp — "What would you like to know?" page
│
├── scripts/                           ── data pipeline ──
│   ├── sources.toml                   editable PDF manifest
│   ├── download_sources.py            fetch + sha256
│   ├── extract_pdfs.py                pdfplumber + pypdfium2
│   └── draft_kpi_values.py            LLM-assisted drafter with quote validation
│
├── data/
│   ├── warehouse/                     gitignored: generated cudw_synthetic.duckdb
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
- **Tier 3 (demonstrated on synthetic data)**: the agent queries a warehouse shaped like the real one through governed measure × dimension queries. Pointing it at the real warehouse means changing the connection in `WarehouseEngine` (DuckDB → a read-only Oracle role) and the generated tables for the real ones. The cube models, tools, and agent stay the same, because the names already match.

The boundaries are the `KPIStore` interface in `src/oirp_agent/kpi_store.py` and the `WarehouseEngine` in `src/oirp_agent/warehouse.py`. Everything above them stays identical. Same with `search_methodology` — swap the keyword scoring for pgvector + Voyage embeddings without touching `tools.py` or `agent.py`.

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

- **No live OIRP data connection.** The verified store is hand-extracted from public PDFs at a point in time. The warehouse is synthetic. Real recent headcounts and retention values are still refused and routed to the published source.
- **Synthetic data is plausible, not calibrated.** Rates and trends are shaped to look like an Ontario university's, not fitted to any real figures. Don't read anything into a synthetic number.
- **No PII.** The synthetic warehouse is student-level, but every student is generated, and name columns are left null. A real integration would add role-based access and complementary suppression on top of the small-cell rule implemented here.
- **The system prompt is ~62k tokens** on the 5.x tokenizer, with the cube models included. Prompt caching keeps the per-turn cost low, but the cold-cache first turn is bigger than before.
- **No conversation memory across sessions.** Each browser session has its own conversation history; nothing persists.
- **Methodology search is keyword-based, not semantic.** Production would use pgvector with Voyage or Cohere embeddings.
- **6 KPIs, not 60.** Coverage is intentionally narrow to demonstrate pattern depth over breadth. The structural typology — simple percentages, composite scores, multi-dimensional cross-tabs, behavioural rates with multi-variant disambiguation, headcount with counting-base ambiguity — is fully exercised.

---

## Cost & rate-limit notes

Running the full demo against your own Anthropic API key costs roughly:

- **Chat session (10 questions):** ~$0.40 against Sonnet 5.5 at medium effort, including one cache write; ~$0.03 against Haiku 5.5.
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
