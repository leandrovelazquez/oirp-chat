---
cube_id: admissions
cube: Admissions
domain: admissions
star: ADMISSIONS
fact_table: ADM_FACT
data_origin: synthetic
status: synthetic
last_reviewed: 2026-11-12
---

# Admissions cube (synthetic warehouse)

> **SYNTHETIC DATA.** Every number this cube returns is generated demo data.
> The structure mirrors the warehouse's undergraduate admissions star
> (`ADM_FACT` and the `ADM_*` dimensions); the values describe no real
> applicant or institution.

## Definition

The undergraduate admissions funnel for each application year (fall intake
2016/17 to 2026/27): applicants → approved (offered) → confirmed (accepted)
→ registered.

## Grain and weighting

`ADM_FACT` holds **one row per application**. An applicant can hold several
applications to different programs, so each row carries
`WEIGHT = 1 / (applications held by that applicant)`:

- **Applicants** = Sum(WEIGHT) counts each applicant once in total, and splits
  them across programs when grouped by Program or Academic Unit.
- **Approved, Refused, Withdrawn, Declined, No answer** are weighted the same
  way (applicant-equivalents).
- **Confirmed** and **Registered** sit on the single application the applicant
  accepted, with value 1, so they count people.

Because of the weighting, "applicants to Engineering" means *applicant share
attributable to Engineering programs*, not "people who listed any Engineering
program". Say so when it matters.

## The funnel ratios (calculated members, ported from the cube's MDX)

| Measure | Definition | Reads as |
|---|---|---|
| `% Approved` | Approved / Applicants | offer rate |
| `% Confirmed` | Confirmed / Applicants | acceptance rate of all applicants |
| `% Registered` | Registered / Applicants | overall yield |
| `% Confirmed of Approved` | Confirmed / Approved | conversion of offers |
| `% Registered of Confirmed` | Registered / Confirmed | "melt" complement: confirmed who actually came |
| `HS Avg` | Weighted OAVE Sum / Sum OAVE Weights | mean entrance average of applicants with one |

## Answer recipes

| Question | Measures | Filters / by |
|---|---|---|
| How many applied for fall 2025? | `Applicants` | Application Year = 2025 |
| Full funnel, one year | `Applicants`, `Approved`, `Confirmed`, `Registered` | Application Year = 2025 |
| Yield by faculty | `% Registered`, `% Confirmed of Approved` | Application Year = …, by `Academic Unit.Faculty` |
| Applicant trend | `Applicants` | by Application Year |
| International applicants | `Applicants`, `% Registered` | by `Region.Category` |
| Does first choice matter? | `% Confirmed of Approved` | by Choice |
| Entrance averages | `HS Avg` | by Application Year or by Program |

## Required dimensions

- **Application Year** must be one value or grouped: pooling intake years is
  rarely what anyone means.
- **Timeframe** defaults to `F` (end of cycle). The real star also holds
  in-cycle snapshots; this synthetic one holds only the end-of-cycle view.

## Consistency with the other cubes

Registered applicants for application year *Y* are the new undergraduates of
fall *Y*: `Registered` here equals the Retention cube's `Cohort` at
Cohort = Y, Years After = 0, and the Enrolment cube's new-undergraduate
`Student Count` for Fall Y. (Cohorts before 2016 have no admissions rows.)

## Caveats

- **Synthetic.** See the banner.
- **Small cells are suppressed** (fewer than 10 distinct applicants).
- **Application counts are not applicant counts** — see the weighting above.
- The 2026/27 cycle is shown as complete in this synthetic set.

## Cube model

```json
{
  "cube": "Admissions",
  "star": "ADMISSIONS",
  "description": "Undergraduate admissions funnel by application year: applicants, offers, confirmations, registrations. SYNTHETIC data.",
  "freshness_sla_days": 7,
  "min_cell_size": 10,
  "roles": {"time": ["Application Year"], "time_say": "the {} intake",
            "trend": "Show the trend over the last five intakes.", "faculty": "Academic Unit.Faculty",
            "funnel": ["Applicants", "Approved", "Confirmed", "Registered"]},
  "measure_groups": {
    "ADM FACT": {
      "fact_table": "ADM_FACT",
      "person_key": "PIDM",
      "required_single": [
        {"dimension": "Timeframe", "default": "F", "why": "each timeframe is a separate snapshot of the same applications."},
        {"dimension": "Application Year", "why": "each intake year is a separate applicant pool."}
      ],
      "measures": {
        "Applicants": {"agg": "sum", "column": "WEIGHT", "unit": "applicants", "ssas": "Sum(ADM_FACT.WEIGHT)", "description": "Applicants, each counted once across their applications."},
        "Approved":   {"agg": "sum", "column": "APPR",   "unit": "applicants", "ssas": "Sum(ADM_FACT.APPR)", "description": "Offers (applicant-weighted)."},
        "Refused":    {"agg": "sum", "column": "REFU",   "unit": "applicants", "ssas": "Sum(ADM_FACT.REFU)"},
        "Withdrawn":  {"agg": "sum", "column": "WITD",   "unit": "applicants", "ssas": "Sum(ADM_FACT.WITD)"},
        "Declined":   {"agg": "sum", "column": "DECL",   "unit": "applicants", "ssas": "Sum(ADM_FACT.DECL)"},
        "No_Answer":  {"agg": "sum", "column": "NOAN",   "unit": "applicants", "ssas": "Sum(ADM_FACT.NOAN)"},
        "Confirmed":  {"agg": "sum", "column": "CONF",   "unit": "applicants", "ssas": "Sum(ADM_FACT.CONF)", "description": "Applicants who accepted an offer."},
        "Registered": {"agg": "sum", "column": "ATCU",   "unit": "applicants", "ssas": "Sum(ADM_FACT.ATCU)", "description": "Applicants who registered."},
        "Weighted OAVE Sum": {"agg": "sum", "column": "WOAVE", "unit": "points", "ssas": "Sum(ADM_FACT.WOAVE)"},
        "Sum OAVE Weights":  {"agg": "sum", "column": "OAVE_WEIGHT", "unit": "applicants", "ssas": "Sum(ADM_FACT.OAVE_WEIGHT)"}
      },
      "calculated": {
        "HS Avg":      {"numerator": ["Weighted OAVE Sum"], "denominator": "Sum OAVE Weights", "unit": "average", "mdx": "IIF([Measures].[Sum OAVE Weights]>0,[Measures].[Weighted OAVE Sum]/[Measures].[Sum OAVE Weights],NULL)"},
        "% Approved":  {"numerator": ["Approved"],   "denominator": "Applicants", "unit": "percent", "mdx": "IIF([Measures].[Applicants]>0,[Measures].[Approved]/[Measures].[Applicants],NULL)"},
        "% Confirmed": {"numerator": ["Confirmed"],  "denominator": "Applicants", "unit": "percent", "mdx": "IIF([Measures].[Applicants]>0,[Measures].[Confirmed]/[Measures].[Applicants],NULL)"},
        "% Registered":{"numerator": ["Registered"], "denominator": "Applicants", "unit": "percent", "mdx": "IIF([Measures].[Applicants]>0,[Measures].[Registered]/[Measures].[Applicants],NULL)"},
        "% Confirmed of Approved":  {"numerator": ["Confirmed"],  "denominator": "Approved",  "unit": "percent", "mdx": "IIF([Measures].[Approved]>0,[Measures].[Confirmed]/[Measures].[Approved],NULL)"},
        "% Registered of Confirmed":{"numerator": ["Registered"], "denominator": "Confirmed", "unit": "percent", "mdx": "IIF([Measures].[Confirmed]>0,[Measures].[Registered]/[Measures].[Confirmed],NULL)"}
      }
    }
  },
  "dimensions": {
    "Application Year": {"fact_columns": {"ADM FACT": "ACADYEAR"}, "table": "ADM_ACADYEAR", "key": "ACADYEAR_KEY", "label": "LABEL_DESC", "description": "Intake year, e.g. 2025/26 (key 2025 = fall 2025 intake)."},
    "Timeframe":   {"fact_columns": {"ADM FACT": "CNT"},      "table": "ADM_CNT",      "key": "CNT_KEY",      "label": "LABEL_DESC", "description": "Snapshot; F = end of cycle (default, only one present)."},
    "Academic Unit": {"fact_columns": {"ADM FACT": "ACADUNIT"}, "table": "ADM_ACADUNIT", "key": "ACADUNIT_KEY", "label": "LABEL_DESC",
                     "levels": {"Faculty": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}, "description": "Department of the program applied to; level Faculty."},
    "Program":     {"fact_columns": {"ADM FACT": "PROGRAM"},  "table": "ADM_PROGRAM",  "key": "PROGRAM_KEY",  "label": "LABEL_DESC",
                     "levels": {"Faculty": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}},
    "Choice":      {"fact_columns": {"ADM FACT": "CHOICE"},   "table": "ADM_CHOICE",   "key": "CHOICE_KEY",   "label": "LABEL_DESC", "description": "Rank of this program in the applicant's choices."},
    "OUAC Type":   {"fact_columns": {"ADM FACT": "OUACTYPE"}, "table": "ADM_OUACTYPE", "key": "OUACTYPE_KEY", "label": "LABEL_DESC"},
    "Application Type": {"fact_columns": {"ADM FACT": "APPTYPE"}, "table": "ADM_APPTYPE", "key": "APPTYPE_KEY", "label": "LABEL_DESC",
                     "levels": {"Category": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}},
    "HS Average":  {"fact_columns": {"ADM FACT": "AVG"},      "table": "ADM_AVG",      "key": "AVG_KEY",      "label": "LABEL_DESC"},
    "Region":      {"fact_columns": {"ADM FACT": "REGION"},   "table": "ADM_REGION",   "key": "REGION_KEY",   "label": "LABEL_DESC",
                     "levels": {"Category": {"label": "LEVEL1_DESC", "key": "LEVEL1"}},
                     "description": "Applicant home region; Category = Ottawa Area / Other Ontario / Other Canada / International."},
    "Country":     {"fact_columns": {"ADM FACT": "COUNTRY"},  "table": "ADM_COUNTRY",  "key": "COUNTRY_KEY",  "label": "LABEL_DESC",
                     "levels": {"Continent": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}, "description": "Country of citizenship."},
    "Applicant Gender": {"fact_columns": {"ADM FACT": "SEX"}, "table": "ADM_SEX",      "key": "SEX_KEY",      "label": "LABEL_DESC"},
    "Full Time - Part Time": {"fact_columns": {"ADM FACT": "FTPT"}, "table": "ADM_FTPT", "key": "FTPT_KEY",  "label": "LABEL_DESC"}
  }
}
```

## Related

- `Enrolment` cube — registrants appear there as new students.
- `Retention` cube — registrants form the cohort.
