---
kpi_id: overall_experience_rating
domain: student_engagement
source_survey: NSSE
status: verified
last_reviewed: 2026-04-27
owner: oirp-chat (portfolio project)
---

# Overall Educational Experience Rating (NSSE)

## Definition

The percentage of NSSE respondents who rated their entire educational experience
at Carleton as either **"Good"** or **"Excellent"** on a four-point scale
(Excellent / Good / Fair / Poor). Reported separately for **first-year** and
**final-year** undergraduate respondents.

This is one of NSSE's two headline overall-satisfaction questions. The other is
`would_choose_same_institution_pct` (see Related KPIs).

## Calculation

```
overall_experience_good_or_excellent_pct
  = (count of "Excellent" responses + count of "Good" responses)
    / (total respondents to the question, excluding non-applicable)
```

Institutional results are **gender-weighted** by NSSE before publication, to
correct for known female response bias. Both Carleton and Ontario consortium
figures in OIRP summaries are weighted; do not attempt to re-weight or combine
with unweighted samples.

## Synonyms

When a user asks any of the following, they almost certainly mean this metric:

- "overall satisfaction" (in NSSE context — see disambiguation below)
- "overall experience" / "overall experience rating"
- "how do students rate Carleton"
- "student satisfaction" (NSSE)
- "are students happy at Carleton" (NSSE-grounded answer)
- "good or excellent rating"
- "would they rate their experience well"

**Disambiguation.** "Student satisfaction" can also refer to CUSC's overall
satisfaction question or to program-exit surveys. Those are *different
instruments with different populations and scales* — do not conflate. If the
user does not specify a source, prefer NSSE for first-year/final-year
undergraduates and ask for clarification when ambiguous.

## Source Documents

| Survey Year | Source File                | Location                      |
| ----------- | -------------------------- | ----------------------------- |
| 2023        | `nsse_2023_summary.pdf`    | "Overall Experience", Figure 1, p. 5 |
| 2020        | `nsse_2020_summary.pdf`    | "Overall Experience" section  |
| 2017        | `nsse_2017_summary.pdf`    | "Overall Experience" section  |
| 2014        | `nsse_2014_summary.pdf`    | "Overall Experience" section  |
| 2011        | `nsse_2011_summary.pdf`    | "Overall Experience" section  |

(2020/2017/2014/2011 page references to be filled in as PDFs are ingested.)

## Verified Values

These are the canonical numbers. The agent should look these up via
`get_kpi_value()` rather than re-derive from prose. New values are added only
after a reviewer confirms them against the source PDF.

```json
[
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
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "carleton",
    "value_pct": 78,
    "metric_variant": "good_or_excellent",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "78% of final-year respondents rated their overall experience"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "value_pct": 73,
    "metric_variant": "good_or_excellent",
    "derivation_note": "Derived from Figure 1 stacked bar: 'Excellent' 20% + 'Good' 53% = 73%. The figure shows response categories Excellent/Good/Fair/Poor for Rest of Ontario first-year.",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "Rest of Ontario 20% 53% 23% 4%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "value_pct": 75,
    "metric_variant": "good_or_excellent",
    "derivation_note": "Derived from Figure 1 stacked bar: 'Excellent' 24% + 'Good' 51% = 75%. The figure shows response categories Excellent/Good/Fair/Poor for Rest of Ontario final-year.",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "Rest of Ontario 24% 51% 20% 5%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-27"
  }
]
```

### Response Distribution Detail (2023)

For users who ask about the full four-point response distribution
(Excellent / Good / Fair / Poor) rather than just the good_or_excellent
aggregate. Derived from Figure 1 chart-embedded values; reviewer-verified.

```json
[
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "carleton",
    "distribution": {
      "excellent_pct": 20,
      "good_pct": 55,
      "fair_pct": 23,
      "poor_pct": 3
    },
    "metric_variant": "full_distribution",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "Carleton 20% 55% 23% 3%"
    },
    "note": "Distribution sum (20+55+23+3 = 101%) reflects rounding in source figure; the prose-stated good_or_excellent aggregate of 74% in the companion record is authoritative over the chart-implied 75% (20+55).",
    "verified_by": "manual_review",
    "verified_on": "2026-04-30"
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "carleton",
    "distribution": {
      "excellent_pct": 22,
      "good_pct": 56,
      "fair_pct": 18,
      "poor_pct": 4
    },
    "metric_variant": "full_distribution",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "Carleton 22% 56% 18% 4%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-30"
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "distribution": {
      "excellent_pct": 20,
      "good_pct": 53,
      "fair_pct": 23,
      "poor_pct": 4
    },
    "metric_variant": "full_distribution",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "Rest of Ontario 20% 53% 23% 4%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-30"
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "comparison_group": "ontario_consortium_excl_carleton",
    "distribution": {
      "excellent_pct": 24,
      "good_pct": 51,
      "fair_pct": 20,
      "poor_pct": 5
    },
    "metric_variant": "full_distribution",
    "source": {
      "file": "nsse_2023_summary.pdf",
      "page": 5,
      "figure": "Figure 1",
      "quote_anchor": "Rest of Ontario 24% 51% 20% 5%"
    },
    "verified_by": "manual_review",
    "verified_on": "2026-04-30"
  }
]
```

> **Note for the agent.** Both Carleton and rest-of-Ontario consortium values
> for 2023 are now verified above (good_or_excellent aggregate plus the full
> four-point distribution). Carleton-vs-Ontario differences for 2023 were not
> statistically significant for either cohort. Where chart-embedded
> distributions sum to 101% (Carleton first-year), this is a rounding artifact
> of the source figure; the prose-stated good_or_excellent aggregate is
> authoritative.

## Comparison Context

NSSE results are reported alongside the average for the **rest of the Ontario
consortium** (i.e., Ontario consortium *excluding* Carleton, for both
descriptive and statistical-testing purposes).

In 2023, 19 Ontario universities participated as a consortium. The consortium
is a meaningful comparator because all Ontario universities operate under the
same provincial policy and funding framework. However, mission, program mix,
and the presence of three-year vs four-year undergraduate programs vary across
institutions and may explain some of the observed variation. **Differences
between Carleton and the consortium should not be interpreted as institutional
performance gaps without that context.**

## Caveats and Methodological Notes

**Response rate.** The 2023 response rate was **21%** (2,030 of ~9,700 invited
students), with 1,090 first-year and 940 final-year respondents. This is lower
than 2020 and lower than typical for NSSE administrations. Treat single-year
point estimates with appropriate uncertainty and prefer multi-year context when
characterizing change.

**Response bias.** Carleton respondents skew female (56% first-year, 61%
final-year in 2023). NSSE applies gender weighting to align with each
institution's actual gender distribution; published figures already reflect
this weighting.

**Statistical significance.** Per OIRP's reporting convention, differences are
flagged as "statistically significant" only where p < .05. Effect sizes in
2023 Carleton-vs-Ontario comparisons were small (typically < 0.3). The 2023
Carleton-vs-Ontario difference for **overall experience was not statistically
significant** for either cohort.

**Final-year cohort composition.** "Final-year" at Carleton blends third-year
students in three-year programs with fourth-year students in four-year
programs. In 2023, 8% of final-year respondents were in their third year and
92% in their fourth. Not all Ontario consortium institutions have three-year
programs, so cohort definition differs slightly across the comparison group.

**Trend characterization.** Across the 2017 / 2020 / 2023 administrations,
overall satisfaction has trended downward at Carleton for both cohorts, with a
parallel decline in Ontario overall. The 2020-to-2023 decrease for Carleton
**first-year** respondents was statistically significant. The 2014-to-2020
decline for Carleton **final-year** respondents was statistically significant,
with a small non-significant uptick in 2023.

## Confidence Tier Guidance

When the agent answers questions about this KPI, it should select a confidence
tier based on which path produced the answer:

- **High confidence.** Question maps directly to a verified value above
  (e.g., "What % of first-year students rated their experience good or excellent
  in 2023?" → look up → 74%).
- **Medium confidence.** Question requires synthesis across verified values,
  trend characterization supported by the source text, or qualitative
  Carleton-vs-Ontario framing per the prose in this file.
- **Low confidence — refuse or hedge strongly.** Examples:
  - Faculty-level breakdowns of overall experience (NSSE summaries do not
    publish overall-experience by faculty for Carleton).
  - Causal claims ("why did satisfaction drop").
  - Mixing this metric with non-NSSE satisfaction sources without explicit
    user direction.
  - Forecasts or predictions.

## Related KPIs

- `would_choose_same_institution_pct` — companion NSSE overall-satisfaction
  question, asked in the same administration. NSSE 2023 Figure 4.
- `quality_of_interactions_*` — five relationship-quality items (students,
  academic advisors, faculty, student services staff, administrative staff).
  NSSE 2023 Figures 7–8.
- `nsse_engagement_indicators_*` — ten thematic indicator scores grouped under
  Academic Challenge, Learning with Peers, Experiences with Faculty, and
  Campus Environment.
- `cusc_overall_satisfaction` — different survey, different population, **do
  not conflate**.

## Glossary References

- **NSSE** — National Survey of Student Engagement, administered by Indiana
  University's Center for Postsecondary Research. Carleton has participated in
  NSSE every three years; 2023 was the ninth Carleton administration.
- **Ontario consortium** — group of Ontario universities participating in NSSE
  in a coordinated administration. In 2023: 19 universities. In OIRP reporting,
  "rest of Ontario" = consortium *excluding* Carleton.
- **Comparison groups (verified-values field).** This file's
  `comparison_group` field uses two values: `carleton` (Carleton respondents
  only) and `ontario_consortium_excl_carleton` (rest-of-Ontario consortium
  average, excluding Carleton). Tool callers filtering by `comparison_group`
  must use these exact values.
- **First-year** — respondents in their first year of undergraduate study at
  Carleton at the time of survey.
- **Final-year** — respondents in their third year (three-year program) or
  fourth year (four-year program) of undergraduate study at Carleton at the
  time of survey.

## Change Log

| Date       | Change                                          | Reviewer |
| ---------- | ----------------------------------------------- | -------- |
| 2026-04-27 | Initial draft from `nsse_2023_summary.pdf`      | (you)    |
| 2026-04-30 | Added rest-of-Ontario 2023 values for first-year and final-year, drafted by `scripts/draft_kpi_values.py` and verified by manual review. | (you) |
| 2026-04-30 | Added Response Distribution Detail block with full four-point distributions (Carleton + Ontario, both cohorts) for 2023 from Figure 1; flagged the Carleton first-year 101% sum as a rounding artifact (prose-stated 74% authoritative). Added comparison_group glossary entry to clarify field vocabulary. Drafter-proposed at medium confidence; manually verified against source PDF Figure 1. | (you) |
