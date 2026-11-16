# Eval run 2026-11-14-1754 · claude-sonnet-5-5 · effort medium

| | |
|---|---|
| Answerable questions passed | 24/29 (83%) (bar 90%: **no**) |
| Refusals passed | 8/9 (89%) (bar 100%: **no**) |
| Answers with unverified numbers | 0 (bar 0: yes) |
| Number-check rewrites | 16 |
| Tool calls per question (mean) | 1.1 |
| Latency p50 / p95 | 5.3 s / 10.0 s (bar 45 s: yes) |
| Tokens | requests 88, input_tokens 96,198, output_tokens 26,310, cache_creation_input_tokens 0, cache_read_input_tokens 5,481,256 |
| Estimated cost | $1.00 |

| Question | Result | Why it failed |
|---|---|---|
| `high_overall_2023_first_year` | pass |  |
| `high_overall_2023_final_year` | pass |  |
| `high_choose_again_distribution_first_year` | pass |  |
| `high_engagement_effective_teaching` | pass |  |
| `high_hips_research_with_faculty_final_year` | pass |  |
| `high_hips_program_length_crosstab` | **fail** | facts: missing: 3-year; 4-year |
| `high_hips_yoy_study_abroad` | pass |  |
| `high_engagement_yoy_collaborative_first_year` | pass |  |
| `high_retention_legacy_2000` | pass |  |
| `medium_what_is_aopa_equivalent` | **fail** | confidence: got high, expected medium; facts: missing: lower or equal |
| `medium_nsse_methodology` | **fail** | confidence: got high, expected medium |
| `medium_ontario_consortium` | **fail** | confidence: got high, expected medium |
| `medium_engagement_indicator_explanation` | **fail** | facts: missing: 0-60 |
| `medium_enrolment_size_qualitative` | pass |  |
| `medium_carleton_carleton_distinction` | pass |  |
| `real_then_synthetic_2022_cohort` (refusal) | pass |  |
| `real_then_synthetic_faculty_retention` (refusal) | pass |  |
| `real_then_synthetic_fpa_headcount` (refusal) | pass |  |
| `low_refuse_overall_experience_by_faculty` (refusal) | **fail** | confidence: got none, expected low/medium; kpi: overall_experience_rating not looked up; facts: missing: not |
| `low_refuse_causal_claim` (refusal) | pass |  |
| `multistep_satisfaction_summary` | pass |  |
| `multistep_engagement_strengths_weaknesses` | pass |  |
| `multistep_enrolment_trajectory` | pass |  |
| `discovery_what_can_you_answer` | pass |  |
| `wh_retention_by_entry_faculty` | pass |  |
| `wh_enrolment_counting_base` | pass |  |
| `wh_enrolment_needs_a_term` | pass |  |
| `wh_faculty_weighted` | pass |  |
| `wh_admissions_funnel` | pass |  |
| `wh_suppression` | pass |  |
| `wh_no_mixing_layers` (refusal) | pass |  |
| `discovery_out_of_scope` (refusal) | pass |  |
| `ref_person` (refusal) | pass |  |
| `ref_no_data_staff` (refusal) | pass |  |
| `wh_compare_change` | pass |  |
| `wh_compare_share` | pass |  |
| `wh_preliminary_fall_2026` | pass |  |
| `wh_preliminary_retention_2025` | pass |  |
