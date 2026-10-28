
import json
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

PRACTICES_FILE = DATA_DIR / "practices.csv"
SCORED_FILE = DATA_DIR / "scored_practices.csv"
DRAFTS_FILE = DATA_DIR / "outreach_drafts.csv"
COMPLIANCE_FILE = DATA_DIR / "compliance_report.csv"

st.set_page_config(
    page_title="GP Practice Intelligence",
    page_icon="🏥",
    layout="wide",
)

st.title("GP Practice Intelligence & Outreach Engine")
st.caption(
    "Explore publicly sourced practice information, lead scores, "
    "outreach drafts, and review flags."
)


@st.cache_data
def load_csv(path_string):
    path = Path(path_string)

    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, encoding="utf-8-sig").fillna("")
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        st.warning(f"Could not read {path.name}: {exc}")
        return pd.DataFrame()


practices = load_csv(str(PRACTICES_FILE))
scored = load_csv(str(SCORED_FILE))
drafts = load_csv(str(DRAFTS_FILE))
compliance = load_csv(str(COMPLIANCE_FILE))


def merge_data():
    """Combine the project outputs using source practice names."""
    if scored.empty:
        return practices.copy()

    result = scored.copy()

    if not drafts.empty and "practice_name" in drafts.columns:
        draft_columns = [
            column for column in [
                "practice_name",
                "recipient_email",
                "subject",
                "draft_body",
                "draft_status",
            ]
            if column in drafts.columns
        ]
        draft_data = drafts[draft_columns].drop_duplicates(
            subset=["practice_name"]
        )
        result = result.merge(
            draft_data,
            on="practice_name",
            how="left",
            suffixes=("", "_draft"),
        )

    if (
        not compliance.empty
        and "practice_name" in compliance.columns
    ):
        review_columns = [
            column for column in [
                "practice_name",
                "compliance_status",
                "flag_count",
                "flag_categories",
                "compliance_flags",
            ]
            if column in compliance.columns
        ]
        review_data = compliance[review_columns].drop_duplicates(
            subset=["practice_name"]
        )
        result = result.merge(
            review_data,
            on="practice_name",
            how="left",
            suffixes=("", "_review"),
        )

    return result


data = merge_data()

# Sidebar controls
st.sidebar.header("Dashboard controls")

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

search_text = st.sidebar.text_input(
    "Search practices",
    placeholder="Practice name, suburb, or address",
)

available_tiers = (
    sorted(data["lead_tier"].astype(str).unique().tolist())
    if "lead_tier" in data.columns
    else []
)

selected_tiers = st.sidebar.multiselect(
    "Lead tier",
    options=available_tiers,
    default=available_tiers,
)

review_options = (
    sorted(data["compliance_status"].astype(str).unique().tolist())
    if "compliance_status" in data.columns
    else []
)

selected_reviews = st.sidebar.multiselect(
    "Compliance status",
    options=review_options,
    default=review_options,
)

filtered = data.copy()

if search_text.strip():
    searchable_columns = [
        column for column in [
            "practice_name", "suburb", "address", "phone", "email"
        ]
        if column in filtered.columns
    ]

    if searchable_columns:
        mask = pd.Series(False, index=filtered.index)
        for column in searchable_columns:
            mask |= filtered[column].astype(str).str.contains(
                search_text.strip(),
                case=False,
                regex=False,
                na=False,
            )
        filtered = filtered[mask]

if selected_tiers and "lead_tier" in filtered.columns:
    filtered = filtered[
        filtered["lead_tier"].astype(str).isin(selected_tiers)
    ]

if selected_reviews and "compliance_status" in filtered.columns:
    filtered = filtered[
        filtered["compliance_status"].astype(str).isin(
            selected_reviews
        )
    ]

# Overview metrics
st.subheader("Overview")

total_practices = len(data)
high_leads = (
    int((data["lead_tier"] == "High").sum())
    if "lead_tier" in data.columns else 0
)
medium_leads = (
    int((data["lead_tier"] == "Medium").sum())
    if "lead_tier" in data.columns else 0
)
low_leads = (
    int((data["lead_tier"] == "Low").sum())
    if "lead_tier" in data.columns else 0
)

if "lead_score" in data.columns and not data.empty:
    scores = pd.to_numeric(data["lead_score"], errors="coerce")
    average_score = scores.mean()
else:
    average_score = float("nan")

metric1, metric2, metric3, metric4, metric5 = st.columns(5)
metric1.metric("Practices", total_practices)
metric2.metric(
    "Average lead score",
    f"{average_score:.1f}/100"
    if pd.notna(average_score) else "N/A",
)
metric3.metric("High tier", high_leads)
metric4.metric("Medium tier", medium_leads)
metric5.metric("Low tier", low_leads)

if total_practices == 0:
    st.info(
        "No extracted practices found yet. Run the extraction pipeline "
        "and refresh this dashboard when data is available."
    )

# Main tabs
tab_overview, tab_practices, tab_outreach, tab_compliance, tab_exports = (
    st.tabs([
        "Overview",
        "Practice explorer",
        "Outreach drafts",
        "Compliance review",
        "Exports",
    ])
)

with tab_overview:
    st.subheader("Lead tier distribution")

    if total_practices and "lead_tier" in data.columns:
        tier_counts = (
            data["lead_tier"].value_counts()
            .reindex(["High", "Medium", "Low"], fill_value=0)
        )
        st.bar_chart(tier_counts)
    else:
        st.info("Lead tier chart will appear when scored data is available.")

    st.subheader("Highest-scoring practices")

    if not filtered.empty and "lead_score" in filtered.columns:
        top = filtered.copy()
        top["lead_score"] = pd.to_numeric(
            top["lead_score"], errors="coerce"
        )
        display_columns = [
            column for column in [
                "practice_name", "suburb", "lead_score",
                "lead_tier", "compliance_status"
            ]
            if column in top.columns
        ]
        st.dataframe(
            top.sort_values("lead_score", ascending=False)[
                display_columns
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No practices match the selected filters.")

with tab_practices:
    st.subheader("Practice explorer")

    if not filtered.empty:
        display_columns = [
            column for column in [
                "practice_name", "address", "suburb", "phone", "email",
                "services", "bulk_billing", "online_booking",
                "telehealth", "doctor_count", "confidence",
                "lead_score", "lead_tier", "score_reasons"
            ]
            if column in filtered.columns
        ]

        st.dataframe(
            filtered[display_columns],
            use_container_width=True,
            hide_index=True,
        )

        names = filtered["practice_name"].astype(str).tolist()
        selected_name = st.selectbox(
            "Inspect a practice",
            options=names,
        )

        matches = filtered[
            filtered["practice_name"].astype(str) == selected_name
        ]

        if not matches.empty:
            record = matches.iloc[0]

            st.markdown(f"### {selected_name}")

            left, right = st.columns(2)

            with left:
                st.write("**Address:**", record.get("address", "") or "Unknown")
                st.write("**Suburb:**", record.get("suburb", "") or "Unknown")
                st.write("**Phone:**", record.get("phone", "") or "Unknown")
                st.write("**Email:**", record.get("email", "") or "Unknown")

            with right:
                st.write("**Bulk billing:**", record.get("bulk_billing", "") or "Unknown")
                st.write("**Online booking:**", record.get("online_booking", "") or "Unknown")
                st.write("**Telehealth:**", record.get("telehealth", "") or "Unknown")
                st.write("**Doctor count:**", record.get("doctor_count", "") or "Unknown")

            with st.expander("View scoring explanation"):
                reasons = record.get("score_reasons", "")
                try:
                    parsed_reasons = json.loads(reasons) if reasons else []
                    if isinstance(parsed_reasons, list):
                        for reason in parsed_reasons:
                            st.write(f"- {reason}")
                    else:
                        st.write(reasons or "No scoring explanation available.")
                except (json.JSONDecodeError, TypeError):
                    st.write(reasons or "No scoring explanation available.")

    else:
        st.info("No practices match the selected filters.")


with tab_outreach:
    st.subheader("Outreach drafts")

    if not filtered.empty and "draft_body" in filtered.columns:
        draft_rows = filtered[
            filtered["draft_body"].astype(str).str.strip() != ""
        ]

        if draft_rows.empty:
            st.info("No outreach drafts are available for these practices.")
        else:
            for i, (_, record) in enumerate(draft_rows.iterrows()):
                name = record.get("practice_name", "Unknown practice")

                with st.expander(str(name)):
                    st.write(
                        "**Recipient:**",
                        record.get("recipient_email", "") or "Missing",
                    )
                    st.write("**Subject:**", record.get("subject", ""))

                    st.text_area(
                        "Draft email",
                        value=str(record.get("draft_body", "")),
                        height=260,
                        key=f"draft_{name}_{i}",
                    )

                    st.caption(
                        "Draft only. The dashboard does not send emails."
                    )
    else:
        st.info(
            "No draft data is available. Run python outreach.py first."
        )


with tab_compliance:
    st.subheader("Compliance review")

    if not filtered.empty and "compliance_status" in filtered.columns:
        review_columns = [
            column for column in [
                "practice_name", "recipient_email", "compliance_status",
                "flag_count", "flag_categories", "compliance_flags",
                "review_scope",
            ]
            if column in filtered.columns
        ]

        st.dataframe(
            filtered[review_columns],
            use_container_width=True,
            hide_index=True,
        )

        if "compliance_flags" in filtered.columns:
            for _, record in filtered.iterrows():
                with st.expander(
                    f"Review notes — {record.get('practice_name', 'Unknown')}"
                ):
                    st.write(
                        record.get("compliance_flags", "")
                        or "No notes available."
                    )
    else:
        st.info(
            "No compliance report is available. Run python compliance.py first."
        )

with tab_exports:
    st.subheader("Download project data")

    exports = [
        ("Practices", practices, "practices.csv"),
        ("Scored practices", scored, "scored_practices.csv"),
        ("Outreach drafts", drafts, "outreach_drafts.csv"),
        ("Compliance report", compliance, "compliance_report.csv"),
    ]

    for label, frame, filename in exports:
        st.markdown(f"**{label}**")

        if frame.empty:
            st.caption("No data available yet.")
        else:
            st.download_button(
                label=f"Download {filename}",
                data=frame.to_csv(index=False).encode("utf-8-sig"),
                file_name=filename,
                mime="text/csv",
                key=f"download_{filename}",
            )

st.divider()
st.caption(
    "Data comes from collected public practice websites and local processing. "
    "Lead scores are heuristic, not verified commercial predictions. "
    "Compliance flags are preliminary checks, not legal advice. "
    "Verify source evidence and contact permissions before outreach."
)
