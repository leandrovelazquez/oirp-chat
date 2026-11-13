r"""
Synthetic CUDW-shaped warehouse generator.

Builds a DuckDB database whose tables mirror the shape of three subject areas of
an institutional-research warehouse -- the undergraduate retention star
(`URET_*`), the enrolment star (`STDCOUNT` / `STDACADUNIT` and their
dimensions) and the undergraduate admissions star (`ADM_*`) -- and fills them
with **entirely synthetic data**. No real student, applicant or institutional
figure is used anywhere; every value is drawn from the seeded random model
below.

One simulated population feeds all three stars, so they agree with each other:

    applicant (ADM_FACT) --registers--> new student (STDCOUNT, NEWRET_CODE='N')
                                     \-> cohort member (URET_FACT, YEARS=0)

Grain, mirroring the real tables:

    URET_FACT     one row per student per academic year since entry
                  (YEARS = 0, 1, 2, ...). COUNT = 1 on every row, so
                  Sum(COUNT) at a fixed YEARS is the cohort size.
    STDCOUNT      one row per student x term x count date (CNT = I / P / F).
    STDACADUNIT   one row per student x term x count date x academic unit,
                  with WEIGHT splitting combined programs across units.
    ADM_FACT      one row per application (an applicant may hold several),
                  WEIGHT = 1 / (applications held by that applicant).

Run:
    python -m oirp_agent.synthetic_warehouse            # build if missing
    python -m oirp_agent.synthetic_warehouse --force    # rebuild
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "warehouse" / "cudw_synthetic.duckdb"

GENERATOR_VERSION = "1.0"
SEED = 20261112

# ---- time window -----------------------------------------------------------
FIRST_SIM_COHORT = 2006   # simulated so 2016+ enrolment has upper-year students
URET_FIRST_COHORT = 2011  # rolling cohort window loaded into URET_FACT
CURRENT_YEAR = 2026       # current academic year 2026/27: fall term only so far
ENROL_FIRST_YEAR = 2016   # STDCOUNT / STDACADUNIT window
ADM_FIRST_YEAR = 2016     # ADM_FACT window

# Retention star is loaded this many days behind the others, to exercise the
# agent's freshness caveat (see semantic_layer/warehouse/retention.md).
RETENTION_LOAD_LAG_DAYS = 21

# ---- reference data (synthetic but plausible) ------------------------------

FACULTIES = [
    # code, description, share of new undergraduate intake
    ("FASS", "Faculty of Arts and Social Sciences", 0.26),
    ("FED", "Faculty of Engineering and Design", 0.22),
    ("FPA", "Faculty of Public Affairs", 0.21),
    ("SCI", "Faculty of Science", 0.20),
    ("SPROTT", "Sprott School of Business", 0.11),
]
FACULTY_DESC = {c: d for c, d, _ in FACULTIES}

DEPTS = [
    # dept code, description, faculty, undergrad degree, share within faculty
    ("PSYC", "Psychology", "FASS", "BA", 0.28),
    ("ENGL", "English", "FASS", "BA", 0.09),
    ("HIST", "History", "FASS", "BA", 0.08),
    ("SOAN", "Sociology and Anthropology", "FASS", "BA", 0.10),
    ("PHIL", "Philosophy", "FASS", "BA", 0.05),
    ("LALS", "Linguistics and Language Studies", "FASS", "BA", 0.06),
    ("CGSC", "Cognitive Science", "FASS", "BCOGSC", 0.10),
    ("MUSI", "Music", "FASS", "BMUS", 0.04),
    ("GEOG", "Geography and Environmental Studies", "FASS", "BA", 0.08),
    ("ARTH", "Art History", "FASS", "BA", 0.04),
    ("WGST", "Women's and Gender Studies", "FASS", "BA", 0.03),
    ("INDG", "Indigenous Studies", "FASS", "BA", 0.05),
    ("COMS", "Journalism and Communication", "FPA", "BJ", 0.22),
    ("PSCI", "Political Science", "FPA", "BA", 0.18),
    ("LAWS", "Law and Legal Studies", "FPA", "BA", 0.20),
    ("ECON", "Economics", "FPA", "BECON", 0.14),
    ("PADM", "Public Policy and Administration", "FPA", "BPAPM", 0.08),
    ("SOWK", "Social Work", "FPA", "BSW", 0.08),
    ("INAF", "International Affairs", "FPA", "BGINS", 0.10),
    ("CIVE", "Civil and Environmental Engineering", "FED", "BENG", 0.16),
    ("MAAE", "Mechanical and Aerospace Engineering", "FED", "BENG", 0.24),
    ("SYSC", "Systems and Computer Engineering", "FED", "BENG", 0.20),
    ("ELEC", "Electronics", "FED", "BENG", 0.08),
    ("ARCH", "Architecture", "FED", "BAS", 0.14),
    ("IDES", "Industrial Design", "FED", "BID", 0.08),
    ("ITEC", "Information Technology", "FED", "BIT", 0.10),
    ("BIOL", "Biology", "SCI", "BSC", 0.20),
    ("CHEM", "Chemistry", "SCI", "BSC", 0.08),
    ("COMP", "Computer Science", "SCI", "BCS", 0.30),
    ("ERTH", "Earth Sciences", "SCI", "BSC", 0.05),
    ("MATH", "Mathematics and Statistics", "SCI", "BMATH", 0.10),
    ("PHYS", "Physics", "SCI", "BSC", 0.05),
    ("NEUR", "Neuroscience", "SCI", "BSC", 0.12),
    ("HLTH", "Health Sciences", "SCI", "BHSC", 0.10),
    ("BUSI", "Business", "SPROTT", "BCOM", 1.00),
]
DEPT = {d[0]: d for d in DEPTS}
DEPTS_BY_FACULTY: dict[str, list[tuple]] = {}
for _d in DEPTS:
    DEPTS_BY_FACULTY.setdefault(_d[2], []).append(_d)

DEGREE_DESC = {
    "BA": "Bachelor of Arts", "BCOGSC": "Bachelor of Cognitive Science",
    "BMUS": "Bachelor of Music", "BJ": "Bachelor of Journalism",
    "BECON": "Bachelor of Economics",
    "BPAPM": "Bachelor of Public Affairs and Policy Management",
    "BSW": "Bachelor of Social Work", "BGINS": "Bachelor of Global and International Studies",
    "BENG": "Bachelor of Engineering", "BAS": "Bachelor of Architectural Studies",
    "BID": "Bachelor of Industrial Design", "BIT": "Bachelor of Information Technology",
    "BSC": "Bachelor of Science", "BCS": "Bachelor of Computer Science",
    "BMATH": "Bachelor of Mathematics", "BHSC": "Bachelor of Health Sciences",
    "BCOM": "Bachelor of Commerce",
    "MA": "Master of Arts", "MSC": "Master of Science", "MENG": "Master of Engineering",
    "PHD": "Doctor of Philosophy",
}

# Faculty-level adjustments to the simulation (synthetic).
FACULTY_HS_SHIFT = {"FASS": -1.0, "FPA": 0.0, "FED": 2.0, "SCI": 1.5, "SPROTT": 1.5}
FACULTY_CUTOFF = {"FASS": 74.0, "FPA": 76.0, "FED": 80.0, "SCI": 78.0, "SPROTT": 80.0}
FACULTY_RET_SHIFT = {"FASS": -0.10, "FPA": 0.0, "FED": 0.05, "SCI": -0.15, "SPROTT": 0.15}
FACULTY_GRAD_TERMS = {"FED": 4, "FASS": 4, "FPA": 4, "SCI": 4, "SPROTT": 4}

# New undergraduate registrants per fall (synthetic targets).
COHORT_TARGET = {
    2006: 4500, 2007: 4550, 2008: 4600, 2009: 4700, 2010: 4800, 2011: 4850,
    2012: 4950, 2013: 5050, 2014: 5150, 2015: 5250, 2016: 5400, 2017: 5600,
    2018: 5550, 2019: 5450, 2020: 5150, 2021: 5400, 2022: 5350, 2023: 5150,
    2024: 4950, 2025: 4900, 2026: 5050,
}
# International share of the APPLICANT pool by year (synthetic; shaped like the
# publicly reported rise to a 2018 peak and the post-2024 collapse).
INTL_APPLICANT_SHARE = {
    2006: 0.10, 2007: 0.10, 2008: 0.11, 2009: 0.11, 2010: 0.12, 2011: 0.13,
    2012: 0.14, 2013: 0.15, 2014: 0.17, 2015: 0.18, 2016: 0.20, 2017: 0.22,
    2018: 0.25, 2019: 0.22, 2020: 0.17, 2021: 0.19, 2022: 0.19, 2023: 0.16,
    2024: 0.10, 2025: 0.05, 2026: 0.04,
}
GRAD_INTAKE = {"GM": 1600, "GP": 240}  # per fall, roughly flat
GRAD_INTL_SHARE = {y: (0.34 if y < 2024 else 0.24 if y == 2024 else 0.18) for y in range(2006, 2027)}

# Home regions. CATEGORY drives the Region dimension's top level.
REGIONS = [
    # code, country, prov, county, category, country_sort, country_name, prov_name, county_name, area_code, area_name
    ("ON-OTT", "CA", "ON", "OTT", "Ottawa Area", 1, "Canada", "Ontario", "Ottawa", "OTTA", "Ottawa Area"),
    ("ON-GTA", "CA", "ON", "TOR", "Other Ontario", 1, "Canada", "Ontario", "Toronto", "GTA", "Greater Toronto Area"),
    ("ON-OTH", "CA", "ON", "OTH", "Other Ontario", 1, "Canada", "Ontario", "Other Ontario", "REST", "Rest of Ontario"),
    ("QC", "CA", "QC", None, "Other Canada", 1, "Canada", "Quebec", None, "QC", "Quebec"),
    ("BC", "CA", "BC", None, "Other Canada", 1, "Canada", "British Columbia", None, "WEST", "Western Canada"),
    ("AB", "CA", "AB", None, "Other Canada", 1, "Canada", "Alberta", None, "WEST", "Western Canada"),
    ("NS", "CA", "NS", None, "Other Canada", 1, "Canada", "Nova Scotia", None, "ATL", "Atlantic Canada"),
    ("CA-OTH", "CA", "XX", None, "Other Canada", 1, "Canada", "Other provinces/territories", None, "OTHC", "Other Canada"),
]
DOMESTIC_REGION_WEIGHTS = [("ON-OTT", 0.38), ("ON-GTA", 0.22), ("ON-OTH", 0.27),
                           ("QC", 0.05), ("BC", 0.02), ("AB", 0.02), ("NS", 0.02), ("CA-OTH", 0.02)]

COUNTRIES = [
    # statscan code, alpha2, continent code, region code, continent, region, nation code, description, intl weight
    ("1", "CA", "NA", "NAM", "North America", "Northern America", "CA", "Canada", 0.0),
    ("2", "CN", "AS", "EAS", "Asia", "Eastern Asia", "CN", "China", 0.28),
    ("3", "IN", "AS", "SAS", "Asia", "Southern Asia", "IN", "India", 0.17),
    ("4", "NG", "AF", "WAF", "Africa", "Western Africa", "NG", "Nigeria", 0.08),
    ("5", "US", "NA", "NAM", "North America", "Northern America", "US", "United States", 0.05),
    ("6", "BD", "AS", "SAS", "Asia", "Southern Asia", "BD", "Bangladesh", 0.05),
    ("7", "SA", "AS", "WAS", "Asia", "Western Asia", "SA", "Saudi Arabia", 0.04),
    ("8", "IR", "AS", "SAS", "Asia", "Southern Asia", "IR", "Iran", 0.04),
    ("9", "VN", "AS", "SEA", "Asia", "South-Eastern Asia", "VN", "Vietnam", 0.04),
    ("10", "PK", "AS", "SAS", "Asia", "Southern Asia", "PK", "Pakistan", 0.04),
    ("11", "FR", "EU", "WEU", "Europe", "Western Europe", "FR", "France", 0.03),
    ("12", "KE", "AF", "EAF", "Africa", "Eastern Africa", "KE", "Kenya", 0.03),
    ("13", "LB", "AS", "WAS", "Asia", "Western Asia", "LB", "Lebanon", 0.03),
    ("14", "GB", "EU", "NEU", "Europe", "Northern Europe", "GB", "United Kingdom", 0.03),
    ("15", "BR", "SA", "SAM", "South America", "South America", "BR", "Brazil", 0.03),
    ("16", "MX", "NA", "CAM", "North America", "Central America", "MX", "Mexico", 0.03),
    ("17", "KR", "AS", "EAS", "Asia", "Eastern Asia", "KR", "South Korea", 0.03),
]
COUNTRY = {c[1]: c for c in COUNTRIES}
INTL_COUNTRY_WEIGHTS = [(c[1], c[8]) for c in COUNTRIES if c[8] > 0]
PR_COUNTRY_WEIGHTS = [("CN", 0.25), ("IN", 0.2), ("IR", 0.1), ("PK", 0.1), ("NG", 0.1),
                      ("LB", 0.1), ("VN", 0.05), ("GB", 0.05), ("FR", 0.05)]

AVG_BANDS = [  # key, label, lower bound (None = no average)
    ("1", "90% +", 90.0), ("2", "85% - 89.9%", 85.0), ("3", "80% - 84.9%", 80.0),
    ("4", "75% - 79.9%", 75.0), ("5", "Below 75%", 0.0), ("N", "No high school average", None),
]
APPLTY = [  # key, label, category key, category, status
    ("D", "Direct from secondary school", "NEW", "New", "Direct entry"),
    ("T", "Transfer from college or university", "NEW", "New", "Transfer"),
    ("M", "Mature student", "NEW", "New", "Mature"),
    ("O", "Other admission", "NEW", "New", "Other"),
]
OUACTYPE = [("101", "OUAC 101 - Ontario secondary school"), ("105", "OUAC 105 - Other applicants")]
SEXES = [("F", "Female"), ("M", "Male"), ("X", "Another gender")]
CNT_CODES = [("I", "Initial count"), ("P", "Official count (snapshot date)"), ("F", "Final count")]
LEVELS = [  # level code, prog level key, prog level, value, level key
    ("UG", "U", "Undergraduate", "Undergraduate", "UG"),
    ("GM", "G", "Graduate", "Masters", "GM"),
    ("GP", "G", "Graduate", "Doctoral", "GP"),
]
AGE_BANDS = [(0, 17, "17 and under"), (18, 20, "18-20"), (21, 24, "21-24"),
             (25, 29, "25-29"), (30, 39, "30-39"), (40, 120, "40 and over")]


def age_band(age: int) -> str:
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "Unknown"


def avg_band(oave: float | None) -> str:
    if oave is None:
        return "N"
    for key, _, lo in AVG_BANDS:
        if lo is not None and oave >= lo:
            return key
    return "5"


def term_code(year: int, semester: str) -> str:
    """Banner-style term: YYYY10 winter, YYYY20 summer, YYYY30 fall."""
    return f"{year}{ {'W': '10', 'S': '20', 'F': '30'}[semester] }"


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def weighted_choice(rng: random.Random, pairs: list[tuple]):
    total = sum(w for _, w in pairs)
    r = rng.random() * total
    acc = 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


# ============================================================================
# Simulation model
# ============================================================================


@dataclass
class YearRecord:
    acadyear: int
    status: str            # 'C' registered/continuing, 'G' graduated, 'S' not registered
    dept: str | None       # unit of registration (C) or last unit (G/S)
    levl: int | None       # year level while registered
    ncrs: int = 0
    nfail: int = 0
    nwdn: int = 0
    credits: float = 0.0
    gpa_points: float = 0.0  # credit-weighted GPA sum for the year
    winter: bool = True      # registered in the winter term too


@dataclass
class Student:
    pidm: int
    cohort: int
    level_code: str          # UG / GM / GP
    sex: str
    birth_year: int
    feestat: str             # D domestic / I international
    citizen: str             # alpha2
    region: str
    ftpt: str                # F / P at entry
    applty: str
    ouactype: str
    oave: float | None
    first_dept: str
    second_dept: str | None = None   # combined program partner (weight 0.5)
    years: list[YearRecord] = field(default_factory=list)


class Simulator:
    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)
        self.next_pidm = 1_000_001
        self.students: list[Student] = []
        self.applications: list[dict] = []

    # ---- attribute draws ----

    def _pidm(self) -> int:
        p = self.next_pidm
        self.next_pidm += 1
        return p

    def _residency(self, year: int, intl_share: float) -> tuple[str, str, str]:
        rng = self.rng
        if rng.random() < intl_share:
            c = weighted_choice(rng, INTL_COUNTRY_WEIGHTS)
            return "I", c, f"INT-{c}"
        region = weighted_choice(rng, DOMESTIC_REGION_WEIGHTS)
        citizen = "CA" if rng.random() > 0.08 else weighted_choice(rng, PR_COUNTRY_WEIGHTS)
        return "D", citizen, region

    def _pick_dept(self, faculty: str | None = None) -> str:
        rng = self.rng
        if faculty is None:
            faculty = weighted_choice(rng, [(f, s) for f, _, s in FACULTIES])
        return weighted_choice(rng, [(d[0], d[4]) for d in DEPTS_BY_FACULTY[faculty]])

    def _applicant_profile(self, year: int) -> dict:
        rng = self.rng
        feestat, citizen, region = self._residency(year, INTL_APPLICANT_SHARE[year])
        r = rng.random()
        if feestat == "I":
            applty = "D" if r < 0.85 else "T"
        else:
            applty = "D" if r < 0.80 else "T" if r < 0.92 else "M" if r < 0.97 else "O"
        ouactype = "101" if (applty == "D" and region.startswith("ON-")) else "105"
        oave = None
        if applty == "D":
            oave = round(min(99.5, max(62.0, rng.gauss(83.0, 6.0))), 1)
        elif applty == "T" and rng.random() < 0.4:
            oave = round(min(99.0, max(60.0, rng.gauss(78.0, 6.5))), 1)
        age = 18 if applty == "D" else rng.randint(19, 24) if applty == "T" else rng.randint(23, 45)
        ftpt = "P" if (applty == "M" and rng.random() < 0.55) or rng.random() < 0.03 else "F"
        return {
            "sex": weighted_choice(rng, [("F", 0.54), ("M", 0.45), ("X", 0.01)]),
            "birth_year": year - age, "feestat": feestat, "citizen": citizen,
            "region": region, "applty": applty, "ouactype": ouactype,
            "oave": oave, "ftpt": ftpt,
        }

    # ---- admissions funnel ----

    def simulate_admissions_year(self, year: int, target: int, record: bool) -> list[Student]:
        """Generate applicants until `target` of them register. Returns the registrants."""
        rng = self.rng
        registrants: list[Student] = []
        while len(registrants) < target:
            prof = self._applicant_profile(year)
            pidm = self._pidm()
            n_apps = weighted_choice(rng, [(1, 0.6), (2, 0.28), (3, 0.12)])
            first_rank = weighted_choice(rng, [(1, 0.34), (2, 0.30), (3, 0.36)])
            depts: list[str] = []
            first_fac = weighted_choice(rng, [(f, s) for f, _, s in FACULTIES])
            while len(depts) < n_apps:
                fac = first_fac if rng.random() < 0.6 else None
                d = self._pick_dept(fac)
                if d not in depts:
                    depts.append(d)
            weight = 1.0 / n_apps
            apps = []
            for i, d in enumerate(depts):
                fac = DEPT[d][2]
                if prof["oave"] is not None:
                    shifted = prof["oave"] + rng.gauss(0, 1.5)
                    approved = shifted >= FACULTY_CUTOFF[fac]
                else:
                    approved = rng.random() < 0.62
                withdrawn = (not approved) and rng.random() < 0.08
                apps.append({"dept": d, "rank": min(first_rank + i, 3),
                             "approved": approved, "withdrawn": withdrawn})
            approved_apps = [a for a in apps if a["approved"]]
            confirmed = None
            if approved_apps:
                best = min(approved_apps, key=lambda a: a["rank"])
                p_conf = {1: 0.62, 2: 0.30, 3: 0.14}[best["rank"]]
                if prof["feestat"] == "I":
                    p_conf -= 0.10
                if prof["oave"] is not None and prof["oave"] >= 92:
                    p_conf -= 0.08
                if rng.random() < max(0.03, p_conf):
                    confirmed = best
            registered = confirmed is not None and rng.random() < 0.93
            noanswer = (confirmed is None) and bool(approved_apps) and rng.random() < 0.15

            if record:
                for a in apps:
                    is_conf = a is confirmed
                    self.applications.append({
                        "PIDM": pidm, "ACADYEAR": year, "DEPT": a["dept"],
                        "FACULTY": DEPT[a["dept"]][2], "DEGREE": DEPT[a["dept"]][3],
                        "CHOICE": a["rank"], "WEIGHT": weight, "PROF": prof,
                        "APPR": weight if a["approved"] else 0.0,
                        "REFU": weight if (not a["approved"] and not a["withdrawn"]) else 0.0,
                        "WITD": weight if a["withdrawn"] else 0.0,
                        "CONF": 1.0 if is_conf else 0.0,
                        "DECL": weight if (a["approved"] and not is_conf and not noanswer) else 0.0,
                        "NOAN": weight if (a["approved"] and not is_conf and noanswer) else 0.0,
                        "ATCU": 1.0 if (is_conf and registered) else 0.0,
                    })
            if registered:
                st = Student(
                    pidm=pidm, cohort=year, level_code="UG", sex=prof["sex"],
                    birth_year=prof["birth_year"], feestat=prof["feestat"],
                    citizen=prof["citizen"], region=prof["region"], ftpt=prof["ftpt"],
                    applty=prof["applty"], ouactype=prof["ouactype"], oave=prof["oave"],
                    first_dept=confirmed["dept"],
                )
                if rng.random() < 0.12:  # combined program across two units
                    partner = self._pick_dept()
                    if partner != st.first_dept:
                        st.second_dept = partner
                registrants.append(st)
        return registrants

    # ---- undergraduate trajectories ----

    def simulate_ug_trajectory(self, st: Student) -> None:
        rng = self.rng
        fac = DEPT[st.first_dept][2]
        base = 7.2 + 0.22 * ((st.oave if st.oave is not None else 81.0) - 83.0) + 0.1 * FACULTY_HS_SHIFT[fac]
        ability = rng.gauss(base, 1.6)
        dept = st.first_dept
        status = "C"
        terms_done = 0   # full-time-equivalent years completed
        stopped_years = 0
        for k in range(0, CURRENT_YEAR - st.cohort + 1):
            year = st.cohort + k
            if k > 0:
                prev = st.years[-1]
                if prev.status == "G":
                    status = "G"
                elif prev.status == "C":
                    need = FACULTY_GRAD_TERMS[fac]
                    if terms_done >= need and rng.random() < (0.62 if terms_done == need else 0.75):
                        status = "G"
                    else:
                        gpa = prev.gpa_points / prev.credits if prev.credits else ability
                        logit = {1: 2.05, 2: 2.6}.get(k, 2.9)
                        logit += 0.38 * (gpa - 7.0)
                        logit += FACULTY_RET_SHIFT[fac]
                        if st.ftpt == "P":
                            logit -= 0.9
                        if st.feestat == "I":
                            logit -= 0.15
                        if st.applty == "T":
                            logit += 0.2
                        if year == 2021:
                            logit -= 0.25   # synthetic pandemic-year dip
                        if k > 8:
                            logit -= 0.8
                        status = "C" if rng.random() < logistic(logit) else "S"
                else:  # stopped out
                    stopped_years += 1
                    status = "C" if (stopped_years <= 3 and rng.random() < 0.12) else "S"
                    if status == "C":
                        stopped_years = 0
                # switching units, mostly at the start of second year
                if status == "C" and prev.status == "C" and k <= 2:
                    if rng.random() < (0.09 if k == 1 else 0.03):
                        dept = self._pick_dept(fac if rng.random() < 0.5 else None)
                        fac_new = DEPT[dept][2]
                        fac = fac_new
            if status == "C":
                load = 1.0 if st.ftpt == "F" else rng.choice([0.4, 0.5, 0.6])
                ncrs = max(1, round(10 * load + rng.choice([-1, 0, 0, 1])))
                gpa_year = min(12.0, max(0.0, ability + rng.gauss(0, 1.2) + 0.15 * min(k, 3)))
                p_fail = min(0.45, max(0.005, 0.12 - 0.02 * (gpa_year - 6)))
                nfail = sum(1 for _ in range(ncrs) if rng.random() < p_fail)
                nwdn = sum(1 for _ in range(ncrs) if rng.random() < 0.035)
                credits = (ncrs - nwdn) * 0.5
                levl = min(4, 1 + int(terms_done)) if terms_done < 4 else 5
                st.years.append(YearRecord(
                    acadyear=year, status="C", dept=dept, levl=levl, ncrs=ncrs,
                    nfail=nfail, nwdn=nwdn, credits=credits,
                    gpa_points=round(gpa_year * credits, 3),
                    winter=rng.random() < 0.97))
                terms_done += load
            else:
                st.years.append(YearRecord(acadyear=year, status=status, dept=dept, levl=None))

    # ---- graduate students (enrolment only) ----

    def simulate_grad_intake(self, year: int) -> list[Student]:
        rng = self.rng
        out = []
        for level_code, n in GRAD_INTAKE.items():
            n = int(n * (1.0 + rng.uniform(-0.04, 0.04)))
            for _ in range(n):
                feestat, citizen, region = self._residency(year, GRAD_INTL_SHARE[year])
                st = Student(
                    pidm=self._pidm(), cohort=year, level_code=level_code,
                    sex=weighted_choice(rng, [("F", 0.52), ("M", 0.47), ("X", 0.01)]),
                    birth_year=year - rng.randint(22, 34) - (3 if level_code == "GP" else 0),
                    feestat=feestat, citizen=citizen, region=region,
                    ftpt="F" if rng.random() < 0.86 else "P", applty="O", ouactype="105",
                    oave=None, first_dept=self._pick_dept(),
                )
                duration = (2 if level_code == "GM" else 5) + (1 if st.ftpt == "P" else 0)
                done = False
                for k in range(0, CURRENT_YEAR - year + 1):
                    if done:
                        st.years.append(YearRecord(year + k, "G", st.first_dept, None))
                        continue
                    if k >= duration and rng.random() < 0.85:
                        done = True
                        st.years.append(YearRecord(year + k, "G", st.first_dept, None))
                        continue
                    if k > 0 and rng.random() < (0.05 if level_code == "GM" else 0.06):
                        st.years.append(YearRecord(year + k, "S", st.first_dept, None))
                        break
                    st.years.append(YearRecord(year + k, "C", st.first_dept, k + 1,
                                               winter=rng.random() < 0.98))
                out.append(st)
        return out

    def run(self) -> None:
        for year in range(FIRST_SIM_COHORT, CURRENT_YEAR + 1):
            registrants = self.simulate_admissions_year(
                year, COHORT_TARGET[year], record=year >= ADM_FIRST_YEAR)
            for st in registrants:
                self.simulate_ug_trajectory(st)
            self.students.extend(registrants)
            self.students.extend(self.simulate_grad_intake(year))


# ============================================================================
# Table writers
# ============================================================================

URET_FACT_COLUMNS = [
    "PIDM", "ACADYEAR", "PCAT", "BDEGREE", "FACULTY", "TACADU", "FTPTSTAT", "COUNT",
    "CREDTERM", "FFTE", "EFFTE", "BIUEFFTE", "SEX", "LEVL", "AGE", "WEIGHT", "AGEFULL",
    "UWMAJOR", "UWMINOR", "UWACUNIT", "WEIGHTMA", "CONTINUE", "FDEGREE", "FDVALUE",
    "FACADUNI", "LDEGREE", "LDVALUE", "LACADUNI", "SDEGREE", "SDVALUE", "SACADUNI",
    "GRADUATE", "CONTGRAD", "COHORT", "CONTSTAR", "CONTSTGR", "NCRED", "NCRS", "NF",
    "NW", "SDFW", "NCRED1", "NCRED2", "XGPA1", "XGPA2", "NFAIL", "NWDN", "NDFW", "XOAVE",
    "APPLTY", "OUACTYPE", "HOMZIP", "APPVALUE", "APPTYPE", "FSA", "OTTAREA", "OTTSUM",
    "POST1", "RVALUE", "REGION", "AREA", "AVG", "YEARS", "RETAINED", "RETSTAR", "SWITCH",
    "SWITCHA", "NOAVE", "TOTTSUM", "BCOUNTY", "COUNTY", "COURVAL", "CREGION", "ONTAREA",
    "TCOUNTY", "TPOST1", "STOPOUT", "CHOICE", "CONTINU", "GRADSEVEN", "BMAJOR", "FMAJOR",
    "LMAJOR", "SMAJOR",
]
URET_NUMERIC = {
    "PIDM", "ACADYEAR", "COUNT", "CREDTERM", "FFTE", "EFFTE", "BIUEFFTE", "AGEFULL",
    "WEIGHT", "WEIGHTMA", "CONTINUE", "GRADUATE", "CONTGRAD", "COHORT", "CONTSTAR",
    "CONTSTGR", "NCRED", "NCRS", "NF", "NW", "SDFW", "NCRED1", "NCRED2", "XGPA1", "XGPA2",
    "NFAIL", "NWDN", "NDFW", "XOAVE", "YEARS", "NOAVE", "STOPOUT", "LEVL",
}

STDCOUNT_COLUMNS = [
    "STDCOUNT_ID", "PIDM", "TERM", "FTE", "FTPT", "CNT", "LEVEL_CODE", "NEWRET_CODE",
    "CITIZEN", "IMMIG", "FORFEE", "REGION_CODE", "AGE", "OUACTYPE", "COHORT", "APPLTY",
    "AVG", "OAVE", "CAMP_CODE", "ELGSTAT", "MCUCAT", "CREDTERM", "FEESTAT_CODE", "FFTE",
    "WGUFFTE", "NEW_WGUFFTE",
]
STDACADUNIT_COLUMNS = [
    "STDACADUNIT_ID", "PIDM", "TERM", "DEGMAJ", "DEPT_CODE", "WEIGHT", "CNT", "CITIZEN",
    "FEESTAT_CODE", "REGION_CODE", "AGE", "WFTE", "DEGREE", "ACADYEAR", "WGUWFTE",
    "NEW_WGUWFTE",
]
ADM_FACT_COLUMNS = [
    "PIDM", "ACADYEAR", "CNT", "DEGR", "INAPPDEG", "HISCC", "COUNTRY", "STUDNO", "OAVE",
    "APPLEVEL", "REGLEVEL", "APPTYPE", "PROGRAM", "PVALUE", "DEGREE", "DEGVAL",
    "ACADUNIT", "TACADU", "FACULTY", "WEIGHT", "CHOICE", "REGION", "RVALUE", "POST1",
    "SEX", "APPLTY", "APPVALUE", "OUACTYPE", "AREA", "APPL", "APPR", "REFU", "DEFF",
    "NODE", "CONF", "WITD", "DECL", "NOAN", "AYEAR", "CVALUE", "BCOUNTY", "COUNTY",
    "CREGION", "COURVAL", "TCOUNTY", "TOTTSUM", "TPOST1", "ONTAREA", "AVG", "LEVL",
    "ADMDEC", "STUDEC", "RDEGSHRT", "RSUBTOT", "RDEGVAL", "FTPT", "TDEPT", "DEGSHORT",
    "SUBTOT", "TMAJOR", "ATCU", "APPYEAR", "UPCODE", "CUDATE", "CUDATEV", "STUDATE",
    "STUDATEV", "ADMDATE", "ADMDATEV", "SCVALUE", "WOAVE", "OAVE_WEIGHT",
]
ADM_NUMERIC = {
    "PIDM", "ACADYEAR", "OAVE", "WEIGHT", "CHOICE", "APPL", "APPR", "REFU", "DEFF",
    "NODE", "CONF", "WITD", "DECL", "NOAN", "ATCU", "APPYEAR", "WOAVE", "OAVE_WEIGHT",
}


class CsvStream:
    """One table's rows streamed to a temp CSV file (keeps memory flat)."""

    def __init__(self, path: Path, columns: list[str]) -> None:
        self.path = path
        self.columns = columns
        self.fh = path.open("w", newline="", encoding="utf-8")
        self.w = csv.writer(self.fh)
        self.w.writerow(columns)
        self.n = 0

    def write(self, row) -> None:
        self.w.writerow(["" if v is None else v for v in row])
        self.n += 1

    def close(self) -> None:
        self.fh.close()


class TableWriter:
    """Stream rows to CSV, then bulk-load into DuckDB with explicit types."""

    def __init__(self, con: duckdb.DuckDBPyConnection, tmpdir: Path) -> None:
        self.con = con
        self.tmpdir = tmpdir

    def open(self, table: str, columns: list[str]) -> CsvStream:
        return CsvStream(self.tmpdir / f"{table}.csv", columns)

    def finish(self, table: str, stream: CsvStream, numeric: set[str] = frozenset(),
               integer: set[str] = frozenset()) -> int:
        stream.close()
        types = {c: ("BIGINT" if c in integer else "DOUBLE" if c in numeric else "VARCHAR")
                 for c in stream.columns}
        cols_sql = "{" + ", ".join(f"'{c}': '{t}'" for c, t in types.items()) + "}"
        path_sql = stream.path.resolve().as_posix().replace("'", "''")
        self.con.execute(f'DROP TABLE IF EXISTS "{table}"')
        self.con.execute(
            f"CREATE TABLE \"{table}\" AS SELECT * FROM read_csv('{path_sql}', header=true, "
            f"columns={cols_sql}, nullstr='', quote='\"')"
        )
        return stream.n

    def load(self, table: str, columns: list[str], rows, numeric: set[str] = frozenset(),
             integer: set[str] = frozenset()) -> int:
        s = self.open(table, columns)
        for row in rows:
            s.write(row)
        return self.finish(table, s, numeric, integer)


def _dim(con, table: str, columns: list[str], rows: list[tuple]) -> None:
    con.execute(f'DROP TABLE IF EXISTS "{table}"')
    con.execute(f'CREATE TABLE "{table}" (' + ", ".join(f'"{c}" VARCHAR' for c in columns) + ")")
    if rows:
        ph = ", ".join("?" for _ in columns)
        con.executemany(f'INSERT INTO "{table}" VALUES ({ph})',
                        [tuple(None if v is None else str(v) for v in r) for r in rows])


def write_dimensions(con) -> None:
    dept_rows_l1 = [(d[0], d[1], d[2], FACULTY_DESC[d[2]]) for d in DEPTS]
    # Leaf label: county where there is one, else province; international -> country.
    region_label = {r[0]: (r[8] or r[7]) for r in REGIONS}
    intl_regions = [(f"INT-{c[1]}", c[1], None, None, "International", 2, c[7], None, None, "INTL", "International")
                    for c in COUNTRIES if c[1] != "CA"]
    all_regions = list(REGIONS) + intl_regions
    region_cat_key = {"Ottawa Area": "OTT", "Other Ontario": "ONT", "Other Canada": "CAN", "International": "INT"}

    # ---- retention star dimensions (URET_*) ----
    _dim(con, "URET_COHORT", ["COHORT_KEY", "LABEL_DESC"],
         [(y, str(y)) for y in range(URET_FIRST_COHORT, CURRENT_YEAR + 1)])
    _dim(con, "URET_YEARS", ["YEARS_KEY", "LABEL_DESC"],
         [(k, str(k)) for k in range(0, CURRENT_YEAR - URET_FIRST_COHORT + 1)])
    _dim(con, "URET_ACADYEAR", ["ACADYEAR_KEY", "LABEL_DESC"],
         [(y, f"{y}/{str(y + 1)[2:]}") for y in range(URET_FIRST_COHORT, CURRENT_YEAR + 1)])
    for t, k in (("URET_FACADUNI", "FACADUNI_KEY"), ("URET_LACADUNI", "LACADUNI_KEY"),
                 ("URET_SACADUNI", "SACADUNI_KEY")):
        _dim(con, t, [k, "LABEL_DESC", "LEVEL1", "LEVEL1_DESC"], dept_rows_l1)
    _dim(con, "URET_FACULTY", ["FACULTY_KEY", "LABEL_DESC"], [(c, d) for c, d, _ in FACULTIES])
    _dim(con, "URET_FTPTSTAT", ["FTPTSTAT_KEY", "LABEL_DESC"], [("F", "Full-time"), ("P", "Part-time")])
    _dim(con, "URET_AVG", ["AVG_KEY", "LABEL_DESC"], [(k, l) for k, l, _ in AVG_BANDS])
    _dim(con, "URET_SEX", ["SEX_KEY", "LABEL_DESC"], SEXES)
    _dim(con, "URET_AGE", ["AGE_KEY", "LABEL_DESC"], [(b[2], b[2]) for b in AGE_BANDS])
    _dim(con, "URET_APPLTY", ["APPLTY_KEY", "LABEL_DESC"], [(a[0], a[1]) for a in APPLTY])
    _dim(con, "URET_OUACTYPE", ["OUACTYPE_KEY", "LABEL_DESC"], OUACTYPE)
    _dim(con, "URET_REGION", ["REGION_KEY", "LABEL_DESC", "LEVEL1", "LEVEL1_DESC"],
         [(r[0], region_label.get(r[0], r[6]), region_cat_key[r[4]], r[4]) for r in all_regions])
    _dim(con, "URET_RETAINED", ["RETAINED_KEY", "LABEL_DESC"],
         [("Y", "Retained into second year"), ("N", "Not retained into second year"),
          ("U", "Not yet known")])
    _dim(con, "URET_GRADSEVEN", ["GRADSEVEN_KEY", "LABEL_DESC"],
         [("Y", "Graduated within 7 years"), ("N", "Did not graduate within 7 years"),
          ("U", "Not yet known (cohort under 7 years)")])
    _dim(con, "URET_SWITCHA", ["SWITCHA_KEY", "LABEL_DESC"],
         [("Y", "Switched academic unit"), ("N", "Same academic unit")])
    _dim(con, "URET_LEVEL", ["LEVEL_KEY", "LABEL_DESC"],
         [(1, "Year 1"), (2, "Year 2"), (3, "Year 3"), (4, "Year 4"), (5, "Year 5+")])
    _dim(con, "URET_RETSTAR", ["RETSTAR_KEY", "LABEL_DESC"],
         [("Y", "Persisting"), ("N", "Not persisting")])

    # ---- enrolment star dimensions ----
    _dim(con, "ACADUNIT", ["ACADUNIT_ID", "DEPT_DESC", "FACULTY", "FACULTY_KEY"],
         [(d[0], d[1], FACULTY_DESC[d[2]], d[2]) for d in DEPTS])
    time_rows = []
    for y in range(ENROL_FIRST_YEAR, CURRENT_YEAR + 1):
        for sem, label_sem, cal_year in (("F", "Fall", y), ("W", "Winter", y + 1)):
            if cal_year > CURRENT_YEAR and sem == "W":
                continue
            tc = term_code(cal_year, sem)
            time_rows.append((tc, f"{y}/{str(y + 1)[2:]}", label_sem, f"{label_sem} {cal_year}",
                              tc, sem, y, f"{y}/{str(y + 1)[2:]}", y, tc))
    _dim(con, "TIME", ["TIME_ID", "ACADYEAR", "SEMESTER", "TERM", "TERMKEY", "SEMESTERKEY",
                       "ACADYEARKEY", "FUNDINGYEAR", "FUNDINGYEARKEY", "FUNDINGTERMKEY"], time_rows)
    _dim(con, "TERMCOUNT", ["CNT", "KEY", "NAME"], [(c, c, n) for c, n in CNT_CODES])
    _dim(con, "FTPTSTAT", ["FTPT", "VALUE"], [("F", "Full-time"), ("P", "Part-time")])
    _dim(con, "STDLEVEL", ["LEVEL_CODE", "PROG_LEVEL_KEY", "PROG_LEVEL", "VALUE", "LEVEL_KEY"], LEVELS)
    _dim(con, "NEWRETURN", ["NEWRET_CODE", "CATEGORY_KEY", "CATEGORY", "VALUE"],
         [("N", "N", "New", "New to the institution"), ("R", "R", "Returning", "Returning student")])
    _dim(con, "FEESTAT", ["FEESTAT_CODE", "FEESTAT_LEVEL", "FEESTAT_DESC"],
         [("D", "Domestic", "Domestic tuition"), ("I", "International", "International tuition")])
    _dim(con, "CITIZENSHIP", ["STVNATN_STATSCAN_CDE", "ALPHA2_CODE", "CONTINENT_CODE", "REGION_CODE",
                              "CONTINENT_NAME", "REGION_NAME", "STVNATN_NATION", "NATION_DESC"],
         [(c[1], c[1], c[2], c[3], c[4], c[5], c[6], c[7]) for c in COUNTRIES])
    _dim(con, "REGION", ["REGION_CODE", "COUNTRY", "PROV", "COUNTY", "CATEGORY", "COUNTRY_SORT",
                         "COUNTRY_NAME", "PROV_NAME", "COUNTY_NAME", "AREA_CODE", "AREA_NAME"], all_regions)
    _dim(con, "AGE", ["AGE", "CATEGORY", "VALUE"], [(a, age_band(a), str(a)) for a in range(15, 81)])
    _dim(con, "HSAVG", ["AVG", "AVG_DESC"], [(k, l) for k, l, _ in AVG_BANDS])
    _dim(con, "OUACTYPE", ["OUACTYPE", "OUACTYPE_DESC"], OUACTYPE)
    _dim(con, "APPLTYPE", ["APPLTY", "APPLTY_CATEGORY_KEY", "APPLTY_CATEGORY", "APPLTY_STATUS", "APPLTY_DESC"],
         [(a[0], a[2], a[3], a[4], a[1]) for a in APPLTY])
    _dim(con, "CAMPUS", ["CAMPUS_CODE", "CAMPUS_IND", "CAMPUS_DESC"], [("M", "Main", "Main campus")])

    # ---- admissions star dimensions (ADM_*) ----
    _dim(con, "ADM_FACULTY", ["FACULTY_KEY", "LABEL_DESC"], [(c, d) for c, d, _ in FACULTIES])
    _dim(con, "ADM_ACADUNIT", ["ACADUNIT_KEY", "LABEL_DESC", "LEVEL1", "LEVEL1_DESC"], dept_rows_l1)
    _dim(con, "ADM_PROGRAM", ["PROGRAM_KEY", "LABEL_DESC", "LEVEL1", "LEVEL1_DESC"],
         [(f"{d[3]}-{d[0]}", f"{DEGREE_DESC[d[3]]} - {d[1]}", d[2], FACULTY_DESC[d[2]]) for d in DEPTS])
    _dim(con, "ADM_CHOICE", ["CHOICE_KEY", "LABEL_DESC"],
         [(1, "First choice"), (2, "Second choice"), (3, "Third choice or lower")])
    _dim(con, "ADM_AVG", ["AVG_KEY", "LABEL_DESC"], [(k, l) for k, l, _ in AVG_BANDS])
    _dim(con, "ADM_SEX", ["SEX_KEY", "LABEL_DESC"], SEXES)
    _dim(con, "ADM_OUACTYPE", ["OUACTYPE_KEY", "LABEL_DESC"], OUACTYPE)
    _dim(con, "ADM_APPTYPE", ["APPTYPE_KEY", "LABEL_DESC", "LEVEL1", "LEVEL1_DESC", "LEVEL2", "LEVEL2_DESC"],
         [(a[0], a[1], a[2], a[3], a[0], a[4]) for a in APPLTY])
    _dim(con, "ADM_FTPT", ["FTPT_KEY", "LABEL_DESC"], [("F", "Full-time"), ("P", "Part-time")])
    _dim(con, "ADM_REGION", ["REGION_KEY", "LABEL_DESC", "LEVEL1", "LEVEL1_DESC"],
         [(r[0], region_label.get(r[0], r[6]), region_cat_key[r[4]], r[4]) for r in all_regions])
    _dim(con, "ADM_COUNTRY", ["COUNTRY_KEY", "LABEL_DESC", "LEVEL1", "LEVEL1_DESC"],
         [(c[1], c[7], c[2], c[4]) for c in COUNTRIES])
    _dim(con, "ADM_ACADYEAR", ["ACADYEAR_KEY", "LABEL_DESC"],
         [(y, f"{y}/{str(y + 1)[2:]}") for y in range(ADM_FIRST_YEAR, CURRENT_YEAR + 1)])
    _dim(con, "ADM_CNT", ["CNT_KEY", "LABEL_DESC"], [("F", "End of cycle")])


def uret_rows(students: list[Student]):
    for st in students:
        if st.level_code != "UG" or st.cohort < URET_FIRST_COHORT:
            continue
        first_fac = DEPT[st.first_dept][2]
        y1 = st.years[1] if len(st.years) > 1 else None
        retained = "U" if y1 is None else ("Y" if y1.status == "C" else "N")
        second_unit = y1.dept if (y1 is not None and y1.status == "C") else st.first_dept
        grad_by7 = any(y.status == "G" for y in st.years[:8])
        gradseven = "Y" if grad_by7 else ("U" if st.cohort + 7 > CURRENT_YEAR else "N")
        reg_years = [i for i, y in enumerate(st.years) if y.status == "C"]
        last_dept = st.first_dept
        cum_cred = 0.0
        cum_pts = 0.0
        for k, yr in enumerate(st.years):
            registered = yr.status == "C"
            if registered:
                last_dept = yr.dept
                cum_cred += yr.credits
                cum_pts += yr.gpa_points
            graduate = 1 if yr.status == "G" else 0
            cont = 1 if registered else 0
            # Persisting: registered now, OR not registered now but registers again later
            later = any(i > k for i in reg_years)
            persisting = 1 if (registered or (yr.status == "S" and later)) else 0
            switched = "Y" if last_dept != st.first_dept else "N"
            age = yr.acadyear - st.birth_year
            row = dict.fromkeys(URET_FACT_COLUMNS)
            row.update({
                "PIDM": st.pidm, "ACADYEAR": yr.acadyear, "COHORT": st.cohort, "YEARS": k,
                "COUNT": 1, "FACULTY": first_fac, "FTPTSTAT": st.ftpt, "SEX": st.sex,
                "LEVL": yr.levl, "AGE": age_band(age), "AGEFULL": age,
                "CONTINUE": cont, "GRADUATE": graduate,
                "STOPOUT": 1 if yr.status == "S" else 0,
                "CONTGRAD": cont + graduate, "CONTSTAR": persisting,
                "CONTSTGR": persisting + graduate,
                "FACADUNI": st.first_dept, "LACADUNI": last_dept, "SACADUNI": second_unit,
                "FDEGREE": DEPT[st.first_dept][3], "LDEGREE": DEPT[last_dept][3],
                "SDEGREE": DEPT[second_unit][3],
                "FMAJOR": st.first_dept, "LMAJOR": last_dept, "SMAJOR": second_unit,
                "BMAJOR": st.first_dept, "BDEGREE": DEPT[st.first_dept][3],
                "NCRS": yr.ncrs, "NFAIL": yr.nfail, "NWDN": yr.nwdn,
                "NDFW": yr.nfail + yr.nwdn, "SDFW": yr.nfail + yr.nwdn,
                "NCRED": yr.credits, "NCRED1": yr.credits, "XGPA1": yr.gpa_points,
                "NCRED2": cum_cred if registered else 0.0,
                "XGPA2": round(cum_pts, 3) if registered else 0.0,
                "CREDTERM": yr.credits, "FFTE": round(yr.credits / 5.0, 3) if registered else 0.0,
                "XOAVE": st.oave if (st.oave is not None) else 0.0,
                "NOAVE": 1 if st.oave is not None else 0, "AVG": avg_band(st.oave),
                "APPLTY": st.applty, "APPTYPE": st.applty, "OUACTYPE": st.ouactype,
                "REGION": st.region, "RETAINED": retained, "GRADSEVEN": gradseven,
                "SWITCHA": switched, "SWITCH": "Y" if DEPT[last_dept][3] != DEPT[st.first_dept][3] else "N",
                "RETSTAR": "Y" if persisting else "N",
                "CONTINU": "Y" if cont else "N", "WEIGHT": 1.0,
            })
            yield [row[c] for c in URET_FACT_COLUMNS]


def enrolment_rows(students: list[Student], rng: random.Random):
    """Yield (stdcount_row_base, [(dept, weight), ...], cnt_flags) per student-term."""
    for st in students:
        for idx, yr in enumerate(st.years):
            y = yr.acadyear
            if y < ENROL_FIRST_YEAR:
                continue
            prev = st.years[idx - 1] if idx > 0 else None
            terms = [(term_code(y, "F"), "F")]
            if y + 1 <= CURRENT_YEAR:
                terms.append((term_code(y + 1, "W"), "W"))
            for tc, sem in terms:
                latest = tc == term_code(CURRENT_YEAR, "F")
                if yr.status == "C":
                    if sem == "W" and not yr.winter:
                        continue
                    in_f = (not latest) and rng.random() > 0.012
                    flags = ("I", "P") + (("F",) if in_f else ())
                    newret = "N" if (idx == 0 and sem == "F") else "R"
                elif (yr.status == "S" and sem == "F" and prev is not None and prev.status == "C"
                      and rng.random() < 0.10):
                    flags = ("I",)  # registered, then dropped before the official count
                    newret = "R"
                else:
                    continue
                if st.level_code == "UG":
                    load = 1.0 if st.ftpt == "F" else 0.5
                else:
                    load = 1.0 if st.ftpt == "F" else 0.4
                credits = round((yr.credits / 2.0) if (st.level_code == "UG" and yr.credits) else 2.5 * load, 2)
                fte = round(min(1.25, credits / 2.5), 3) if st.level_code == "UG" else load
                cal_year = int(tc[:4])
                age = cal_year - st.birth_year
                base = {
                    "PIDM": st.pidm, "TERM": tc, "FTE": fte, "FTPT": st.ftpt if fte >= 0.6 or st.ftpt == "P" else "P",
                    "LEVEL_CODE": st.level_code, "NEWRET_CODE": newret, "CITIZEN": st.citizen,
                    "IMMIG": None, "FORFEE": "Y" if st.feestat == "I" else "N",
                    "REGION_CODE": st.region, "AGE": age, "OUACTYPE": st.ouactype,
                    "COHORT": st.cohort, "APPLTY": st.applty if st.level_code == "UG" else None,
                    "AVG": avg_band(st.oave) if st.level_code == "UG" else None,
                    "OAVE": st.oave, "CAMP_CODE": "M", "ELGSTAT": None, "MCUCAT": None,
                    "CREDTERM": credits, "FEESTAT_CODE": st.feestat, "FFTE": round(fte / 2, 3),
                    "WGUFFTE": None, "NEW_WGUFFTE": None,
                }
                dept = yr.dept or st.first_dept
                if st.second_dept and st.level_code == "UG":
                    units = [(dept, 0.5), (st.second_dept if st.second_dept != dept else st.first_dept, 0.5)]
                    if units[0][0] == units[1][0]:
                        units = [(dept, 1.0)]
                else:
                    units = [(dept, 1.0)]
                yield base, units, flags, y


def build(db_path: Path = DEFAULT_DB_PATH, *, verbose: bool = True) -> Path:
    t0 = time.time()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = db_path.with_suffix(".building")
    if tmp_db.exists():
        tmp_db.unlink()

    sim = Simulator(SEED)
    sim.run()
    if verbose:
        n_ug = sum(1 for s in sim.students if s.level_code == "UG")
        print(f"  simulated {len(sim.students):,} students ({n_ug:,} undergraduate), "
              f"{len(sim.applications):,} applications  [{time.time() - t0:.1f}s]")

    con = duckdb.connect(str(tmp_db))
    built_at = datetime.now().replace(microsecond=0)
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as td:
        tw = TableWriter(con, Path(td))
        write_dimensions(con)

        counts["URET_FACT"] = tw.load("URET_FACT", URET_FACT_COLUMNS, uret_rows(sim.students),
                                      numeric=URET_NUMERIC,
                                      integer={"PIDM", "ACADYEAR", "COHORT", "YEARS", "COUNT", "LEVL"})

        # STDCOUNT / STDACADUNIT, expanded per count date, streamed in one pass
        rng = random.Random(SEED + 1)
        sc = tw.open("STDCOUNT", STDCOUNT_COLUMNS)
        su = tw.open("STDACADUNIT", STDACADUNIT_COLUMNS)
        for base, units, flags, acadyear in enrolment_rows(sim.students, rng):
            for cnt in flags:
                r = dict(base, STDCOUNT_ID=sc.n + 1, CNT=cnt)
                sc.write([r[c] for c in STDCOUNT_COLUMNS])
                for dept, w in units:
                    su.write([su.n + 1, base["PIDM"], base["TERM"], f"{DEPT[dept][3]}-{dept}", dept,
                              w, cnt, base["CITIZEN"], base["FEESTAT_CODE"], base["REGION_CODE"],
                              base["AGE"], round(base["FTE"] * w, 4), DEPT[dept][3], acadyear,
                              None, None])
        counts["STDCOUNT"] = tw.finish(
            "STDCOUNT", sc, numeric={"FTE", "OAVE", "CREDTERM", "FFTE", "WGUFFTE", "NEW_WGUFFTE"},
            integer={"STDCOUNT_ID", "PIDM", "AGE", "COHORT"})
        counts["STDACADUNIT"] = tw.finish(
            "STDACADUNIT", su, numeric={"WEIGHT", "WFTE", "WGUWFTE", "NEW_WGUWFTE"},
            integer={"STDACADUNIT_ID", "PIDM", "AGE", "ACADYEAR"})

        student_rows = [(s.pidm, s.sex, None, f"S{s.pidm}", dict(SEXES)[s.sex], s.birth_year, None)
                        for s in sim.students]
        counts["STUDENT"] = tw.load("STUDENT", ["PIDM", "SEX", "BIRTHDATE", "BANNER_ID", "GENDER_DESC",
                                                "BIRTH_YEAR", "STDNAME"], student_rows,
                                    integer={"PIDM", "BIRTH_YEAR"})

        def adm_iter():
            for a in sim.applications:
                p = a["PROF"]
                row = dict.fromkeys(ADM_FACT_COLUMNS)
                row.update({
                    "PIDM": a["PIDM"], "ACADYEAR": a["ACADYEAR"], "CNT": "F",
                    "COUNTRY": p["citizen"], "OAVE": p["oave"], "APPTYPE": p["applty"],
                    "APPLTY": p["applty"], "PROGRAM": f"{a['DEGREE']}-{a['DEPT']}",
                    "DEGREE": a["DEGREE"], "ACADUNIT": a["DEPT"], "FACULTY": a["FACULTY"],
                    "WEIGHT": round(a["WEIGHT"], 6), "CHOICE": a["CHOICE"],
                    "REGION": p["region"], "SEX": p["sex"], "OUACTYPE": p["ouactype"],
                    "APPL": round(a["WEIGHT"], 6), "APPR": round(a["APPR"], 6),
                    "REFU": round(a["REFU"], 6), "WITD": round(a["WITD"], 6),
                    "CONF": a["CONF"], "DECL": round(a["DECL"], 6), "NOAN": round(a["NOAN"], 6),
                    "ATCU": a["ATCU"], "AVG": avg_band(p["oave"]), "LEVL": "UG",
                    "FTPT": p["ftpt"], "APPYEAR": a["ACADYEAR"],
                    "WOAVE": round(p["oave"] * a["WEIGHT"], 6) if p["oave"] is not None else 0.0,
                    "OAVE_WEIGHT": round(a["WEIGHT"], 6) if p["oave"] is not None else 0.0,
                })
                yield [row[c] for c in ADM_FACT_COLUMNS]

        counts["ADM_FACT"] = tw.load("ADM_FACT", ADM_FACT_COLUMNS, adm_iter(), numeric=ADM_NUMERIC,
                                     integer={"PIDM", "ACADYEAR", "CHOICE", "APPYEAR"})

    # ---- provenance: load log + build metadata ----
    con.execute('CREATE TABLE "LOAD_LOG" ("TABLE_NAME" VARCHAR, "STAR" VARCHAR, '
                '"LOADED_AT" TIMESTAMP, "ROW_COUNT" BIGINT, "LOADED_BY" VARCHAR)')
    tables = [r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main' "
        "and table_name <> 'LOAD_LOG' order by 1").fetchall()]
    for t in tables:
        star = ("RETENTION" if t.startswith("URET_") else "ADMISSIONS" if t.startswith("ADM_")
                else "ENROLMENT")
        loaded = built_at - timedelta(days=RETENTION_LOAD_LAG_DAYS) if star == "RETENTION" else built_at
        n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
        con.execute('INSERT INTO "LOAD_LOG" VALUES (?, ?, ?, ?, ?)',
                    [t, star, loaded, n, "synthetic_warehouse.py"])
    con.execute('CREATE TABLE "WAREHOUSE_META" ("KEY" VARCHAR, "VALUE" VARCHAR)')
    con.executemany('INSERT INTO "WAREHOUSE_META" VALUES (?, ?)', [
        ("data_origin", "SYNTHETIC - generated by oirp_agent.synthetic_warehouse; not real data"),
        ("generator_version", GENERATOR_VERSION), ("seed", str(SEED)),
        ("built_at", built_at.isoformat()), ("current_academic_year", f"{CURRENT_YEAR}/{str(CURRENT_YEAR + 1)[2:]}"),
    ])
    con.close()
    if db_path.exists():
        db_path.unlink()
    tmp_db.rename(db_path)
    if verbose:
        for t, n in counts.items():
            print(f"  {t:<12} {n:>10,} rows")
        print(f"  built {db_path} in {time.time() - t0:.1f}s")
    return db_path


def ensure_built(db_path: Path = DEFAULT_DB_PATH) -> Path:
    if not db_path.exists():
        print(f"Synthetic warehouse not found at {db_path}; building it (one-time, ~1 min)...")
        build(db_path)
    return db_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the synthetic CUDW-shaped warehouse.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    ap.add_argument("--force", action="store_true", help="Rebuild even if the file exists.")
    args = ap.parse_args()
    if args.db.exists() and not args.force:
        print(f"{args.db} already exists (use --force to rebuild).")
        return
    build(args.db)


if __name__ == "__main__":
    main()
