"""GeoQueryBench modular Streamlit entry point.

Integration owner: Chaitanya Neerukattu.

This file connects the independently maintained team modules for the expanded
GeoQueryBench review workflow. It displays client-supplied questions/results;
it does not execute uploaded SQL or Python.
"""
from __future__ import annotations

from pathlib import Path
import os

import pandas as pd
import streamlit as st

from geoquerybench.config import APP_VERSION, TEAM_MEMBERS
from geoquerybench.data_loader import (
    expanded_dataset_diagnostics,
    expected_result_file,
    load_expanded_questions,
    load_gold_manifest,
)
from geoquerybench.navigation_reporting import (
    STATUS_FILTERS,
    assigned_ids,
    next_pending_assigned,
    resume_pending,
    reviewer_statuses,
    visible_ids,
)
from geoquerybench.review_workflow import (
    EXPANDED_VERDICTS,
    review_errors,
    upload_visible,
    verdict_is_complete,
)
from geoquerybench.security import require_access
from geoquerybench.storage import (
    assign_unassigned_evenly,
    expanded_evidence_path,
    load_expanded_assignments,
    load_expanded_reviews,
    persist_expanded_evidence,
    save_expanded_assignment,
    save_expanded_review,
)
from geoquerybench.visuals import render_expanded_result


ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = Path(
    os.getenv("GQB_EXPANDED_QUESTIONS", str(ROOT / "data" / "geoquerybench_questions.csv"))
).expanduser()
GOLD_DIR = Path(os.getenv("GQB_GOLD_DIR", str(ROOT / "data"))).expanduser()
DB_PATH = Path(
    os.getenv("GQB_EXPANDED_DB", str(ROOT / "runtime" / "expanded_reviews.sqlite3"))
).expanduser()

st.set_page_config(
    page_title="GeoQueryBench Review Workspace",
    page_icon="🧭",
    layout="wide",
)


def _jump_to(qid: str, notice: str | None = None) -> None:
    """Apply question navigation before widgets are recreated on the next rerun."""
    st.session_state["expanded_nav_target"] = qid
    if notice:
        st.session_state["expanded_nav_notice"] = notice
    st.rerun()


def _load_workspace():
    if not QUESTIONS_PATH.is_file():
        st.error(
            "Expanded question CSV is missing. Add data/geoquerybench_questions.csv "
            "or set GQB_EXPANDED_QUESTIONS."
        )
        st.stop()
    try:
        questions = load_expanded_questions(QUESTIONS_PATH)
    except Exception as exc:
        st.error(f"Question dataset is invalid: {exc}")
        st.stop()
    manifest = load_gold_manifest(GOLD_DIR)
    reviews = load_expanded_reviews(DB_PATH)
    assignments = load_expanded_assignments(DB_PATH)
    return questions, manifest, reviews, assignments


def _review_tab(questions, manifest, reviews, assignments, reviewer):
    all_ids = questions["qid"].astype(str).tolist()
    mine_rows = (
        reviews.loc[reviews["reviewer"].eq(reviewer)].to_dict("records")
        if reviewer != "Guest reviewer" and not reviews.empty
        else []
    )
    statuses = reviewer_statuses(mine_rows, reviewer)
    my_ids = assigned_ids(all_ids, assignments, reviewer)

    if st.session_state.get("expanded_nav_reviewer") != reviewer:
        st.session_state["expanded_nav_reviewer"] = reviewer
        st.session_state.pop("expanded_qid", None)
        st.session_state.pop("expanded_nav_target", None)
        st.session_state["expanded_status_filter"] = "All"
        st.session_state["expanded_category_filter"] = "All"
        st.session_state["expanded_my_only"] = True

    target = st.session_state.pop("expanded_nav_target", None)
    if target in all_ids:
        st.session_state["expanded_qid"] = target
        st.session_state["expanded_status_filter"] = "All"
        st.session_state["expanded_category_filter"] = "All"
        st.session_state["expanded_my_only"] = True

    notice = st.session_state.pop("expanded_nav_notice", None)
    if notice:
        st.success(notice)

    if reviewer != "Guest reviewer":
        completed = sum(statuses.get(qid) in {"Pass", "Fail"} for qid in my_ids)
        st.caption(
            f"Your progress: {completed}/{len(my_ids)} assigned questions completed; "
            "Needs clarification remains pending."
        )

    subset = questions.copy()
    category_col = next((c for c in ("scenario", "task", "difficulty") if c in subset.columns), None)
    if category_col:
        categories = ["All"] + sorted(subset[category_col].astype(str).unique().tolist())
        selected_category = st.selectbox(
            "Question category", categories, key="expanded_category_filter"
        )
        if selected_category != "All":
            subset = subset.loc[subset[category_col].astype(str).eq(selected_category)]

    if reviewer != "Guest reviewer":
        mine_only = st.checkbox(
            "Only my assigned questions", value=True, key="expanded_my_only"
        )
        if mine_only:
            subset = subset.loc[subset["qid"].map(assignments).eq(reviewer)]
        status_filter = st.selectbox(
            "My review status", STATUS_FILTERS, key="expanded_status_filter"
        )
        allowed_ids = set(visible_ids(subset["qid"].tolist(), statuses, status_filter))
        subset = subset.loc[subset["qid"].isin(allowed_ids)]
        st.caption(f"{len(subset):,} questions match the current filters.")

        if st.button("▶ Resume my next pending question", disabled=not my_ids):
            next_qid = resume_pending(all_ids, assignments, reviewer, statuses, mine_rows)
            if next_qid is None:
                st.info("No pending assigned question remains.")
            else:
                _jump_to(next_qid)

    qids = subset["qid"].astype(str).tolist()
    if not qids:
        st.info("No questions match the current filters.")
        return

    if st.session_state.get("expanded_qid") not in qids:
        st.session_state["expanded_qid"] = qids[0]
    qid = st.selectbox("Question ID", qids, key="expanded_qid")
    index = qids.index(qid)
    st.caption(
        f"Question {index + 1} of {len(qids)} · Assigned: {assignments.get(qid, 'Not assigned')}"
    )
    left_nav, right_nav = st.columns(2)
    if left_nav.button("← Previous question", disabled=index == 0):
        _jump_to(qids[index - 1])
    if right_nav.button("Next question →", disabled=index + 1 >= len(qids)):
        _jump_to(qids[index + 1])

    row = subset.loc[subset["qid"].astype(str).eq(qid)].iloc[0]
    en, zh = st.columns(2)
    en.markdown("**English**")
    en.write(row.get("question_en", ""))
    zh.markdown("**中文**")
    zh.write(row.get("question_zh", ""))

    language = "python" if str(row.get("task", "")).lower().startswith("python") else "sql"
    with st.expander("Client-supplied gold code", expanded=True):
        st.code(str(row.get("gold_code", "")), language=language)

    official = expected_result_file(qid, GOLD_DIR, manifest)
    previous = (
        reviews.loc[reviews["qid"].astype(str).eq(qid) & reviews["reviewer"].eq(reviewer)]
        if reviewer != "Guest reviewer" and not reviews.empty
        else pd.DataFrame()
    )
    past = previous.iloc[0] if not previous.empty else None
    initial = (
        EXPANDED_VERDICTS.index(str(past["verdict"]))
        if past is not None and str(past["verdict"]) in EXPANDED_VERDICTS
        else 0
    )

    verdict = st.selectbox(
        "Result of independently executed query",
        EXPANDED_VERDICTS,
        index=initial,
        key=f"verdict_{qid}_{reviewer}",
    )
    st.caption(
        "Pass = matches official result; Fail = materially differs; "
        "Needs clarification = cannot determine safely."
    )

    pass_confirmed = False
    if verdict == "Pass":
        st.success("Matching result: no evidence upload is required.")
        pass_confirmed = st.checkbox(
            "I independently ran the query and checked its output against the official result.",
            key=f"confirm_{qid}_{reviewer}",
        )
    elif verdict == "Fail":
        st.warning("Upload the differing executed result and explain the mismatch before saving.")
    elif verdict == "Needs clarification":
        st.info("Explain the uncertainty; upload is optional.")

    if official is None:
        st.warning(
            "Official result is unavailable. Pass and Fail cannot be saved until the reference exists."
        )

    official_col, evidence_col = st.columns(2)
    with official_col:
        st.subheader("Official reference result")
        if official is not None:
            st.caption(official.name)
            render_expanded_result(official, official.name, key_prefix=f"official_{qid}")

    upload = None
    with evidence_col:
        if upload_visible(verdict):
            st.subheader("Independently executed result")
            upload = st.file_uploader(
                "Upload differing output (required for Fail; maximum 10 MB)",
                type=["csv", "txt", "json", "geojson", "png", "jpg", "jpeg"],
                key=f"upload_{qid}_{reviewer}",
            )
            if upload is not None:
                try:
                    render_expanded_result(
                        upload.getvalue(), upload.name, key_prefix=f"executed_{qid}"
                    )
                except ValueError as exc:
                    st.error(str(exc))
                    upload = None
        else:
            st.caption("Upload is hidden for matching output to save review time.")

    if past is not None and pd.notna(past.get("uploaded_sha256")) and pd.notna(past.get("uploaded_name")):
        prior = expanded_evidence_path(
            str(past["uploaded_sha256"]), str(past["uploaded_name"]), database_file=DB_PATH
        )
        if prior is not None and prior.is_file():
            with st.expander("Previously saved evidence"):
                st.download_button(
                    "Download saved evidence",
                    prior.read_bytes(),
                    file_name=Path(str(past["uploaded_name"])).name,
                    key=f"prior_evidence_{qid}_{reviewer}",
                )

    notes = st.text_area(
        "Comments / reason for mismatch",
        value=str(past["notes"]) if past is not None else "",
        key=f"notes_{qid}_{reviewer}",
        placeholder="Optional for Pass; required for Fail or Needs clarification.",
    )

    save_col, save_next_col = st.columns(2)
    save_clicked = save_col.button(
        "Save review", disabled=reviewer == "Guest reviewer"
    )
    save_next_clicked = save_next_col.button(
        "Save & Next pending →",
        disabled=reviewer == "Guest reviewer",
        type="primary",
    )

    if save_clicked or save_next_clicked:
        errors = review_errors(
            verdict,
            notes,
            official is not None,
            upload is not None,
            pass_confirmed,
        )
        if errors:
            for error in errors:
                st.error(error)
            return

        filename = digest = None
        if upload is not None and upload_visible(verdict):
            filename, digest, _ = persist_expanded_evidence(
                upload.name, upload.getvalue(), database_file=DB_PATH
            )
        save_expanded_review(
            qid,
            reviewer,
            verdict,
            notes,
            filename,
            digest,
            database_file=DB_PATH,
        )

        if save_next_clicked:
            refreshed = dict(statuses)
            refreshed[qid] = verdict
            next_qid = next_pending_assigned(
                all_ids, assignments, reviewer, refreshed, current_id=qid
            )
            if next_qid is not None and next_qid != qid:
                _jump_to(
                    next_qid,
                    f"{qid}: review saved. Opened your next pending assigned question.",
                )
            if next_qid == qid:
                st.success("Review saved. This is your only remaining pending assigned question.")
            else:
                st.success("Review saved. No pending assigned questions remain.")
        else:
            st.success("Review saved.")


def _assignment_tab(questions, assignments, reviewer):
    st.subheader("Reviewer assignments")
    if reviewer == "Guest reviewer":
        st.warning("Select your reviewer name before changing assignments.")
        return

    all_ids = questions["qid"].astype(str).tolist()
    counts = {
        member: sum(owner == member for qid, owner in assignments.items() if qid in all_ids)
        for member in TEAM_MEMBERS
    }
    st.dataframe(
        pd.DataFrame([{"Reviewer": member, "Assigned": counts[member]} for member in TEAM_MEMBERS]),
        hide_index=True,
        use_container_width=True,
    )

    if st.button("Assign previously unassigned questions evenly"):
        added = assign_unassigned_evenly(all_ids, TEAM_MEMBERS, database_file=DB_PATH)
        st.success(f"Assigned {added} previously unassigned questions.")
        st.rerun()

    selected_qid = st.selectbox("Reassign a specific question", all_ids)
    current_owner = assignments.get(selected_qid)
    owner_index = TEAM_MEMBERS.index(current_owner) if current_owner in TEAM_MEMBERS else 0
    new_owner = st.selectbox("New primary reviewer", TEAM_MEMBERS, index=owner_index)
    if st.button("Save this assignment"):
        save_expanded_assignment(selected_qid, new_owner, database_file=DB_PATH)
        st.success(f"{selected_qid} assigned to {new_owner}.")
        st.rerun()


def _progress_tab(questions, reviews, assignments):
    st.subheader("Progress and export")
    all_ids = questions["qid"].astype(str).tolist()
    rows = []
    for member in TEAM_MEMBERS:
        assigned = [qid for qid in all_ids if assignments.get(qid) == member]
        member_reviews = reviews.loc[reviews["reviewer"].eq(member)] if not reviews.empty else pd.DataFrame()
        completed = (
            int(member_reviews["verdict"].map(verdict_is_complete).sum())
            if not member_reviews.empty
            else 0
        )
        rows.append({"Reviewer": member, "Assigned": len(assigned), "Completed": completed})
    progress = pd.DataFrame(rows)
    st.dataframe(progress, hide_index=True, use_container_width=True)
    if not progress.empty:
        st.bar_chart(progress.set_index("Reviewer")[["Assigned", "Completed"]])

    if not reviews.empty:
        st.download_button(
            "Download reviews CSV",
            reviews.to_csv(index=False).encode("utf-8-sig"),
            file_name="expanded_reviews.csv",
            mime="text/csv",
        )
        st.dataframe(reviews, hide_index=True, use_container_width=True)
    else:
        st.info("No reviews saved yet.")

    assignment_frame = pd.DataFrame(
        [{"qid": qid, "reviewer": owner} for qid, owner in assignments.items()]
    )
    st.download_button(
        "Download assignments CSV",
        assignment_frame.to_csv(index=False).encode("utf-8-sig"),
        file_name="expanded_assignments.csv",
        mime="text/csv",
    )


def main():
    require_access()
    questions, manifest, reviews, assignments = _load_workspace()

    st.title("🧭 GeoQueryBench · Modular expanded review")
    st.caption(
        f"Version {APP_VERSION} · team modules integrated by Chaitanya · "
        "client-supplied query text is displayed only"
    )

    diagnostics = expanded_dataset_diagnostics(
        questions, GOLD_DIR, manifest
    )
    completed_qids = (
        set(reviews.loc[reviews["verdict"].isin(["Pass", "Fail"]), "qid"].astype(str))
        if not reviews.empty
        else set()
    )
    cards = st.columns(4)
    cards[0].metric("Questions", diagnostics["rows"])
    cards[1].metric("Official results found", diagnostics.get("official_results_found", 0))
    cards[2].metric("Assigned", sum(qid in assignments for qid in questions["qid"].astype(str)))
    cards[3].metric("Reviewed", len(completed_qids))

    reviewer = st.sidebar.selectbox("Reviewer", ["Guest reviewer"] + TEAM_MEMBERS)
    if reviewer == "Guest reviewer":
        st.sidebar.warning("Select your name to save a review.")

    review_tab, assignment_tab, progress_tab = st.tabs(
        ["🔍 Question verification", "👥 Assignments", "📊 Progress and export"]
    )
    with review_tab:
        _review_tab(questions, manifest, reviews, assignments, reviewer)
    with assignment_tab:
        _assignment_tab(questions, assignments, reviewer)
    with progress_tab:
        _progress_tab(questions, reviews, assignments)


if __name__ == "__main__":
    main()
