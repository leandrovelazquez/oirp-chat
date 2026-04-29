---
kpi_id: nsse_high_impact_practices
domain: student_engagement
source_survey: NSSE
metric_type: participation_rate_with_crosstab
status: verified
last_reviewed: 2026-04-27
owner: oirp-chat (portfolio project)
---

# NSSE High-Impact Practices (HIPs)

## Definition

NSSE defines **High-Impact Practices (HIPs)** as enriching educational
experiences that *"typically demand considerable time and effort, facilitate
learning outside of the classroom, require meaningful interactions with faculty
and other students, encourage collaboration with diverse other students, and
provide frequent and substantive feedback."*

The instrument tracks **six HIPs**:

| HIP                              | First-Year | Final-Year |
| -------------------------------- | :--------: | :--------: |
| Learning Community               |     ✓      |     ✓      |
| Service Learning                 |     ✓      |     ✓      |
| Research with Faculty            |     ✓      |     ✓      |
| Internship or Field Experience   |            |     ✓      |
| Study Abroad                     |            |     ✓      |
| Culminating Senior Experience    |            |     ✓      |

Three are tracked for first-year students; all six for final-year students.
NSSE's stated benchmark goal is for all students to have **participated in at
least two HIPs by the time they graduate**.

The metric reports, for each HIP, the **percentage of respondents who
participated** (or who report at least some participation, in the case of
Service Learning).

## Calculation

```
hip_participation_pct[hip, cohort]
  = (respondents who indicated "Done or in progress" for that HIP)
    / (total respondents in cohort)
```

**Service Learning exception.** Service Learning is reported as percentage who
indicated *"at least some"* service learning, not "Done or in progress." Do
not apply the standard formula to this HIP — use the published value.

**Aggregate metrics.**
- *Participated in at least one HIP* — share of cohort with ≥ 1 HIP.
- *Participated in two or more HIPs* — share of cohort with ≥ 2 HIPs;
  reported only for final-year (the NSSE benchmark target).

Institutional results are gender-weighted by NSSE before publication.

## Synonyms

- "HIPs" / "high-impact practices"
- "experiential learning" (NSSE-grounded; see disambiguation)
- "research with faculty" / "undergraduate research"
- "internship participation" / "co-op participation" (NSSE-grounded)
- "study abroad" / "international experience"
- "service learning" / "community-engaged learning"
- "capstone" / "culminating experience" / "senior project"
- "learning community"

**Disambiguation.** "Experiential learning" is broader than NSSE HIPs —
Carleton has experiential-learning frameworks and reporting outside NSSE. If
the user is asking about institutional experiential-learning programs,
co-curricular records, or specific co-op enrolment, this metric is **not** the
right answer. Similarly, "internship participation" in this metric means
self-reported internship/field experience on the NSSE survey — not actual
institutional co-op enrolment data, which lives elsewhere.

## Source Documents

| Survey Year | Source File              | Location                                         |
| ----------- | ------------------------ | ------------------------------------------------ |
| 2023        | `nsse_2023_summary.pdf`  | "High-Impact Practices", Tables 4–6, p. 11–13   |
| 2020        | `nsse_2020_summary.pdf`  | "High-Impact Practices" section                  |
| 2017        | `nsse_2017_summary.pdf`  | "High-Impact Practices" section                  |

## Verified Values

### 2023 — Carleton vs Ontario by HIP

```json
[
  {
    "year": 2023,
    "cohort": "first_year",
    "hip": "learning_community",
    "carleton_pct": 7,
    "ontario_pct": 9,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "hip": "service_learning",
    "carleton_pct": 41,
    "ontario_pct": 44,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "hip": "research_with_faculty",
    "carleton_pct": 4,
    "ontario_pct": 3,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "first_year",
    "hip": "participated_in_at_least_one",
    "carleton_pct": 45,
    "ontario_pct": 49,
    "statistically_significant_diff": true,
    "diff_direction_carleton_vs_ontario": "lower",
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },

  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "learning_community",
    "carleton_pct": 14,
    "ontario_pct": 17,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "service_learning",
    "carleton_pct": 37,
    "ontario_pct": 49,
    "statistically_significant_diff": true,
    "diff_direction_carleton_vs_ontario": "lower",
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "research_with_faculty",
    "carleton_pct": 27,
    "ontario_pct": 21,
    "statistically_significant_diff": true,
    "diff_direction_carleton_vs_ontario": "higher",
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "internship_or_field_experience",
    "carleton_pct": 44,
    "ontario_pct": 48,
    "statistically_significant_diff": true,
    "diff_direction_carleton_vs_ontario": "lower",
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "study_abroad",
    "carleton_pct": 5,
    "ontario_pct": 6,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "culminating_senior_experience",
    "carleton_pct": 46,
    "ontario_pct": 33,
    "statistically_significant_diff": true,
    "diff_direction_carleton_vs_ontario": "higher",
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "participated_in_at_least_one",
    "carleton_pct": 79,
    "ontario_pct": 81,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "hip": "participated_in_two_or_more",
    "carleton_pct": 51,
    "ontario_pct": 51,
    "statistically_significant_diff": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 11, "table": "Table 4" }
  }
]
```

### 2023 — Carleton Final-Year by Program Length (Cross-Tab)

A useful cross-tabulation: "final-year" at Carleton blends third-year students
in three-year programs with fourth-year students in four-year programs. The
two groups participate in HIPs at very different rates.

```json
[
  {
    "year": 2023,
    "cohort": "final_year",
    "program_length": "three_year",
    "hip_participation": {
      "learning_community": 7,
      "service_learning": 24,
      "research_with_faculty": 3,
      "internship_or_field_experience": 14,
      "study_abroad": 5,
      "culminating_senior_experience": 3,
      "participated_in_at_least_one": 39,
      "participated_in_two_or_more": 12
    },
    "source": { "file": "nsse_2023_summary.pdf", "page": 12, "table": "Table 5" }
  },
  {
    "year": 2023,
    "cohort": "final_year",
    "program_length": "four_year",
    "hip_participation": {
      "learning_community": 15,
      "service_learning": 39,
      "research_with_faculty": 29,
      "internship_or_field_experience": 46,
      "study_abroad": 5,
      "culminating_senior_experience": 50,
      "participated_in_at_least_one": 82,
      "participated_in_two_or_more": 55
    },
    "source": { "file": "nsse_2023_summary.pdf", "page": 12, "table": "Table 5" }
  }
]
```

> **Note on three-year vs four-year program differences.** Differences between
> 3-year and 4-year programs are statistically significant for every HIP
> *except* Learning Community and Study Abroad. Three-year-program final-year
> students participate in HIPs at rates closer to first-year students than to
> four-year-program final-year students. When reporting Carleton's final-year
> HIPs aggregate, the agent should be ready to disaggregate by program length
> if the user wants accuracy.

### 2020 vs 2023 — Carleton Year-over-Year

```json
[
  {
    "cohort": "first_year",
    "hip": "learning_community",
    "value_2020": 7,
    "value_2023": 7,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "first_year",
    "hip": "service_learning",
    "value_2020": 39,
    "value_2023": 41,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "first_year",
    "hip": "research_with_faculty",
    "value_2020": 2,
    "value_2023": 4,
    "statistically_significant_change": true,
    "direction": "increase",
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "first_year",
    "hip": "participated_in_at_least_one",
    "value_2020": 43,
    "value_2023": 45,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "learning_community",
    "value_2020": 13,
    "value_2023": 14,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "service_learning",
    "value_2020": 39,
    "value_2023": 37,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "research_with_faculty",
    "value_2020": 26,
    "value_2023": 27,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "internship_or_field_experience",
    "value_2020": 43,
    "value_2023": 44,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "study_abroad",
    "value_2020": 7,
    "value_2023": 5,
    "statistically_significant_change": true,
    "direction": "decrease",
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" },
    "interpretive_note": "OIRP attributes the decrease to the pandemic and travel restrictions during the 2020 reference period."
  },
  {
    "cohort": "final_year",
    "hip": "culminating_senior_experience",
    "value_2020": 45,
    "value_2023": 46,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "participated_in_at_least_one",
    "value_2020": 80,
    "value_2023": 79,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  },
  {
    "cohort": "final_year",
    "hip": "participated_in_two_or_more",
    "value_2020": 52,
    "value_2023": 51,
    "statistically_significant_change": false,
    "source": { "file": "nsse_2023_summary.pdf", "page": 13, "table": "Table 6" }
  }
]
```

## Headline Findings (2023)

The agent should reach for these as the canonical summary when a user asks
"how does Carleton do on HIPs":

1. **Where there are differences from Ontario, Carleton is more often *lower***
   — particularly Service Learning (final-year) and Internship/Field Experience.
2. **Two notable strengths.** Carleton final-year students participate in
   *Research with Faculty* and *Culminating Senior Experience* at
   statistically significantly higher rates than the Ontario consortium.
3. **NSSE's two-HIP benchmark is met by 51% of Carleton final-year students** —
   identical to the Ontario consortium average.
4. **Year-over-year change has been minimal.** Two statistically significant
   shifts since 2020: first-year Research with Faculty up (2% → 4%), and
   final-year Study Abroad down (7% → 5%, attributed to pandemic-era travel
   restrictions in the 2020 reference period).
5. **Program length matters more than cohort year for HIPs.** Final-year
   students in three-year programs look much more like first-year students
   than like four-year final-year students.

## Caveats and Methodological Notes

**Self-report.** All HIP participation is self-reported on the NSSE
instrument. It is not validated against institutional records (e.g., actual
co-op enrolment, registrar records of capstone courses). Treat as student
perception of participation, which can over- or under-state institutional
reality.

**Service Learning measurement difference.** Service Learning is the only HIP
reported as "at least some" rather than "Done or in progress." When comparing
across HIPs, this is a small inconsistency worth flagging if the user is doing
fine-grained comparison.

**First-year HIP feasibility.** Several HIPs (internships, study abroad,
capstones) are structurally unavailable to first-year students. NSSE only
asks first-years about three HIPs for this reason. Do not interpret the
absence of those values as low first-year participation.

**Effect sizes.** As with all NSSE Carleton-vs-Ontario comparisons in 2023,
effect sizes are small (< 0.3). Statistically significant ≠ practically large.

**Final-year cohort composition.** "Final-year" blends third-year (3-year
programs, 8% of 2023 final-year respondents) and fourth-year (4-year programs,
92%). When reporting *aggregate* final-year HIP rates, the four-year group
dominates the average. When questions are about HIP design or program-level
patterns, the cross-tab in Table 5 is the more honest answer.

**Triennial cadence.** Carleton runs NSSE every three years. "Year-over-year"
in this file means three-year-over-three-year, not annual.

**Response rate (2023).** 21%. See `methodology_notes.md` for general NSSE
response-rate context.

## Confidence Tier Guidance

- **High confidence.**
  - Carleton 2023 participation rate for any of the six HIPs, by cohort →
    look up.
  - Aggregate 2023 metrics (at-least-one, two-or-more) → look up.
  - Carleton vs Ontario directional comparison and statistical significance for
    2023 → look up.
  - Carleton 3-year-program vs 4-year-program HIP rates for 2023 final-year →
    look up.
  - 2020-vs-2023 verified Carleton year-over-year values and significance.

- **Medium confidence.**
  - Synthesizing across HIPs to characterize Carleton's overall HIPs profile.
  - Interpreting why aggregate final-year HIP rates look the way they do
    using the program-length cross-tab.
  - Trend characterization beyond 2020-vs-2023 (would need values from
    pre-2020 source PDFs not yet extracted).
  - Comparing HIPs participation to NSSE's two-HIP benchmark goal.

- **Low confidence — refuse or hedge strongly.**
  - **Faculty-level breakdowns of HIP participation.** NSSE summaries do not
    publish HIPs by Carleton faculty.
  - **Mapping NSSE HIP self-reports to institutional records** (co-op
    enrolment, capstone-course registration). These are different data sources
    measuring different things.
  - **Causal claims** about why Carleton is higher or lower than Ontario on
    any specific HIP.
  - **Forecasting** future HIP participation.
  - **Inferring program-design recommendations** ("Carleton should add more
    internships") — the data describes participation, not the optimal
    intervention.

## Related KPIs

- `nsse_engagement_indicators` — composite indicator scores; HIPs are a
  separate NSSE construct, **not** an engagement indicator. Do not conflate.
- `overall_experience_rating` — overall NSSE satisfaction; sometimes
  contextualized using HIPs participation.
- `would_choose_same_institution` — companion overall-satisfaction question.
- *(Future KPIs)*: institutional co-op enrolment, capstone-course completion
  rate — non-NSSE behavioural analogues that should not be conflated with
  these self-report measures.

## Glossary References

- **HIP (High-Impact Practice)** — NSSE-defined category of enriching
  educational experience. Six are tracked on the survey.
- **Done or in progress** — NSSE response option indicating the respondent
  has either completed or is currently engaged in the HIP. The standard
  numerator for HIP participation rates (except Service Learning).
- **Two-HIP benchmark** — NSSE's stated goal that all students participate in
  at least two HIPs by graduation.
- **Three-year vs four-year programs** — Two undergraduate program structures
  at Carleton. Three-year programs typically lead to a general bachelor's;
  four-year programs to an honours bachelor's. HIP participation rates differ
  substantially between the two.

## Change Log

| Date       | Change                                                    | Reviewer |
| ---------- | --------------------------------------------------------- | -------- |
| 2026-04-27 | Initial draft from `nsse_2023_summary.pdf` (Tables 4–6)   | (you)    |
