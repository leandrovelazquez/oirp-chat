---
cube_id: enrolment
cube: Enrolment
domain: enrolment
star: ENROLMENT
fact_table: STDCOUNT, STDACADUNIT
data_origin: synthetic
status: synthetic
last_reviewed: 2026-11-12
---

# Enrolment cube (synthetic warehouse)

> **SYNTHETIC DATA.** Every number this cube returns is generated demo data.
> The structure mirrors the warehouse's enrolment star (`STDCOUNT`,
> `STDACADUNIT` and their dimensions); the values describe no real student or
> institution. Never present them as Carleton's actual enrolment, and never
> mix them with the *published* figures in `undergraduate_enrolment_by_faculty`.

## Definition

Registered students per term, at each **count date**, undergraduate and
graduate, with their load, level, fee status, citizenship, home region, age
and academic unit. Terms run from Fall 2016 to **Fall 2026** (the current
term; Winter 2027 hasn't started).

## Grain — two measure groups

| Measure group | Fact | One row per | Use for |
|---|---|---|---|
| **STDCOUNT** | `STDCOUNT` | student × term × count date | headcount, FTE, anything *not* by academic unit |
| **STDACADUNIT** | `STDACADUNIT` | student × term × count date × academic unit | anything **by department or faculty** |

A student in a combined program sits in two academic units with `WEIGHT` 0.5
each. That is why enrolment by unit uses **`Acadunit Weighted Count`**: it sums
the weights, so faculty totals add up to the headcount. `STDACADUNIT Count`
counts unit memberships and double-counts combined-program students. Prefer
the weighted count and say it's weighted.

Measures from different groups can't be combined in one query. Dimensions
belong to one or both groups (Academic Unit is STDACADUNIT-only; Student
Level, New - Returning, Full-Part Time, OUAC Type, Cohort, Entrance Average,
Application Type and Campus are STDCOUNT-only).

## Counting bases — the disambiguation that matters

- **Count Date** (`CNT`): `I` Initial, `P` Official count (snapshot date),
  `F` Final. **The engine defaults to `P`, the official count**, and reports
  that it did (`applied_defaults`). Fall 2026 has no `F` yet; the final count
  hasn't been taken.
- **Term**: always one term. The engine refuses a query that spans terms
  without grouping by `Time`. Fall and winter headcounts are different
  populations; never add them.
- **Headcount vs FTE**: `Student Count` is distinct students; `FTE` is
  load-weighted (a full course load in a term = 1.0). They differ — part-time
  students count fully in headcount and partially in FTE.
- **International**: two different definitions exist here.
  `Tuition Assessment` = fee status (Domestic / International tuition) — the
  usual meaning of "international students". `Citizenship` = country of
  citizenship; permanent residents pay domestic fees but have non-Canadian
  citizenship. Say which one you used.
- **Level**: `Student Level` = Undergraduate / Masters / Doctoral (level
  `Program Level` groups Masters + Doctoral as Graduate). "Students" without a
  level means everyone; ask or state it.

## Answer recipes

| Question | Measure group / measures | Filters / by |
|---|---|---|
| Undergraduate headcount, fall 2025 | STDCOUNT: `Student Count` | Time = Fall 2025, Student Level = Undergraduate |
| Same, full-time only | `Student Count` | + Full-Part Time = Full-time |
| FTE | `FTE` | Time = …, Student Level = … |
| New first-year intake | `Student Count` | Time = Fall YYYY, Student Level = Undergraduate, New - Returning = New |
| International share | `Student Count` | by Tuition Assessment |
| Headcount trend | `Student Count` | by Time, Time.Semester = Fall |
| Enrolment by faculty | STDACADUNIT: `Acadunit Weighted Count` | Time = …, by `Academic Unit.Faculty` |
| By department | `Acadunit Weighted Count` | by `Academic Unit` (optionally filter `Academic Unit.Faculty`) |

The Time dimension accepts the term code (`202530`) or label (`Fall 2025`);
`Time.Academic Year` (`2025/26`) and `Time.Semester` (`Fall`/`Winter`) are
levels.

## Measures (mirroring the Enrolment cube)

- **Student Count** — DistinctCount(STDCOUNT.PIDM).
- **Cumulative Student Count** — Count of STDCOUNT rows.
- **FTE** — Sum(STDCOUNT.FTE); **FFTE** — Sum(STDCOUNT.FFTE) (fiscal FTE,
  half-year weighted).
- **HS Avg** — calculated, `[OAVE-sum]/[OAVE-N]`.
- **Acadunit Weighted Count** — in the cube this is the MDX member
  `[Student Count]/[Cumulative Student Count]*[Acadunit Temp Weighted Count]`.
  Within one term and one count date the ratio is exactly 1 (one STDCOUNT row
  per student), so it equals Sum(STDACADUNIT.WEIGHT) — which is how it is
  computed here, with Term and Count Date forced single-valued.
- **Acadunit Weighted FTE** — Sum(STDACADUNIT.WFTE).
- **STDACADUNIT Count** — Count(STDACADUNIT.PIDM): unit memberships.

## Caveats

- **Synthetic.** See the banner.
- **Small cells are suppressed** (fewer than 10 distinct students).
- **Faculty of registration, not of teaching.** Academic Unit is the unit of
  the student's program, not where their courses are taught.
- **Count date matters.** Initial > Official > Final for the same term, because
  students drop before and after the official date.

## Cube model

```json
{
  "cube": "Enrolment",
  "star": "ENROLMENT",
  "description": "Registered students per term and count date: headcount, FTE, and weighted counts by academic unit. SYNTHETIC data.",
  "freshness_sla_days": 7,
  "min_cell_size": 10,
  "measure_groups": {
    "STDCOUNT": {
      "fact_table": "STDCOUNT",
      "person_key": "PIDM",
      "required_single": [
        {"dimension": "Count Date", "default": "P", "why": "the same student appears once per count date."},
        {"dimension": "Time", "why": "fall and winter (and different years) are different populations; FTE is per term."}
      ],
      "measures": {
        "Student Count": {"agg": "count_distinct", "column": "PIDM", "unit": "students", "ssas": "DistinctCount(STDCOUNT.PIDM)", "description": "Headcount: distinct students."},
        "Cumulative Student Count": {"agg": "count", "unit": "rows", "ssas": "Count(STDCOUNT rows)"},
        "FTE":  {"agg": "sum", "column": "FTE",  "unit": "fte", "ssas": "Sum(STDCOUNT.FTE)", "description": "Load-weighted count; full load in a term = 1.0."},
        "FFTE": {"agg": "sum", "column": "FFTE", "unit": "fte", "ssas": "Sum(STDCOUNT.FFTE)", "description": "Fiscal FTE (half-year weighted)."},
        "OAVE-N":   {"agg": "count_nonnull", "column": "OAVE", "unit": "students", "ssas": "Count(STDCOUNT.OAVE)"},
        "OAVE-sum": {"agg": "sum", "column": "OAVE", "unit": "points", "ssas": "Sum(STDCOUNT.OAVE)"}
      },
      "calculated": {
        "HS Avg": {"numerator": ["OAVE-sum"], "denominator": "OAVE-N", "unit": "average", "mdx": "IIF([OAVE-N]>0,[OAVE-sum]/[OAVE-N],NULL)"}
      }
    },
    "STDACADUNIT": {
      "fact_table": "STDACADUNIT",
      "person_key": "PIDM",
      "required_single": [
        {"dimension": "Count Date", "default": "P", "why": "the same student appears once per count date."},
        {"dimension": "Time", "why": "weighted counts are per term; different terms are different populations."}
      ],
      "measures": {
        "Acadunit Weighted Count": {"agg": "sum", "column": "WEIGHT", "unit": "students", "ssas": "[Measures].[Student Count]/[Measures].[Cumulative Student Count]*[Measures].[Acadunit Temp Weighted Count]  (= Sum(STDACADUNIT.WEIGHT) within one term and count date)", "description": "Headcount apportioned across academic units; units sum to the headcount."},
        "Acadunit Weighted FTE":   {"agg": "sum", "column": "WFTE", "unit": "fte", "ssas": "Sum(STDACADUNIT.WFTE)"},
        "STDACADUNIT Count":       {"agg": "count_nonnull", "column": "PIDM", "unit": "rows", "ssas": "Count(STDACADUNIT.PIDM)", "description": "Unit memberships; double-counts combined programs."}
      },
      "calculated": {}
    }
  },
  "dimensions": {
    "Time":        {"fact_columns": {"STDCOUNT": "TERM", "STDACADUNIT": "TERM"}, "table": "TIME", "key": "TIME_ID", "label": "TERM",
                    "levels": {"Academic Year": {"label": "ACADYEAR", "key": "ACADYEARKEY"}, "Semester": {"label": "SEMESTER", "key": "SEMESTERKEY"}},
                    "description": "Term, e.g. 'Fall 2025' (code 202530). Levels: Academic Year ('2025/26'), Semester ('Fall'/'Winter')."},
    "Count Date":  {"fact_columns": {"STDCOUNT": "CNT", "STDACADUNIT": "CNT"}, "table": "TERMCOUNT", "key": "CNT", "label": "NAME",
                    "description": "I = Initial, P = Official count (default), F = Final."},
    "Student Level": {"fact_columns": {"STDCOUNT": "LEVEL_CODE"}, "table": "STDLEVEL", "key": "LEVEL_CODE", "label": "VALUE",
                    "levels": {"Program Level": {"label": "PROG_LEVEL", "key": "PROG_LEVEL_KEY"}},
                    "description": "Undergraduate / Masters / Doctoral; level Program Level = Undergraduate / Graduate."},
    "New - Returning": {"fact_columns": {"STDCOUNT": "NEWRET_CODE"}, "table": "NEWRETURN", "key": "NEWRET_CODE", "label": "CATEGORY"},
    "Full-Part Time":  {"fact_columns": {"STDCOUNT": "FTPT"}, "table": "FTPTSTAT", "key": "FTPT", "label": "VALUE"},
    "Tuition Assessment": {"fact_columns": {"STDCOUNT": "FEESTAT_CODE", "STDACADUNIT": "FEESTAT_CODE"}, "table": "FEESTAT", "key": "FEESTAT_CODE", "label": "FEESTAT_LEVEL",
                    "description": "Fee status: Domestic / International. The usual definition of 'international student'."},
    "Citizenship": {"fact_columns": {"STDCOUNT": "CITIZEN", "STDACADUNIT": "CITIZEN"}, "table": "CITIZENSHIP", "key": "STVNATN_STATSCAN_CDE", "label": "NATION_DESC",
                    "levels": {"Continent": {"label": "CONTINENT_NAME", "key": "CONTINENT_CODE"}, "World Region": {"label": "REGION_NAME", "key": "REGION_CODE"}},
                    "description": "Country of citizenship (not fee status)."},
    "Region":      {"fact_columns": {"STDCOUNT": "REGION_CODE", "STDACADUNIT": "REGION_CODE"}, "table": "REGION", "key": "REGION_CODE", "label": "CATEGORY",
                    "levels": {"Country": {"label": "COUNTRY_NAME", "key": "COUNTRY"}, "Province": {"label": "PROV_NAME", "key": "PROV"}},
                    "description": "Home region; leaf label is the category (Ottawa Area / Other Ontario / Other Canada / International)."},
    "Age":         {"fact_columns": {"STDCOUNT": "AGE", "STDACADUNIT": "AGE"}, "table": "AGE", "key": "AGE", "label": "CATEGORY", "description": "Age band."},
    "Student Gender": {"fact_columns": {"STDCOUNT": "PIDM", "STDACADUNIT": "PIDM"}, "table": "STUDENT", "key": "PIDM", "label": "GENDER_DESC"},
    "OUAC Type":   {"fact_columns": {"STDCOUNT": "OUACTYPE"}, "table": "OUACTYPE", "key": "OUACTYPE", "label": "OUACTYPE_DESC"},
    "Cohort":      {"fact_columns": {"STDCOUNT": "COHORT"}, "table": null, "key": null, "label": null, "description": "Fall of entry (degenerate dimension)."},
    "Application Type Ugrad": {"fact_columns": {"STDCOUNT": "APPLTY"}, "table": "APPLTYPE", "key": "APPLTY", "label": "APPLTY_DESC"},
    "Entrance Average": {"fact_columns": {"STDCOUNT": "AVG"}, "table": "HSAVG", "key": "AVG", "label": "AVG_DESC"},
    "Campus":      {"fact_columns": {"STDCOUNT": "CAMP_CODE"}, "table": "CAMPUS", "key": "CAMPUS_CODE", "label": "CAMPUS_DESC"},
    "Academic Unit": {"fact_columns": {"STDACADUNIT": "DEPT_CODE"}, "table": "ACADUNIT", "key": "ACADUNIT_ID", "label": "DEPT_DESC",
                    "levels": {"Faculty": {"label": "FACULTY", "key": "FACULTY_KEY"}},
                    "description": "Department of the student's program; level Faculty (FASS, FED, FPA, SCI, SPROTT)."}
  }
}
```

## Related

- `undergraduate_enrolment_by_faculty` (published layer) — real published
  figures and the counting-base vocabulary.
- `Retention` cube — the same undergraduates, followed by cohort.
- `Admissions` cube — where each fall's new students came from.
