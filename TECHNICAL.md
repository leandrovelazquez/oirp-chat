# OIRP-chat — technical breakdown

A deep-dive companion to the README. Written for technical reviewers — engineers, hiring managers with engineering background, institutional-research staff curious about implementation. If you only want the pitch, read the README. If you want to know why every architectural decision was made the way it was, read this.

---

## Table of contents

1. [What it is, in one paragraph](#1-what-it-is-in-one-paragraph)
2. [The problem it actually solves](#2-the-problem-it-actually-solves)
3. [System architecture at a glance](#3-system-architecture-at-a-glance)
4. [The semantic layer](#4-the-semantic-layer)
5. [The agent loop](#5-the-agent-loop)
6. [The three tools](#6-the-three-tools)
7. [Confidence tier tracking](#7-confidence-tier-tracking)
8. [The data pipeline](#8-the-data-pipeline)
9. [The web layer](#9-the-web-layer)
10. [What was deliberately not built](#10-what-was-deliberately-not-built)
11. [Cost, performance, scaling](#11-cost-performance-scaling)
12. [How it would evolve toward production](#12-how-it-would-evolve-toward-production)

---

## 1. What it is, in one paragraph

OIRP-chat is a chat assistant for institutional-research questions about Carleton University (student engagement, retention, enrolment). It answers questions in natural language and cites every numerical claim back to a specific source PDF and page. When a value isn't in its verified store, it refuses to answer and routes the user to the correct OIRP source instead of guessing. Built on Claude Sonnet 4.6 with manual tool use, a curated semantic layer of 73 verified records across 6 KPIs, a Python data pipeline that extracts and LLM-drafts new records from source PDFs, and two web UIs (a developer view at `/` and an OIRP-styled mock at `/oirp`).

That's the whole product. Everything below is *how*.

---

## 2. The problem it actually solves

### Why naive RAG over PDFs fails for institutional research

The typical "build a chatbot for our documents" pattern is: chunk PDFs → embed with a vector model → store in a vector DB → retrieve top-K chunks at query time → ask an LLM to answer. This works for FAQ-style content and breaks immediately on institutional-research data, for three reasons:

**Definitional ambiguity.** OIRP publishes "first-year retention rate" under at least four distinct definitions — FTFY one-year, FTFY two-year, all-first-year, and progression-to-second-year — each with different numerators, denominators, and cohort definitions. A naive RAG bot picks the chunk it retrieved, doesn't know there's ambiguity, and confidently gives the wrong number.

**Cross-reference dependence.** A single answer to "how does Carleton compare to Ontario on NSSE engagement indicators" requires knowing: which 19 institutions are in the consortium, that comparisons exclude Carleton itself, that effect sizes were all <0.3, that statistical significance ≠ practical significance, and that some indicators are reported only directionally while others have point values. None of this lives in a single retrievable chunk.

**Refusal is the right answer surprisingly often.** "What was Carleton's retention rate by faculty in 2023?" — OIRP doesn't publish this breakdown. The correct response is "I don't have that; you'd need to request it from the Departmental Measures team." A naive RAG bot fabricates plausible per-faculty numbers because *something* must be retrieved.

### The pattern this project uses instead

Rather than retrieve at query time, **pre-curate the canonical answers and have the agent look them up**. The semantic layer is a deliberately small set of human-curated records, each tagged with its source page and a verbatim quote anchor. The agent doesn't *generate* numbers — it queries a structured store. When the store doesn't have what's asked, the agent's system prompt makes refusal the default behavior. Hallucination becomes structurally impossible for any value not in the store, because the agent has no other source of numerical claims.

This trades coverage breadth for correctness depth. 73 records, not 73,000. But every one of those 73 is grounded, cited, and reviewable.

The pattern is borrowed from Fullscript's [Flurry](https://builders.fullscript.com/posts/building-flurry-how-we-used-agents-to-democratize-data-access-at-fullscript) — their "verified queries" for SQL, adapted as "verified values" for OIRP's published-percentage shape of data.

---

## 3. System architecture at a glance

Five components, each with a single clear responsibility:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  USER                                                                    │
│   browser at  / (engineer view)  or  /oirp (institutional view)          │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ JSON over HTTP (/api/chat)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  WEB LAYER  ─ src/oirp_agent/web.py                                      │
│   FastAPI + uvicorn                                                      │
│   • Per-session OIRPAgent (cookie-keyed)                                 │
│   • /api/chat, /api/info, /api/reset                                     │
│   • Serves static/index.html and static/oirp.html                        │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ agent.chat(message) → TurnResult
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  AGENT LOOP  ─ src/oirp_agent/agent.py                                   │
│   Manual tool-use loop against Claude Sonnet 4.6                         │
│   • System prompt assembled at startup from base + KPI files (~22k tok)  │
│   • Prompt caching: ephemeral cache_control on the system block          │
│   • Per-turn confidence tracking                                         │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ tool calls: get_kpi_value,
                                 │             search_methodology,
                                 │             list_kpis
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  KPI STORE  ─ src/oirp_agent/kpi_store.py                                │
│   In-memory store built from parsed markdown                             │
│   • records[]:    flat list of verified values (73 across 6 KPIs)        │
│   • prose_sections[]:  H2-split sections for keyword search              │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ (loaded once at process start)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SEMANTIC LAYER  ─ semantic_layer/kpis/*.md                              │
│   6 markdown files, each containing:                                     │
│   • YAML frontmatter (kpi_id, status, domain)                            │
│   • Prose: definition, calculation, synonyms, caveats, related KPIs      │
│   • One or more ```json fenced blocks with verified values + sources     │
│   THIS IS THE GROUND TRUTH. Everything else is plumbing around it.       │
└──────────────────────────────────────────────────────────────────────────┘

Out-of-band pipeline (run offline, not in the request path):

   sources.toml  →  download_sources.py  →  data/pdfs/
                 →  extract_pdfs.py      →  data/extracted/
                 →  draft_kpi_values.py  →  data/proposed/
                 →  human review         →  semantic_layer/kpis/*.md
```

If you remember nothing else: **the semantic layer is the project, everything else is plumbing around it.** The architecture's job is to keep that file system honest and queryable.

---

## 4. The semantic layer

### File anatomy

Each KPI lives in a single `semantic_layer/kpis/<kpi_id>.md`. Six files today:

| KPI | Shape | Records |
|---|---|---|
| `overall_experience_rating` | Simple % with optional full distribution | 8 |
| `would_choose_same_institution` | Simple % with full distribution | 8 |
| `nsse_engagement_indicators` | Composite metric, mixed directional + numerical | 15 |
| `nsse_high_impact_practices` | Multi-dim participation rates with cross-tabs | 26 |
| `first_year_retention_rate` | Behavioural rate, multi-variant, partially extracted | 6 |
| `undergraduate_enrolment_by_faculty` | Headcount with counting-base ambiguity | 10 |

Each file has the same structural anatomy:

```markdown
---
kpi_id: overall_experience_rating       ← YAML frontmatter for the loader
domain: student_engagement
source_survey: NSSE
status: verified | partial | stub
last_reviewed: 2026-04-30
---

# Overall Educational Experience Rating (NSSE)

## Definition          ← plain-English what-and-why
## Calculation         ← exact formula or methodology
## Synonyms            ← words the user might use ("satisfaction", "rating")
                        with explicit disambiguation against other KPIs
## Source Documents    ← which PDFs the data comes from
## Verified Values     ← one or more ```json fenced blocks
                        these are what the agent looks up
## Comparison Context  ← what "Ontario consortium" means here, etc.
## Caveats             ← response rate, gender weighting, effect sizes
## Confidence Tier Guidance     ← per-KPI HIGH/MEDIUM/LOW rules
## Related KPIs        ← cross-references
## Glossary References ← terminology used in the verified-values fields
## Change Log          ← when this file was edited and by whom
```

### Verified values, concretely

A single record from `overall_experience_rating.md`:

```json
{
  "year": 2023,
  "cohort": "first_year",
  "comparison_group": "carleton",
  "value_pct": 74,
  "metric_variant": "good_or_excellent",
  "source": {
    "file": "nsse_2023_summary.pdf",
    "page": 5,
    "figure": "Figure 1",
    "quote_anchor": "Seventy-four percent of first-year respondents"
  },
  "verified_by": "manual_review",
  "verified_on": "2026-04-27"
}
```

A few choices worth highlighting:

- **`comparison_group`** is a field, not a separate KPI. This file holds both Carleton values and rest-of-Ontario-consortium values, distinguished by this dimension. Agent tool calls filter on it.
- **`source` is structured**, not a free-text citation. The agent extracts `file` and `page` for inline citations to users.
- **`quote_anchor`** is the verbatim source-text proof that this number isn't fabricated. The drafter pipeline validates this; the agent surfaces it on request.
- **No `confidence` field on the record itself** — confidence is a property of the *answer turn* (computed from which tools fired with which results), not of the data. A high-quality record can still produce a low-confidence answer if the question stretched beyond what the record supports.

### Why markdown for the ground truth

Markdown with YAML frontmatter and embedded JSON gives three things at once:

1. **GitHub diffs are reviewable.** Every change to a verified value shows up as a small, focused PR-able diff.
2. **A human can read the file.** Prose and JSON sit together, so a reviewer understands both *what* the value is and *why* it's defined that way.
3. **The agent reads the same file.** No separate "human docs" vs "machine docs." Both views of every KPI come from one source.

Trade-off: parsing custom markdown is more code than reading a YAML file or a database row. The `prompt_loader.py` module handles this in about 100 lines.

---

## 5. The agent loop

### Why a manual tool-use loop

The Anthropic Python SDK ships with `client.beta.messages.tool_runner()` that handles the tool-call loop automatically. This project uses the lower-level `client.messages.create()` and implements the loop by hand in `src/oirp_agent/agent.py`. ~200 lines instead of ~80.

The trade-off is deliberate. For a portfolio piece, the explicitness is the point — a reviewer can read the agent file and see exactly how tool-calling, conversation history, and confidence tracking fit together. The auto-runner would hide that.

### The loop, simplified

```python
def chat(self, user_message: str) -> TurnResult:
    self.history.append({"role": "user", "content": user_message})
    trace = TurnTrace()

    for _ in range(MAX_TOOL_ROUNDS):              # bounded at 8
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},   # prompt caching
            }],
            tools=TOOL_SCHEMAS,
            messages=self.history,
        )

        # Persist assistant turn to history (required for next tool round)
        self.history.append({"role": "assistant",
                             "content": serialize(response.content)})

        if response.stop_reason != "tool_use":
            break

        # Execute every tool_use block in this response
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = self.dispatcher.dispatch(block.name, block.input)
            trace.record(block.name, block.input, result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        self.history.append({"role": "user", "content": tool_results})

    return TurnResult(
        text=extract_text(self.history[-1]["content"]),
        confidence=trace.confidence,
        trace=trace,
    )
```

Three things this loop does that matter:

**Persists the conversation through the API's expected shape.** Tool results go in a `user`-role message with `tool_result` blocks; the previous assistant message must remain in history with its `tool_use` blocks intact. The serialization helper in the real code handles converting between SDK objects (returned by `create`) and plain dicts (required when re-sending in `messages`).

**Bounded loop.** `MAX_TOOL_ROUNDS = 8`. In practice the agent rarely fires more than 2-3 tool calls per turn, but the bound prevents runaway loops if the model gets stuck.

**Confidence tracking inline.** Every tool call's result is fed to `TurnTrace.record()`, which classifies it for the per-turn confidence tier (see §7).

### System prompt assembly

At startup, `prompt_loader.assemble_system_prompt()` reads `semantic_layer/base_prompt.md` and substitutes its `{{KPI_DOCUMENTS}}` placeholder with the concatenated text of every KPI file. Result: a ~22k-token system prompt the agent sees on every turn. Contents:

- The base prompt: identity, tools, confidence-tier discipline, hard rules (never invent numbers, always cite, refuse rather than guess), response format.
- Every KPI file in full: frontmatter, prose, JSON blocks, glossary references, change log.

This is large but appropriate. The base prompt is ~1.5k tokens; the rest is the semantic layer itself, which the agent uses for tool-selection reasoning, disambiguation, and refusal decisions. Without the full file content the agent doesn't know that "retention" needs disambiguation or that "engagement" can mean five different things.

### Prompt caching

The system prompt is wrapped in `cache_control: {type: "ephemeral"}`. Anthropic's prompt caching writes the prefix to cache on first send (5-minute TTL, refreshed on each hit) and reads it on subsequent sends. The effects:

- **Rate limit**: cached input tokens don't count toward ITPM. A 22k-token prompt would otherwise blow Tier 1 limits on multi-turn conversations.
- **Cost**: cached reads bill at 10% of normal input pricing. A chat session of 10 questions costs ~$0.05 instead of ~$0.30.
- **Latency**: cache reads are faster (~10-20% reduction in time-to-first-token for prompts this size).

The first chat after server start has a "cold cache" — that turn writes ~22k tokens. Every subsequent turn within 5 minutes reads from cache. Tier 1 Sonnet's ITPM accommodates the cold-cache write comfortably.

---

## 6. The three tools

The agent has exactly three tools, chosen to keep the design surface small enough to reason about:

### `get_kpi_value(kpi_id, filters?)`

**Purpose.** Structured lookup against the verified-records store. Primary tool — the agent uses this for any specific number.

**Input.** `kpi_id` (required, e.g. `"overall_experience_rating"`) and an optional `filters` dict of exact-match key/value pairs (e.g. `{year: 2023, cohort: "first_year"}`).

**Implementation.** Filter the in-memory `records` list by `kpi_id`, then by every key in `filters`. Return all matching records.

**Returns.** `{kpi_id, filters, match_count, records[]}`. Each record carries its full `source` object so the agent can cite inline.

**Empty-result handling.** If `match_count == 0`, the system prompt instructs the agent to refuse rather than guess, citing the correct OIRP source. This is the single most important behavior in the system. The tool itself doesn't produce the refusal — the agent does, based on the empty result and the system-prompt instruction.

### `search_methodology(query, kpi_id?, top_k?)`

**Purpose.** Keyword search across the prose sections of the KPI files for methodology, definitions, caveats, headline findings.

**Input.** A `query` string, optional `kpi_id` to scope, optional `top_k` (default 5).

**Implementation.** Tokenize the query into words longer than 2 characters. For each prose section, score by sum of token frequencies. Return top-K sections with their kpi_id, header, and full text.

**Honesty about the design.** This is naive keyword scoring, not vector similarity. For a portfolio demo it's the honest minimum that proves the architecture — the boundary is the `search_prose()` method in `kpi_store.py`, and swapping to pgvector + Voyage embeddings would be a ~50-line change that touches no other file.

### `list_kpis()`

**Purpose.** Discovery — returns metadata about every KPI in the layer.

**Input.** None.

**Returns.** A list of `{kpi_id, domain, status, metric_type, source_survey, summary}` records. The summary is the first paragraph of the KPI's Definition section.

**Use.** The agent calls this when the user's question doesn't clearly map to a known KPI ("what can I ask you about?"). Rarely fires; when it does, it's a discovery turn.

### What's NOT here

Notably absent:

- **No web search.** The agent has no way to retrieve external content. Removes a class of failure modes (citing Wikipedia or unaffiliated college-ranking sites for Carleton data).
- **No computation tool.** The agent cannot run SQL, evaluate expressions, or compute trends. Trend characterization comes from the prose in the KPI files (where OIRP has published its interpretation) or from the user's own synthesis across multiple `get_kpi_value` lookups.
- **No file-reading tool.** The agent never directly reads source PDFs at query time. All values flow through the human-reviewed verified store.

These are deliberate. Each absent tool would expand the surface area for hallucination.

---

## 7. Confidence tier tracking

After every chat turn, the system attaches a HIGH / MEDIUM / LOW / NONE confidence tier to the response. The UI renders it as a colored badge next to the answer.

### Classification logic

Implemented in `src/oirp_agent/confidence.py`:

```
if any get_kpi_value call returned ≥1 record:
    HIGH      # verified lookup hit
elif any search_methodology call returned matches:
    MEDIUM    # methodology / synthesis
elif only list_kpis was called:
    MEDIUM    # discovery turn
elif any get_kpi_value call returned 0 records:
    LOW       # the agent should have refused; flag for review
else:
    NONE      # no tools fired — agent answered from system-prompt knowledge
```

### Why this matters

The classification isn't a guess at the model's epistemic state — it's grounded in what tools fired and what they returned. A HIGH badge means "this answer came from a record that exists in the verified store." A LOW badge means "the agent queried the store and got nothing back; check that it actually refused instead of answering anyway."

For an institutional-research bot specifically, calibration matters more than fluency. A flat "I don't know" is a *successful* response when the question stretches past the store; the LOW tier surfaces that successful refusal to the reviewer.

### What this enables

Two downstream uses:

**Eval harness.** The eval scaffold in `evals/questions.yaml` includes an `expected_confidence` field per question. A future eval runner compares the actual tier against the expected one — turning subjective answer-quality into a measurable pass/fail.

**Operator review.** For a deployed bot, logging the confidence tier per turn (alongside the tool trace) gives operators a triage queue: review the LOW turns first, audit the MEDIUM ones occasionally, trust the HIGH ones in aggregate.

---

## 8. The data pipeline

The pipeline turns source PDFs into reviewed verified-value records. Three stages, each a separate Python script in `scripts/`.

### Stage 1 — `download_sources.py`

**Input.** `scripts/sources.toml`, an editable TOML manifest of `(id, url, doc_type, year, title)` entries.

**What it does.** Downloads each PDF to `data/pdfs/<id>.pdf`, computes SHA-256, writes `data/pdfs/manifest.json` with `{id, url, sha256, downloaded_at, ...}`. Idempotent: re-running skips files whose existing hash matches.

**Notable choices.**

- *No dependencies beyond stdlib + tomllib.* Pure Python 3.11+ with `urllib.request` for the HTTP. One less library to depend on.
- *Atomic writes.* Each download writes to a `.tmp` file first, then renames. An interrupted run can never leave a half-written PDF on disk.
- *Bounded size.* `MAX_BYTES = 50MB`. A misconfigured URL can't fill the disk.
- *Polite User-Agent.* `oirp-chat/0.1 (portfolio demo; local download script)`. Identifies the script in OIRP's access logs if they look.
- *Manifest as source of truth.* The TOML file lists what *should* exist; the manifest JSON records what *does* exist with content hashes. Diff the two to see drift.

### Stage 2 — `extract_pdfs.py`

**Input.** `data/pdfs/manifest.json` + the PDFs themselves.

**What it does.** For each PDF, opens with pdfplumber and extracts:

- Per-page text (with `x_tolerance=2, y_tolerance=3` for stable columnar layouts).
- Per-page tables as nested lists of cells (None for empty cells where the PDF used visual padding).
- Page renderings as PNGs (via pypdfium2 at 150 DPI) for any page containing a table, for human review and vision-model fallback.

Writes to `data/extracted/<id>/`: `pages.json`, `tables.json`, `meta.json` (provenance: source sha256, tool versions, timestamp), plus `page-NN.png` for pages with tables.

**Notable choices.**

- *pdfplumber over pypdf.* Better at table-aware extraction; OIRP survey summaries are table-heavy.
- *PNG rendering as a fallback path.* If pdfplumber mangles a particular table (merged cells, missing borders), the PNG of that page is ready to be sent to Claude as a vision input. The current drafter doesn't use this path yet; the rendering infrastructure is in place for when it's needed.
- *Idempotent against source sha256.* Re-extraction is skipped when the meta.json's `source_sha256` matches the manifest. `--force` bypasses.
- *No "cleaning" of extracted tables.* `pages.json` and `tables.json` contain the raw pdfplumber output, None cells and all. Cleaning is downstream (the LLM drafter handles it).

### Stage 3 — `draft_kpi_values.py`

**Input.** One PDF's `data/extracted/<id>/` directory + all existing semantic-layer KPI files.

**What it does.** Calls Claude with the existing KPI schemas as context and the extracted PDF pages as the corpus. The agent uses three custom tools:

- `propose_kpi_value(kpi_id, record, confidence, notes)` — propose one new verified-value record matching the existing KPI's schema. Required: `record.source` must include a `quote_anchor` field (verbatim ≥8-word excerpt from the cited page).
- `flag_correction(kpi_id, ...)` — flag a discrepancy with an existing record.
- `finish(summary)` — terminate with a reviewer-facing summary.

After the agent returns, every proposed record's `quote_anchor` is **string-matched** against the cited page's extracted text. Mismatches get flagged in bold red in the output review file.

Output: `data/proposed/<pdf_id>.review.md` — a human-readable markdown file with each proposal, its confidence tier, its quote-validation status, and the drafter's notes.

**Notable choices.**

- *Tool use, not free-form generation.* Free-form JSON would let the model produce convincing-looking proposals without grounding. Tool calls require the model to construct the schema deliberately.
- *Verbatim quote anchor is required, not optional.* Without it, post-hoc verification is impossible.
- *Prompt caching on the system prompt + KPI files.* The 22k-token context is identical across every tool turn within a single drafter run. cache_control on both blocks reduces effective ITPM consumption by ~85% and cost by similar.
- *Default model is Haiku 4.5 for cost.* For PDFs with messier tables (NSSE summaries) the user can override with `--model claude-sonnet-4-6`. Mixing models per task type is a real cost-management decision, not a hedge.
- *NEVER writes to `semantic_layer/kpis/`.* Output goes only to `data/proposed/`. Human review is a structural gate, not a recommended habit.

### Measured pipeline outcomes (4 PDFs, 1 review pass)

| PDF | Pages | Tables | Proposals | Quote-verified | Adopted after review |
|---|---|---|---|---|---|
| `nsse_2023_summary` | 19 | 18 | 10 | 10 (100%) | 9 |
| `operating_budget_2024_25` | 22 | 15 | 2 | 2 (100%) | 1 |
| `operating_budget_2025_26` | 18 | 5 | 3 | 2 (67%) | 2 |
| `students_enrolment_2023_24_annual_report` | 20 | 0 | 1 | 0 (0%) | 0 (used as anchor wording only) |

Net effect: verified store expanded from **60 to 73 records** after ~16 minutes of human review per PDF. The single unverified-quote case was an annual-report claim that the drafter had grounded in a paraphrase of source text rather than a verbatim excerpt — the validator caught it and the reviewer skipped it.

---

## 9. The web layer

### FastAPI + uvicorn

`src/oirp_agent/web.py` defines a small FastAPI app with five routes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve `static/index.html` (engineering view) |
| GET | `/oirp` | Serve `static/oirp.html` (institutional view) |
| GET | `/api/info` | Semantic-layer summary (KPI count, model, active sessions) |
| POST | `/api/chat` | Send a user message, return text + confidence + tool trace |
| POST | `/api/reset` | Clear the current session's conversation history |

Per-session state is keyed by an HTTP-only `oirp_session` cookie. The first chat call generates a session ID and stores an `OIRPAgent` instance in a process-local dict; subsequent calls reuse it. No persistence — restarting the server resets all sessions.

For a single-user portfolio demo this is fine. For production you'd back the session map with Redis and persist conversation history separately.

### Inline `.env` loader

At module load, `web.py` checks for `.env` at the project root and applies any `KEY=value` pairs to `os.environ` via `setdefault`. This means `uvicorn oirp_agent.web:app` just works without remembering to `export ANTHROPIC_API_KEY=...` first — a common stumbling block.

Inlined rather than depending on python-dotenv: one fewer dependency, the parser is ~10 lines, and the behavior is fully transparent in the source.

### Two HTML files

Both UIs are single self-contained HTML files (~600 lines each including CSS and JS). No build step, no frameworks, no node_modules.

**`static/index.html`** — engineering view. Wide chat layout, full message history, confidence-badge per response, expandable tool-call trace per turn. Mobile-friendly but built for desktop demos.

**`static/oirp.html`** — institutional view. Two-column layout: hero content on the left (deep-red Carleton-adjacent palette, serif headlines, prose explaining the project), chat panel sticky on the right. On mobile (`max-width: 960px`) the chat collapses to a "💬 Ask OIRP" floating launcher that opens the chat as a full-screen overlay. Concept-demo disclaimer banner across the top, footer note linking to GitHub.

The two pages share zero code — they're independent HTML files. Both call the same `/api/chat` endpoint. The same agent answers the same questions; only the presentation differs.

---

## 10. What was deliberately not built

The boundary between "should this be in scope" and "save it for later" matters for a portfolio piece. Naming what's deliberately *not* here is itself a signal of judgment.

**No vector embeddings.** Methodology search is keyword scoring. The architecture's `KPIStore.search_prose()` is the swap point; pgvector + Voyage is a clean upgrade when the answer quality on methodology questions stops being good enough.

**No conversation memory across sessions.** Each browser session has its own history. A real product would persist conversations per user; the demo doesn't need that complexity.

**No web search tool.** The agent cannot retrieve external content. Removes a hallucination surface — external sites about "Carleton" frequently mean Carleton College in Minnesota, and a web-search-equipped agent would happily cite them.

**No SQL/computation tool.** No `run_query` or `eval_expression`. Numbers come from the verified store or not at all.

**No PII handling.** Public aggregate data only. A real OIRP integration would need column-level masking, small-cell suppression, audit logging, role-based access — all out of scope for a portfolio demo.

**No observability stack.** Tool traces are surfaced per-turn in the UI; nothing is persisted to a database, Langfuse, or similar. A few production hooks would be the next obvious add.

**No automated eval runner yet.** `evals/questions.yaml` contains 25 hand-written test questions with expected confidence tiers and key facts. The script that walks the YAML, runs each question through the agent, and produces a pass/fail markdown report is described in the README's roadmap but not yet built.

**No streaming chat.** The web UI POSTs a question and waits for the full response. Streaming would be a nicer UX (token-by-token rendering) but adds API complexity that's not worth it for the demo scale.

Each absence is a deliberate scope choice, not a forgotten feature.

---

## 11. Cost, performance, scaling

### Token economics

The 22k-token system prompt is the dominant cost driver. Without prompt caching, every chat turn would bill 22k input tokens at Sonnet 4.6's $3/M = $0.066 per turn. With caching:

- **Cold cache (first turn):** ~22k tokens written at $3.75/M = $0.083 (one-time).
- **Warm cache (subsequent turns within 5 min):** 22k tokens read at $0.30/M = $0.007.

A 10-question chat session costs roughly **$0.05** total.

### Rate limits

Tier 1 Sonnet 4.6 ITPM is approximately 50k. Without caching, two 22k-token turns in 60 seconds would exceed this. With caching, only the cold-cache write counts against ITPM — subsequent reads are exempt — so a comfortable conversation rate of 1 question per few seconds stays well under the limit.

The drafter encountered ITPM issues during development before caching was added. Once both the system prompt and the (per-PDF, ~22k token) user message were both cached with `cache_control`, runs completed without rate-limit errors.

### Memory

The KPI store fits comfortably in memory: 73 records, 74 prose sections, ~150KB total. The semantic layer is loaded once at startup and shared across all sessions. No DB connection pool, no cache eviction, no concurrency primitives — just a Python dict.

### Scaling ceiling

The current architecture would handle ~100 KPIs (~1000 verified records, ~1500 prose sections) before any redesign is needed. Beyond that:

- The system prompt grows past ~50k tokens, which starts to bump into model context windows on cheaper variants and increases cold-cache write cost. Solution: lazy-load only the KPIs relevant to a session, using `list_kpis` as a routing step.
- Keyword search across hundreds of prose sections gets slow and lossy. Solution: switch to vector embeddings with relevance reranking.
- The per-session in-memory state doesn't scale past one process. Solution: externalize sessions to Redis.

None of these limits are within an order of magnitude of where the project currently is.

---

## 12. How it would evolve toward production

The project is structured deliberately as **tier 1 + 2 of a notional tier 3**. The phases below describe what each tier looks like and what would change.

### Tier 1 — current

Hand-curated verified values from public PDFs, in JSON blocks within KPI markdown files. Keyword search over prose. Single-process FastAPI. ~73 records, 6 KPIs.

Already shipped.

### Tier 2 — current

LLM-assisted drafter that proposes new records from extracted PDFs with verbatim quote validation. Human review gate between proposals and the verified store.

Already shipped.

### Tier 3 — production architecture

Three changes to plug into Carleton's actual systems:

**Replace the static KPI store with live database queries.** The `KPIStore` interface in `kpi_store.py` is the boundary. Its current implementation loads from markdown files; the production implementation would query OIRP's data warehouse via a read-only connection. The agent layer above doesn't change.

In practice this means each `get_kpi_value` call becomes a parameterized SQL query against a known schema. The semantic layer's role shifts: instead of *storing* the values, it documents the *queries* that produce them (verified queries, in Flurry's exact terminology). The KPI markdown files would carry SQL snippets in their JSON blocks rather than literal values.

**Replace keyword methodology search with vector retrieval.** Embed the prose sections (and the actual source PDFs, chunked) with Voyage or Cohere embeddings. Store in pgvector. `search_methodology` queries become approximate-nearest-neighbor lookups with relevance reranking. Same interface from the agent's perspective.

**Add the production concerns that a portfolio demo skipped.** PII detection, small-cell suppression, per-user authorization (via Carleton SSO), audit logging of every tool call and answer, alerting on LOW-confidence rates above threshold, an operator dashboard for triaging the LOW turns. Add observability (Langfuse or similar) so a maintainer can drill into specific responses.

None of these are speculative — they're the obvious upgrades that follow from the current architecture's interfaces. The boundary discipline (KPIStore is the swap point, the agent layer is institution-agnostic, the data layer plugs in) is what makes them straightforward additions rather than rewrites.

### What stays the same

Across all tiers, the parts that don't change:

- The semantic layer concept (definitions, synonyms, disambiguation, verified content with grounding).
- The refusal-by-default behavior.
- The confidence-tier discipline.
- The agent loop and tool schemas.
- The two web UIs.

That continuity is the point of the design.

---

## Closing

The shortest defensible description of this project:

> A chat agent for institutional-research data that refuses to guess. Backed by a small, well-curated semantic layer with verbatim source citations. Built on Claude with manual tool use, prompt caching, and an LLM-assisted drafter that closes the loop on adding new records under human review.

Everything in this document is the elaboration of that sentence. If a reader walks away remembering only that the agent refuses rather than guesses, and that refusal is the actual product, that's the right takeaway.

For the engineering audience specifically: the parts of this project that are non-obvious in hindsight are the boundary discipline (KPIStore as a clean swap point, agent layer as institution-agnostic), the structural-not-statistical confidence tracking (based on what tools fired, not what the model thinks it knows), and the human-review gate in the drafter pipeline (the LLM proposes, the human commits). Those are the bits worth scrutinizing if you're evaluating the work.

---

*Repository: [github.com/leandrovelazquez/oirp-chat](https://github.com/leandrovelazquez/oirp-chat). Built as a portfolio project; not affiliated with Carleton University or its Office of Institutional Research and Planning.*
