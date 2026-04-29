---
kpi_id: nsse_engagement_indicators
domain: student_engagement
source_survey: NSSE
metric_type: composite
status: verified
last_reviewed: 2026-04-27
owner: oirp-chat (portfolio project)
---

# NSSE Engagement Indicators

## Definition

NSSE clusters its individual survey items into **ten Engagement Indicators**,
grouped under four themes. Each indicator is a composite score on a **0–60
scale** representing how strongly respondents engage with that aspect of their
educational experience.

The ten indicators and their themes:

| Theme                       | Indicator                          |
| --------------------------- | ---------------------------------- |
| **Academic Challenge**      | Higher-Order Learning              |
|                             | Reflective & Integrative Learning  |
|                             | Learning Strategies                |
|                             | Quantitative Reasoning             |
| **Learning with Peers**     | Collaborative Learning             |
|                             | Discussions with Diverse Others    |
| **Experiences with Faculty**| Student-Faculty Interaction        |
|                             | Effective Teaching Practices       |
| **Campus Environment**      | Quality of Interactions            |
|                             | Supportive Environment             |

Each indicator is reported separately for **first-year** and **final-year**
respondents, and is benchmarked against the rest of the Ontario consortium.

## Calculation

This is a **derived/composite metric**, not a raw survey response. The agent
must not attempt to recompute indicator scores from individual item responses —
NSSE's published methodology defines the underlying items, weights, and scaling.

```
indicator_score
  = NSSE_published_composite(
      items belonging to indicator,
      respondent cohort,
      institutional gender weighting
    )
  ∈ [0, 60]
```

Indicator scores are not percentages and are not directly comparable to the
0–100 scales used in other parts of NSSE reporting (e.g., overall experience
rating). When a user mixes scales, flag the conversion explicitly.

## Synonyms

- "engagement indicators" / "engagement scores"
- "NSSE indicators"
- "academic challenge" / "higher-order learning" / etc. (the individual
  indicator names)
- "how engaged are Carleton students"
- "Carleton vs Ontario engagement"
- "the ten indicators"

**Disambiguation.** Users sometimes say "engagement" loosely to mean
participation, attendance, or course interaction in non-NSSE contexts. If the
question is about course-level engagement, LMS analytics, or co-curricular
participation, this is **not** the right metric — clarify with the user.

## Source Documents

| Survey Year | Source File              | Location                                          |
| ----------- | ------------------------ | ------------------------------------------------- |
| 2023        | `nsse_2023_summary.pdf`  | "NSSE Engagement Indicators", Table 3 + breakouts, p. 9–11 |
| 2020        | `nsse_2020_summary.pdf`  | "NSSE Engagement Indicators" section              |
| 2017        | `nsse_2017_summary.pdf`  | "NSSE Engagement Indicators" section              |

Carleton-vs-2020 numerical comparisons in the 2023 PDF are reported only for
indicators with statistically significant year-over-year change. Other
indicators' 2020 values would need extraction from the 2020 source PDF.

## Verified Values

### 2023 Carleton vs Ontario Consortium — Direction of Difference

The 2023 source PDF reports **direction of statistically significant
difference** rather than indicator point values for the cross-sectional
comparison. The agent should report these directional findings, not invented
point values.

```json
[
  {
    "year": 2023,
    "indicator": "higher_order_learning",
    "theme": "academic_challenge",
    "first_year_vs_ontario": "lower",
    "final_year_vs_ontario": "no_difference",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "reflective_integrative_learning",
    "theme": "academic_challenge",
    "first_year_vs_ontario": "lower",
    "final_year_vs_ontario": "no_difference",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "learning_strategies",
    "theme": "academic_challenge",
    "first_year_vs_ontario": "lower",
    "final_year_vs_ontario": "lower",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "quantitative_reasoning",
    "theme": "academic_challenge",
    "first_year_vs_ontario": "no_difference",
    "final_year_vs_ontario": "no_difference",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "collaborative_learning",
    "theme": "learning_with_peers",
    "first_year_vs_ontario": "lower",
    "final_year_vs_ontario": "lower",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "discussions_with_diverse_others",
    "theme": "learning_with_peers",
    "first_year_vs_ontario": "no_difference",
    "final_year_vs_ontario": "no_difference",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "student_faculty_interaction",
    "theme": "experiences_with_faculty",
    "first_year_vs_ontario": "lower",
    "final_year_vs_ontario": "lower",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "effective_teaching_practices",
    "theme": "experiences_with_faculty",
    "first_year_vs_ontario": "higher",
    "final_year_vs_ontario": "higher",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "quality_of_interactions",
    "theme": "campus_environment",
    "first_year_vs_ontario": "no_difference",
    "final_year_vs_ontario": "higher",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  },
  {
    "year": 2023,
    "indicator": "supportive_environment",
    "theme": "campus_environment",
    "first_year_vs_ontario": "no_difference",
    "final_year_vs_ontario": "no_difference",
    "source": { "file": "nsse_2023_summary.pdf", "page": 9, "table": "Table 3" }
  }
]
```

### 2020 vs 2023 Carleton — Year-over-Year Change (Statistically Significant Only)

```json
[
  {
    "indicator": "quantitative_reasoning",
    "cohort": "first_year",
    "value_2020": 24.87,
    "value_2023": 26.72,
    "direction": "increase",
    "statistically_significant": true,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11 }
  },
  {
    "indicator": "collaborative_learning",
    "cohort": "first_year",
    "value_2020": 33.13,
    "value_2023": 30.31,
    "direction": "decrease",
    "statistically_significant": true,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11 }
  },
  {
    "indicator": "discussions_with_diverse_others",
    "cohort": "first_year",
    "value_2020": 41.04,
    "value_2023": 39.22,
    "direction": "decrease",
    "statistically_significant": true,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11 }
  },
  {
    "indicator": "higher_order_learning",
    "cohort": "final_year",
    "value_2020": 37.38,
    "value_2023": 39.29,
    "direction": "increase",
    "statistically_significant": true,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11 }
  },
  {
    "indicator": "collaborative_learning",
    "cohort": "final_year",
    "value_2020": 32.36,
    "value_2023": 28.21,
    "direction": "decrease",
    "statistically_significant": true,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11 }
  }
]
```

> **Note for the agent.** The 2023 source PDF reports point values
> (the 0–60 scores) **only** for the seven indicator-cohort pairs above where
> 2020-vs-2023 change was statistically significant. For all other
> indicator-cohort pairs in 2020 and 2023, this file does not yet contain
> verified point values. Do **not** invent numbers. Either:
>
> 1. Report the directional finding from the 2023 cross-sectional table, or
> 2. State that point values for that indicator-cohort-year are not yet
>    extracted into the verified store, and offer to look up the source PDF.

## Item-Level Drivers (Qualitative)

For statistically significant Carleton-vs-Ontario differences, the source PDF
identifies which underlying items drove the indicator-level result. The agent
should treat these as **qualitative explanations**, not as separate metrics.

**Higher-Order Learning (first-year, lower).** First-year Carleton respondents
were less likely than the Ontario average on two items: *evaluating a point of
view, decision, or information source*; and *forming a new idea or
understanding from various pieces of information*.

**Reflective & Integrative Learning (first-year, lower).** Four items drove the
difference, including *connecting learning to societal problems or issues* and
*examining strengths and weaknesses of one's own views*.

**Learning Strategies (both cohorts, lower).** Both cohorts: *reviewed your
notes after class*. First-year only: *identified key information from reading
assignments*. Final-year only: *summarized what you learned*.

**Collaborative Learning (both cohorts, lower).** Three shared items including
*asking another student for help* and *preparing for exams together*. Final-year
also: *explained course material to other students*.

**Student-Faculty Interaction (both cohorts, lower).** First-year on three
items including *talking about career plans with a faculty member*. Final-year
on *working with a faculty member on activities other than coursework*.

**Effective Teaching Practices (both cohorts, higher).** Both cohorts:
*instructors provided prompt and detailed feedback on tests or assignments*.
Final-year additionally: *instructors provided feedback on a draft or
work-in-progress*.

**Quality of Interactions (final-year, higher).** Final-year respondents rated
three relationship types as better than the Ontario average: *academic
advisors*, *student services staff*, and *administrative staff and offices*.

## Caveats and Methodological Notes

**Effect sizes are small.** All statistically significant Carleton-vs-Ontario
differences in 2023 had effect sizes < 0.3. The source PDF explicitly
characterizes these as "small differences in practical terms." When reporting
direction, the agent should not imply large gaps. A useful default phrasing:
*"slightly lower than Ontario, statistically significant but small in
practical terms."*

**Statistical vs practical significance.** "Statistically significant" means
p < .05 with NSSE's standard testing. It does **not** mean the difference is
meaningful in everyday terms. Always pair the direction with the effect-size
caveat when answering.

**Composite-score interpretation.** Indicator scores are designed for
benchmarking across institutions and across time, not for absolute
interpretation. A score of 30 is not "fair"; it is "what 30 means on this
indicator's specific item composition." Avoid imposing intuitive grade-like
interpretations on the 0–60 scale.

**Triennial cadence.** Carleton runs NSSE every three years. Year-over-year
trends are at the three-year cadence; do not interpolate or imply annual
trends.

**Response rate (2023).** 21% overall, with 1,090 first-year and 940 final-year
respondents. Lower than 2020. Apply the same uncertainty caveats noted in
`overall_experience_rating.md`.

**Gender weighting.** All published indicator scores are gender-weighted by
NSSE to align with each institution's actual gender distribution.

## Confidence Tier Guidance

- **High confidence.**
  - Direction of 2023 Carleton-vs-Ontario difference for any of the ten
    indicators (lower, higher, no difference) → look up.
  - 2020-vs-2023 point values and direction for the seven indicator-cohort
    pairs in the verified store → look up.
  - Item-level qualitative drivers for the statistically significant
    differences listed above.

- **Medium confidence.**
  - Synthesizing across multiple indicators ("how does Carleton perform on the
    academic challenge theme overall in 2023").
  - Characterizing trend trajectory using the verified 2020/2023 pairs.
  - Interpreting Carleton's pattern of strengths (Effective Teaching Practices,
    Quality of Interactions for final-year) versus areas of weakness
    (Collaborative Learning, Student-Faculty Interaction).

- **Low confidence — refuse or hedge strongly.**
  - **Faculty-level breakdowns** of indicator scores. NSSE summaries do not
    publish indicator scores by Carleton faculty.
  - **Point values** for indicator-cohort-year combinations not in the
    verified store.
  - **Pre-2020 trends** not yet extracted.
  - **Causal attribution.** "Why is Collaborative Learning lower at Carleton?"
    — the source PDF does not answer this; the agent should not speculate.
  - **Forecasting** future indicator scores.
  - **Recomputing** indicator scores from item-level data.

## Related KPIs

- `overall_experience_rating` — NSSE's headline overall-satisfaction question;
  a different construct from indicator scores. Often asked together.
- `would_choose_same_institution_pct` — companion overall NSSE question.
- `nsse_high_impact_practices` — separate NSSE construct (HIPs participation
  rates), not an engagement indicator.
- `quality_of_interactions_items` — the underlying item-level data feeding the
  Quality of Interactions indicator. NSSE 2023 Figures 7–8.
- `nsse_obstacles_to_progress` — separate Ontario-consortium-specific items.

## Glossary References

- **Engagement Indicator** — NSSE composite score (0–60) bundling related
  survey items under one of ten themes.
- **Theme** — One of four NSSE-defined groupings (Academic Challenge,
  Learning with Peers, Experiences with Faculty, Campus Environment).
- **Effect size** — Magnitude of a statistical difference, distinct from
  whether the difference is statistically significant. NSSE's reported
  Carleton-vs-Ontario effect sizes in 2023 were all < 0.3 (small).
- **Statistical significance** — In OIRP NSSE reporting, p < .05.
- **Ontario consortium (rest of)** — Consortium total *excluding* Carleton, used
  as the comparison group for both descriptive and statistical-testing
  purposes.

## Change Log

| Date       | Change                                                | Reviewer |
| ---------- | ----------------------------------------------------- | -------- |
| 2026-04-27 | Initial draft from `nsse_2023_summary.pdf` (2023 + 2020-2023 deltas) | (you) |
