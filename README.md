# OIRP-chat

A semantic-layer-grounded chat agent for institutional-research questions about
Carleton University. Portfolio demo. Inspired by [Fullscript's
Flurry](https://builders.fullscript.com/posts/building-flurry-how-we-used-agents-to-democratize-data-access-at-fullscript)
architecture, scaled down to public OIRP-style data.

> **Disclaimer.** This is an unaffiliated portfolio project. It is not endorsed
> by Carleton University or Carleton's Office of Institutional Research and
> Planning (OIRP). All KPI values are extracted from publicly published OIRP
> sources, with citations.

## What it does

You ask plain-English questions about Carleton's student engagement, retention,
enrolment, and survey results. The agent answers with verified values, cited
sources, and an explicit confidence tier — or refuses cleanly when the answer
isn't in its verified store.

```
you › What percentage of first-year Carleton students rated their
       experience as good or excellent in 2023?

The 2023 NSSE summary reports that 74% of Carleton first-year respondents
rated their entire educational experience as either "Good" or "Excellent"
(Source: nsse_2023_summary.pdf, Figure 1, p. 5).

This was slightly higher than the rest of the Ontario consortium average,
though the difference was not statistically significant. The Carleton
result also reflects a statistically significant decline from 2020 to 2023
for first-year respondents.

Confidence: HIGH — verified lookup
```

## The architecture

The whole project hinges on one design decision: a **semantic layer** sits
between the agent and the data. The agent does not see raw PDFs or run
ad-hoc searches; it queries a structured store of **verified KPI definitions
and values**, each with explicit source citations.

```
┌─────────────────────────────┐
│ User question (plain text)  │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Claude (Opus 4.7)           │
│   + system prompt           │  ← assembled at startup from all KPI files
│   + 3 tools                 │
└──────────────┬──────────────┘
               │
        ┌──────┴──────┐
        │             │
┌───────▼──────┐ ┌────▼─────────────┐
│ KPIStore     │ │ Confidence       │
│  records[]   │ │ tracker          │
│  prose[]     │ │  (per-turn)      │
└───────┬──────┘ └──────────────────┘
        │
┌───────▼──────────────────────────┐
│ semantic_layer/kpis/*.md          │
│   markdown files with frontmatter │
│   + JSON verified-values blocks   │
│   + prose definitions/caveats     │
└───────────────────────────────────┘
```

Three tools, by design:

| Tool | Purpose | Confidence outcome |
|---|---|---|
| `get_kpi_value` | Structured lookup against verified records | **HIGH** if it returns ≥1 record |
| `search_methodology` | Keyword search over prose sections | **MEDIUM** when used alone |
| `list_kpis` | Discovery / metadata | **MEDIUM** (treated as a discovery turn) |

The agent is instructed to **refuse rather than guess**. If `get_kpi_value`
returns nothing for a specific year/cohort/dimension, the agent says so and
points the user at the right OIRP source instead of inventing a number.

## What's in the semantic layer

Six KPI files at the time of this writing, exercising the full structural
typology you'd hit in real institutional-research data:

| KPI | Source | Shape | Status |
|---|---|---|---|
| `overall_experience_rating` | NSSE 2023 | Simple % | verified |
| `would_choose_same_institution` | NSSE 2023 | Simple % with distribution | verified |
| `nsse_engagement_indicators` | NSSE 2023 | Composite, mixed numerical/directional | verified |
| `nsse_high_impact_practices` | NSSE 2023 | Multi-dim participation rates with cross-tabs | verified |
| `first_year_retention_rate` | OIRP Databook + Annual Report + Operating Budgets | Behavioural rate, multi-variant, partial extraction | partial |
| `undergraduate_enrolment_by_faculty` | OIRP Databook + Annual Report + Operating Budgets | Headcount with counting-base ambiguity, partial extraction | partial |

Each file has:

- YAML frontmatter (`kpi_id`, `domain`, `status`, etc.)
- A definition, calculation, synonyms list, and disambiguation notes
- One or more `json` fenced blocks containing **verified values** with sources
- Caveats, confidence-tier guidance per KPI, related KPIs, and a glossary

The semantic layer is the project. The agent loop is glue. If you only read
two files, read [overall_experience_rating.md](semantic_layer/kpis/overall_experience_rating.md)
(simple shape) and [first_year_retention_rate.md](semantic_layer/kpis/first_year_retention_rate.md)
(messy real-world shape with partial extraction).

## Production architecture (the tier-3 swap)

This demo is **tier 1 + 2** of a notional tier-3 architecture:

- **Tier 1 (done)**: public published values manually verified into the JSON
  blocks. ~60 records across 6 KPIs.
- **Tier 2 (done)**: prose methodology, definitions, and caveats searchable
  via keyword over the markdown files.
- **Tier 3 (architecture-ready)**: live connections to OIRP's warehouse and
  Data Cubes via a real read-only role, swapping the static JSON store for
  database queries. The agent layer doesn't change.

The boundary is the `KPIStore` interface. Replace its implementation with
SQL queries or HTTP calls to OIRP's Data Cubes API; everything above stays
identical. Same with `search_methodology` — swap the keyword scoring for
pgvector + Voyage embeddings without touching `tools.py` or `agent.py`.

This separation is what would make the system shippable inside Carleton:
the chat layer is institution-agnostic; the semantic layer encodes
Carleton-specific business logic; the data layer plugs into Carleton's
warehouse. Three concerns, three swappable parts.

## Run it locally

```bash
# 1. Install
pip install -e .

# 2. Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. REPL
python -m oirp_agent

# Or single-shot:
python -m oirp_agent --once "Compare HIPs participation between 3-year and 4-year programs in 2023"

# Or with tool tracing:
python -m oirp_agent --show-trace
```

## Project layout

```
oirp_chat/
├── README.md                      # this file
├── pyproject.toml
├── semantic_layer/
│   ├── base_prompt.md             # behavioral instructions + {{KPI_DOCUMENTS}} placeholder
│   └── kpis/
│       ├── overall_experience_rating.md
│       ├── would_choose_same_institution.md
│       ├── nsse_engagement_indicators.md
│       ├── nsse_high_impact_practices.md
│       ├── first_year_retention_rate.md
│       └── undergraduate_enrolment_by_faculty.md
├── src/oirp_agent/
│   ├── __init__.py
│   ├── __main__.py                # CLI entry point
│   ├── prompt_loader.py           # parses markdown → KPIDocument objects
│   ├── kpi_store.py               # in-memory store, filterable
│   ├── tools.py                   # tool schemas + dispatch
│   ├── confidence.py              # tier tracking
│   └── agent.py                   # the explicit tool loop
└── evals/
    └── questions.yaml             # 25-question eval scaffold (in progress)
```

## Limitations (deliberate, named)

- **No live data.** All values are hand-extracted from public PDFs at a
  point in time. Recent absolute headcount and FTE values for retention and
  enrolment are flagged as "not yet extracted" and the agent refuses
  rather than guesses.
- **No PII / privacy concerns** — public aggregate data only. (A real OIRP
  bot would need column-level masking and small-cell suppression.)
- **No conversation memory across sessions.** History is in-process only.
- **Methodology search is keyword-based.** Production would use embeddings.
- **6 KPIs, not 60.** Coverage is intentionally narrow to demonstrate
  pattern depth over breadth. The next 4–6 KPIs (CUSC overall satisfaction,
  graduate application volumes, time to completion, etc.) would all reuse
  one of the five structural shapes already exercised.

## Inspiration

The semantic-layer-with-verified-queries pattern is drawn directly from
Fullscript's [Flurry post](https://builders.fullscript.com/posts/building-flurry-how-we-used-agents-to-democratize-data-access-at-fullscript).
The key insight transferred: schema is not the same thing as business
context, and an agent without the latter will generate plausible-looking
SQL (or, in our case, plausible-looking percentages) that's wrong in
ways that are hard to catch.

## License

MIT. Use freely.
