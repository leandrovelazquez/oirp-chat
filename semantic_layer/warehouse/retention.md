---
cube_id: retention
cube: Retention
domain: student_outcomes
star: RETENTION
fact_table: URET_FACT
data_origin: synthetic
status: synthetic
last_reviewed: 2026-11-12
---

# Retention cube (synthetic warehouse)

> **SYNTHETIC DATA.** Every number this cube returns is generated demo data.
> The structure (table names, columns, grain, measures, MDX formulas) mirrors
> the institutional-research warehouse's undergraduate retention star; the
> values do not describe any real student or any real institution. Never
> present a value from this cube as Carleton's actual retention rate, and never
> compare it numerically with the *published* retention figures in
> `first_year_retention_rate`.

## Definition

Tracks every new undergraduate entering cohort (new entrants in a fall term,
full- and part-time, including transfer and mature entrants) through each
following academic year: are they still registered, have they graduated, or
have they stopped out?

## Grain

`URET_FACT` holds **one row per student per academic year since entry**.
`YEARS` ("Years After") is 0 in the entry year, 1 the next year, and so on.
`COUNT` is 1 on every row, so **`Cohort` = Sum(COUNT) is the cohort size at
any single Years After**.

Consequences the agent must respect:

- **Always fix Years After.** Summing across Years After counts each student
  once per year tracked, which is meaningless. The engine refuses a query that
  doesn't filter Years After to one value or group by it.
- **At Years After = 0 every student is Continuing** (Cohort = Continuing =
  Persisting, Graduating = 0). That is expected, not a data fault; it happens to
  the newest cohort every year.
- **Graduating is cumulative.** At Years After = 6, Graduating counts everyone
  who has graduated by then, not just in that year.
- The cohort window is **2011–2026** (`URET_COHORT`). The current academic
  year is 2026/27, so the newest cohort with a year-1 outcome is **2025**;
  cohort 2026 has only Years After = 0.

## Answer recipes

| Question | Measures | Filters / by |
|---|---|---|
| First-year retention rate, cohort X | `% Continuing` | Cohort = X, Years After = 1 |
| Two-year retention, cohort X | `% Continuing` (or `% Continuing or Graduating`) | Cohort = X, Years After = 2 |
| Graduation rate within N years | `% Graduating` | Cohort = X, Years After = N |
| Retention trend over cohorts | `% Continuing` | Years After = 1, by Cohort |
| By entry faculty | `% Continuing` | Years After = 1, by `1st Academic Unit.Faculty` |
| By current/last faculty | `% Continuing` | by `Last Academic Unit.Faculty` (see caveat) |
| International vs domestic | `% Continuing` | by `Region.Category` (International vs Canadian categories) |
| By entrance average | `% Continuing` | by `HS Avg` |
| Full-time vs part-time | `% Continuing` | by `Full-Partime` |
| "Full-time first-year (FTFY)" style rate | `% Continuing` | Full-Partime = Full-time, Application Type = Direct from secondary school, Years After = 1 |
| Stop-out vs temporary absence | `% Stopout`, `% Persisting` | Years After = N |
| First-year academic performance | `GPA1`, `% DFW`, `% Fail` | Years After = 0 |

**Which faculty?** For cohort retention the standard attribution is the
**entry** unit (`1st Academic Unit`). `Last Academic Unit` is the unit at the
student's most recent registration; using it makes faculties that students
switch *into* look better retained. Say which one you used.

## Measures (mirroring the Retention cube)

- **Cohort** — Sum(COUNT): students in the cohort.
- **Continuing** — Sum(CONTINUE): registered in that academic year.
- **Graduating** — Sum(GRADUATE): graduated by that academic year (cumulative).
- **Stopout** — Sum(STOPOUT): neither registered nor graduated that year.
- **Persisting** — Sum(CONTSTAR): registered that year, *or* not registered
  that year but registers again later (a temporary stop-out). For recent years
  this equals Continuing, because a later return can't have happened yet.
- Calculated members, ported from the cube's MDX: `% Continuing`,
  `% Graduating`, `% Stopout`, `% Continuing or Graduating`, `% Persisting`,
  `% Persisting or Graduating`, `GPA1`, `GPA2`, `% Fail`, `% WDN`, `% DFW`,
  `HS Avg`.

GPA is on a 12-point scale. `GPA1` is the credit-weighted GPA for that academic
year; `GPA2` is cumulative to that year.

## Freshness

The retention star is loaded by a separate pipeline from enrolment and
admissions. **In this demo it is deliberately loaded about three weeks behind
the other stars**, the way the real retention star can fall behind when its
pipeline isn't scheduled. Every query result carries `data_as_of` and `stale`;
when `stale` is true, say so and give the as-of date.

## Caveats

- **Synthetic.** See the banner at the top.
- **Small cells are suppressed.** Fewer than 10 students in a cell → the values
  come back null with `suppressed: true`. Say a value is suppressed; never
  estimate it.
- **Retention is not progression.** This cube measures staying registered, not
  advancing a year level. `Student Level` shows year level while registered.
- **No causal claims.** The cube shows who stayed, not why.

## Cube model

```json
{
  "cube": "Retention",
  "star": "RETENTION",
  "description": "Undergraduate entering cohorts tracked year by year: continuing, graduated, stopped out. SYNTHETIC data.",
  "freshness_sla_days": 7,
  "min_cell_size": 10,
  "measure_groups": {
    "URET FACT": {
      "fact_table": "URET_FACT",
      "person_key": "PIDM",
      "required_single": [
        {"dimension": "Years After", "why": "every student has one row per year tracked, so totals across Years After are meaningless."}
      ],
      "measures": {
        "Cohort":      {"agg": "sum", "column": "COUNT",    "unit": "students", "ssas": "Sum(URET_FACT.COUNT)", "description": "Students in the cohort."},
        "Continuing":  {"agg": "sum", "column": "CONTINUE", "unit": "students", "ssas": "Sum(URET_FACT.CONTINUE)", "description": "Registered in that academic year."},
        "Graduating":  {"agg": "sum", "column": "GRADUATE", "unit": "students", "ssas": "Sum(URET_FACT.GRADUATE)", "description": "Graduated by that academic year (cumulative)."},
        "Stopout":     {"agg": "sum", "column": "STOPOUT",  "unit": "students", "ssas": "Sum(URET_FACT.STOPOUT)", "description": "Neither registered nor graduated."},
        "Continuing or Graduating": {"agg": "sum", "column": "CONTGRAD", "unit": "students", "ssas": "Sum(URET_FACT.CONTGRAD)"},
        "Persisting":  {"agg": "sum", "column": "CONTSTAR", "unit": "students", "ssas": "Sum(URET_FACT.CONTSTAR)", "description": "Registered, or a temporary stop-out who returns later."},
        "Persisting or Graduating": {"agg": "sum", "column": "CONTSTGR", "unit": "students", "ssas": "Sum(URET_FACT.CONTSTGR)"},
        "Number of Fs":   {"agg": "sum", "column": "NFAIL", "unit": "courses", "ssas": "Sum(URET_FACT.NFAIL)"},
        "Number of WDNs": {"agg": "sum", "column": "NWDN",  "unit": "courses", "ssas": "Sum(URET_FACT.NWDN)"},
        "Number of DFWs": {"agg": "sum", "column": "NDFW",  "unit": "courses", "ssas": "Sum(URET_FACT.NDFW)"},
        "NCRS":   {"agg": "sum", "column": "NCRS",   "unit": "courses", "ssas": "Sum(URET_FACT.NCRS)"},
        "NCRED1": {"agg": "sum", "column": "NCRED1", "unit": "credits", "ssas": "Sum(URET_FACT.NCRED1)"},
        "XGPA1":  {"agg": "sum", "column": "XGPA1",  "unit": "points",  "ssas": "Sum(URET_FACT.XGPA1)"},
        "NCRED2": {"agg": "sum", "column": "NCRED2", "unit": "credits", "ssas": "Sum(URET_FACT.NCRED2)"},
        "XGPA2":  {"agg": "sum", "column": "XGPA2",  "unit": "points",  "ssas": "Sum(URET_FACT.XGPA2)"},
        "XOAVE":  {"agg": "sum", "column": "XOAVE",  "unit": "points",  "ssas": "Sum(URET_FACT.XOAVE)"},
        "NOAVE":  {"agg": "sum", "column": "NOAVE",  "unit": "students", "ssas": "Sum(URET_FACT.NOAVE)"}
      },
      "calculated": {
        "% Continuing": {"numerator": ["Continuing"], "denominator": "Cohort", "unit": "percent", "mdx": "[Measures].[Continuing]/[Measures].[Cohort]"},
        "% Graduating": {"numerator": ["Graduating"], "denominator": "Cohort", "unit": "percent", "mdx": "[Measures].[Graduating]/[Measures].[Cohort]"},
        "% Stopout":    {"numerator": ["Stopout"],    "denominator": "Cohort", "unit": "percent", "mdx": "[Measures].[Stopout]/[Measures].[Cohort]"},
        "% Continuing or Graduating": {"numerator": ["Continuing", "Graduating"], "denominator": "Cohort", "unit": "percent", "mdx": "([Measures].[Continuing]+[Measures].[Graduating])/[Measures].[Cohort]"},
        "% Persisting": {"numerator": ["Persisting"], "denominator": "Cohort", "unit": "percent", "mdx": "[Measures].[Persisting]/[Measures].[Cohort]"},
        "% Persisting or Graduating": {"numerator": ["Persisting", "Graduating"], "denominator": "Cohort", "unit": "percent", "mdx": "([Measures].[Persisting]+[Measures].[Graduating])/[Measures].[Cohort]"},
        "GPA1":   {"numerator": ["XGPA1"], "denominator": "NCRED1", "unit": "gpa_12pt", "mdx": "IIF([Measures].[NCRED1]>0,[Measures].[XGPA1]/[Measures].[NCRED1],NULL)"},
        "GPA2":   {"numerator": ["XGPA2"], "denominator": "NCRED2", "unit": "gpa_12pt", "mdx": "IIF([Measures].[NCRED2]>0,[Measures].[XGPA2]/[Measures].[NCRED2],NULL)"},
        "% Fail": {"numerator": ["Number of Fs"],   "denominator": "NCRS", "unit": "percent", "mdx": "IIF([Measures].[NCRS]>0,[Measures].[Number of Fs]/[Measures].[NCRS],NULL)"},
        "% WDN":  {"numerator": ["Number of WDNs"], "denominator": "NCRS", "unit": "percent", "mdx": "IIF([Measures].[NCRS]>0,[Measures].[Number of WDNs]/[Measures].[NCRS],NULL)"},
        "% DFW":  {"numerator": ["Number of DFWs"], "denominator": "NCRS", "unit": "percent", "mdx": "IIF([Measures].[NCRS]>0,[Measures].[Number of DFWs]/[Measures].[NCRS],NULL)"},
        "HS Avg": {"numerator": ["XOAVE"], "denominator": "NOAVE", "unit": "average", "mdx": "IIF([Measures].[NOAVE]>0,[Measures].[XOAVE]/[Measures].[NOAVE],NULL)"}
      }
    }
  },
  "dimensions": {
    "Cohort":        {"fact_columns": {"URET FACT": "COHORT"},   "table": "URET_COHORT",   "key": "COHORT_KEY",   "label": "LABEL_DESC", "description": "Fall of entry (2011-2026)."},
    "Years After":   {"fact_columns": {"URET FACT": "YEARS"},    "table": "URET_YEARS",    "key": "YEARS_KEY",    "label": "LABEL_DESC", "description": "Academic years since entry; 0 = entry year."},
    "Academic Year": {"fact_columns": {"URET FACT": "ACADYEAR"}, "table": "URET_ACADYEAR", "key": "ACADYEAR_KEY", "label": "LABEL_DESC", "description": "Academic year observed, e.g. 2025/26 (key 2025)."},
    "1st Academic Unit": {"fact_columns": {"URET FACT": "FACADUNI"}, "table": "URET_FACADUNI", "key": "FACADUNI_KEY", "label": "LABEL_DESC",
                          "levels": {"Faculty": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}, "description": "Department of entry; level Faculty."},
    "2nd Academic Unit": {"fact_columns": {"URET FACT": "SACADUNI"}, "table": "URET_SACADUNI", "key": "SACADUNI_KEY", "label": "LABEL_DESC",
                          "levels": {"Faculty": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}, "description": "Department in second year (entry unit if not registered then)."},
    "Last Academic Unit": {"fact_columns": {"URET FACT": "LACADUNI"}, "table": "URET_LACADUNI", "key": "LACADUNI_KEY", "label": "LABEL_DESC",
                          "levels": {"Faculty": {"label": "LEVEL1_DESC", "key": "LEVEL1"}}, "description": "Department at most recent registration up to that year."},
    "Switch Academic Unit": {"fact_columns": {"URET FACT": "SWITCHA"}, "table": "URET_SWITCHA", "key": "SWITCHA_KEY", "label": "LABEL_DESC"},
    "Full-Partime":  {"fact_columns": {"URET FACT": "FTPTSTAT"}, "table": "URET_FTPTSTAT", "key": "FTPTSTAT_KEY", "label": "LABEL_DESC", "description": "Load at entry."},
    "HS Avg":        {"fact_columns": {"URET FACT": "AVG"},      "table": "URET_AVG",      "key": "AVG_KEY",      "label": "LABEL_DESC", "description": "Entrance (high school) average band."},
    "Gender":        {"fact_columns": {"URET FACT": "SEX"},      "table": "URET_SEX",      "key": "SEX_KEY",      "label": "LABEL_DESC"},
    "Age":           {"fact_columns": {"URET FACT": "AGE"},      "table": "URET_AGE",      "key": "AGE_KEY",      "label": "LABEL_DESC", "description": "Age band in the academic year observed."},
    "Application Type": {"fact_columns": {"URET FACT": "APPLTY"}, "table": "URET_APPLTY", "key": "APPLTY_KEY",   "label": "LABEL_DESC"},
    "OUAC Type":     {"fact_columns": {"URET FACT": "OUACTYPE"}, "table": "URET_OUACTYPE", "key": "OUACTYPE_KEY", "label": "LABEL_DESC"},
    "Region":        {"fact_columns": {"URET FACT": "REGION"},   "table": "URET_REGION",   "key": "REGION_KEY",   "label": "LABEL_DESC",
                      "levels": {"Category": {"label": "LEVEL1_DESC", "key": "LEVEL1"}},
                      "description": "Home region at entry. Category: Ottawa Area / Other Ontario / Other Canada / International."},
    "Retained":      {"fact_columns": {"URET FACT": "RETAINED"}, "table": "URET_RETAINED", "key": "RETAINED_KEY", "label": "LABEL_DESC", "description": "Whether the student was registered in second year (fixed per student)."},
    "Persisting":    {"fact_columns": {"URET FACT": "RETSTAR"},  "table": "URET_RETSTAR",  "key": "RETSTAR_KEY",  "label": "LABEL_DESC"},
    "Graduated within 7 years": {"fact_columns": {"URET FACT": "GRADSEVEN"}, "table": "URET_GRADSEVEN", "key": "GRADSEVEN_KEY", "label": "LABEL_DESC"},
    "Student Level": {"fact_columns": {"URET FACT": "LEVL"},     "table": "URET_LEVEL",    "key": "LEVEL_KEY",    "label": "LABEL_DESC", "description": "Year level while registered; Unknown when not registered."}
  }
}
```

## Related

- `first_year_retention_rate` (published layer) — the real, published figures
  and the definitions of the retention variants. Use it for "what does Carleton
  publish"; use this cube for analysis of the synthetic warehouse.
- `Enrolment` cube — the same students appear there term by term.
- `Admissions` cube — each cohort's registrants come from that year's
  applicant pool.
