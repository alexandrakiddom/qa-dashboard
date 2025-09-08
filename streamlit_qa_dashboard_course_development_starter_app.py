import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta

st.set_page_config(page_title="QA Dashboard – Course Dev", layout="wide")
st.title("📊 QA Dashboard for Course Development")
st.caption("Track issues, progress, and quality signals while building courses in a learning platform.")

# -----------------------------
# 1) Load Data
# -----------------------------
@st.cache_data
def load_data(file) -> pd.DataFrame:
    df = pd.read_csv(file, parse_dates=["created_at", "updated_at"]) if file else example_data()
    # normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    # coerce categories
    cat_cols = ["status", "severity", "item_type", "course_name", "assignee", "reporter"]
    for c in cat_cols:
        if c in df.columns:
            df[c] = df[c].astype("category")
    return df

@st.cache_data
def example_data(n_courses: int = 3, n_rows: int = 250) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    today = pd.Timestamp.today().normalize()

    courses = [f"Course {i+1}" for i in range(n_courses)]
    units = [f"Unit {i+1}" for i in range(8)]
    item_types = ["Video", "Quiz", "Reading", "Assignment", "Slide"]
    statuses = pd.CategoricalDtype(["Open", "In Progress", "Fixed", "Verified", "Closed"], ordered=True)
    severities = ["Low", "Medium", "High", "Critical"]

    rows = []
    for i in range(n_rows):
        created = today - timedelta(days=int(rng.integers(0, 40)))
        updated = created + timedelta(days=int(rng.integers(0, 15)))
        status = rng.choice(statuses.categories, p=[0.25,0.25,0.2,0.2,0.1])
        rows.append({
            "issue_id": f"ISSUE-{1000+i}",
            "course_name": rng.choice(courses),
            "unit": rng.choice(units),
            "item_id": f"ITEM-{rng.integers(1, 9999)}",
            "item_type": rng.choice(item_types),
            "status": status,
            "severity": rng.choice(severities, p=[0.45,0.35,0.15,0.05]),
            "reporter": rng.choice(["QA", "Author", "Reviewer", "Student"]),
            "assignee": rng.choice(["Alex", "Sam", "Riley", "Jordan", "Kim"]),
            "created_at": created,
            "updated_at": updated,
            "notes": rng.choice(["typo", "broken link", "layout", "audio", "timing", "grading", "accessibility"]),
            "browser": rng.choice(["Chrome", "Safari", "Firefox", "Edge"]),
            "environment": rng.choice(["Staging", "Production"])
        })
    df = pd.DataFrame(rows)
    df["status"] = df["status"].astype(statuses)
    # SLA target (days) based on severity
    sla_map = {"Critical":2, "High":5, "Medium":10, "Low":15}
    df["sla_days"] = df["severity"].map(sla_map)
    df["age_days"] = (pd.Timestamp.today() - df["created_at"]).dt.days
    df["sla_breached"] = df["age_days"] > df["sla_days"]
    return df

with st.sidebar:
    st.header("Data Source")
    uploaded = st.file_uploader("Upload CSV (optional)", type=["csv"]) 
    df = load_data(uploaded)

    st.header("Filters")
    course = st.multiselect("Course", sorted(df["course_name"].unique().tolist()))
    unit = st.multiselect("Unit", sorted(df["unit"].unique().tolist()))
    status = st.multiselect("Status", list(df["status"].cat.categories))
    severity = st.multiselect("Severity", sorted(df["severity"].unique().tolist()))
    assignee = st.multiselect("Assignee", sorted(df["assignee"].unique().tolist()))

# Apply filters
fdf = df.copy()
if course: fdf = fdf[fdf["course_name"].isin(course)]
if unit: fdf = fdf[fdf["unit"].isin(unit)]
if status: fdf = fdf[fdf["status"].isin(status)]
if severity: fdf = fdf[fdf["severity"].isin(severity)]
if assignee: fdf = fdf[fdf["assignee"].isin(assignee)]

# -----------------------------
# 2) KPI Cards
# -----------------------------
open_mask = fdf["status"].isin(["Open", "In Progress"]) 
open_issues = int(open_mask.sum())
verified = int((fdf["status"] == "Verified").sum())
closed = int((fdf["status"] == "Closed").sum())
critical_open = int(((fdf["severity"] == "Critical") & open_mask).sum())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Open (incl. In Progress)", open_issues)
col2.metric("Verified", verified)
col3.metric("Closed", closed)
col4.metric("Critical Open", critical_open)

# SLA
sla_breaches = int((fdf["sla_breached"] & open_mask).sum())
with st.expander("SLA Overview", expanded=False):
    st.write(f"SLA breaches among open items: **{sla_breaches}**")
    sla_by_sev = fdf[open_mask].groupby("severity")["sla_breached"].mean().reset_index()
    sla_by_sev["breach_rate"] = (sla_by_sev["sla_breached"]*100).round(1)
    chart = alt.Chart(sla_by_sev).mark_bar().encode(
        x=alt.X("severity", sort=["Low","Medium","High","Critical"]),
        y="breach_rate",
        tooltip=["severity","breach_rate"]
    ).properties(height=180)
    st.altair_chart(chart, use_container_width=True)

# -----------------------------
# 3) Trends & Distributions
# -----------------------------
left, right = st.columns(2)

# Created per day (throughput)
created_daily = (
    fdf.assign(created_date=fdf["created_at"].dt.date)
       .groupby("created_date").size().reset_index(name="created")
)
created_line = alt.Chart(created_daily).mark_line(point=True).encode(
    x="created_date:T", y="created:Q", tooltip=["created_date:T","created:Q"]
).properties(title="Issues Created per Day", height=240)
left.altair_chart(created_line, use_container_width=True)

# Status distribution
status_counts = fdf["status"].value_counts().rename_axis("status").reset_index(name="count")
status_bar = alt.Chart(status_counts).mark_bar().encode(
    x=alt.X("status", sort=list(df["status"].cat.categories)),
    y="count",
    tooltip=["status","count"]
).properties(title="Status Distribution", height=240)
right.altair_chart(status_bar, use_container_width=True)

# Severity by course
sev_course = fdf.groupby(["course_name","severity"]).size().reset_index(name="count")
sev_stack = alt.Chart(sev_course).mark_bar().encode(
    x=alt.X("count:Q", stack="normalize"), y=alt.Y("course_name:N", sort="-x"), color="severity:N",
    tooltip=["course_name","severity","count"]
).properties(title="Severity Mix by Course", height=240)
st.altair_chart(sev_stack, use_container_width=True)

# -----------------------------
# 4) Aging & Work-in-Progress
# -----------------------------
age_bins = pd.cut(fdf["age_days"], bins=[-1,2,5,10,20,999], labels=["≤2d","3–5d","6–10d","11–20d",">20d"])
age_dist = pd.DataFrame({"age_bucket": age_bins}).value_counts().reset_index(name="count")
age_dist = age_dist.rename(columns={"index":"", 0:"count"})
age_chart = alt.Chart(age_dist).mark_bar().encode(
    x=alt.X("age_bucket:N", title="Age (days)"), y="count:Q", tooltip=["age_bucket","count"]
).properties(title="Issue Age Distribution", height=220)
st.altair_chart(age_chart, use_container_width=True)

# WIP table
st.subheader("Work in Progress (Open & In Progress)")
st.dataframe(fdf[open_mask].sort_values(["severity","age_days"], ascending=[False, False])[ 
    ["issue_id","course_name","unit","item_type","severity","status","assignee","age_days","sla_breached","updated_at","notes"]
])

# -----------------------------
# 5) Detail Explorer
# -----------------------------
st.subheader("Detail Explorer")
with st.expander("Filter & search details"):
    q = st.text_input("Search notes/IDs (simple contains match)")
    temp = fdf.copy()
    if q:
        q_lower = q.lower()
        temp = temp[
            temp.apply(lambda r: q_lower in str(r["issue_id"]).lower() \
                                   or q_lower in str(r["notes"]).lower() \
                                   or q_lower in str(r["item_id"]).lower(), axis=1)
        ]
    st.dataframe(temp.sort_values("updated_at", ascending=False))

# -----------------------------
# 6) Data Dictionary
# -----------------------------
with st.expander("Data Dictionary / Expected Columns", expanded=False):
    st.markdown(
        """
        **Required columns** (case-insensitive):
        - `issue_id` – unique identifier for the QA issue
        - `course_name` – name of the course
        - `unit` – unit/module identifier
        - `item_id` – affected item id
        - `item_type` – e.g., Video, Quiz, Reading, Assignment
        - `status` – one of: Open, In Progress, Fixed, Verified, Closed (ordered)
        - `severity` – Low, Medium, High, Critical
        - `reporter`, `assignee`
        - `created_at`, `updated_at` – ISO dates or recognizable strings
        
        **Optional but recommended**:
        - `browser`, `environment`, `notes`
        - `sla_days` (int) – if omitted, derived from severity: Critical=2, High=5, Medium=10, Low=15
        
        The app also derives:
        - `age_days` = today − created_at (days)
        - `sla_breached` = age_days > sla_days
        """
    )

st.success("Tip: Upload your CSV in the sidebar to replace the demo data. Then refine filters and export views.")
