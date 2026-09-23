"""Assignments, navigation, agreement metrics and exports. Owner: Thomas."""

from datetime import datetime
from itertools import combinations
import time

import pandas as pd
import streamlit as st

from .config import REVIEW_MODES
from .review_workflow import apply_demo_values
from .storage import backup_database, database_connection


def build_balanced_assignment_plan(qids, team_members, agreement_percentage=10, agreement_reviewers=2):
    """Create a deterministic plan with primary and agreement work shared evenly."""
    ordered_qids = [str(value) for value in qids]
    members = [str(value) for value in team_members if str(value).strip()]
    if not ordered_qids or not members:
        return {}, {}

    agreement_reviewers = min(max(2, int(agreement_reviewers)), min(3, len(members)))
    agreement_percentage = max(0, min(int(agreement_percentage), 100))
    agreement_count = round(len(ordered_qids) * agreement_percentage / 100)
    if agreement_percentage and not agreement_count:
        agreement_count = 1
    agreement_count = min(agreement_count, len(ordered_qids))
    agreement_positions = {
        min(len(ordered_qids) - 1, int(index * len(ordered_qids) / agreement_count))
        for index in range(agreement_count)
    } if agreement_count else set()

    plan = {
        qid: [members[position % len(members)]]
        for position, qid in enumerate(ordered_qids)
    }
    workload = {member: 0 for member in members}
    for reviewers in plan.values():
        workload[reviewers[0]] += 1

    settings = {}
    sample_number = 0
    for position, qid in enumerate(ordered_qids):
        reviewers = plan[qid]
        if position in agreement_positions:
            while len(reviewers) < agreement_reviewers:
                tie_order = {
                    member: (members.index(member) - sample_number) % len(members)
                    for member in members
                }
                candidate = min(
                    (member for member in members if member not in reviewers),
                    key=lambda member: (workload[member], tie_order[member]),
                )
                reviewers.append(candidate)
                workload[candidate] += 1
            sample_number += 1
            settings[qid] = (REVIEW_MODES[1], agreement_reviewers)
        else:
            settings[qid] = (REVIEW_MODES[0], 1)

    # Rebalance secondary reviews without changing any primary owner.
    while max(workload.values()) - min(workload.values()) > 1:
        busiest = max(members, key=lambda member: workload[member])
        lightest = min(members, key=lambda member: workload[member])
        replacement_qid = next(
            (
                qid for qid, reviewers in plan.items()
                if busiest in reviewers[1:] and lightest not in reviewers
            ),
            None,
        )
        if replacement_qid is None:
            break
        reviewers = plan[replacement_qid]
        reviewers[reviewers.index(busiest)] = lightest
        workload[busiest] -= 1
        workload[lightest] += 1
    return plan, settings

def save_bulk_assignment(plan, settings, replace_existing=False):
    """Apply one complete assignment plan atomically, then create one backup."""
    now = datetime.now().isoformat(timespec="seconds")
    applied_count = 0
    with database_connection() as connection:
        for qid, reviewers in plan.items():
            existing_count = connection.execute(
                "SELECT COUNT(*) FROM assignments WHERE qid=?", (qid,)
            ).fetchone()[0]
            if existing_count and not replace_existing:
                continue
            connection.execute("DELETE FROM assignments WHERE qid=?", (qid,))
            connection.executemany(
                "INSERT INTO assignments (qid, reviewer, assigned_at) VALUES (?, ?, ?)",
                [(qid, reviewer, now) for reviewer in reviewers],
            )
            review_mode, target_reviews = settings[qid]
            connection.execute(
                """
                INSERT INTO question_settings (qid, review_mode, target_reviews, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(qid) DO UPDATE SET
                    review_mode=excluded.review_mode,
                    target_reviews=excluded.target_reviews,
                    updated_at=excluded.updated_at
                """,
                (qid, review_mode, int(target_reviews), now),
            )
            applied_count += 1
    backup_database()
    return applied_count

def assignment_plan_frame(plan, settings):
    rows = []
    for qid, reviewers in plan.items():
        review_mode, target_reviews = settings[qid]
        rows.append(
            {
                "qid": qid,
                "primary_reviewer": reviewers[0],
                "all_reviewers": "; ".join(reviewers),
                "review_mode": review_mode,
                "target_reviews": target_reviews,
            }
        )
    return pd.DataFrame(rows)

def calculate_agreement_metrics(completed):
    """Return exact agreement and an exploratory pooled Cohen's kappa."""
    pairs = []
    if not completed.empty:
        for _, group in completed.sort_values(["qid", "reviewer"]).groupby("qid"):
            verdicts = group.drop_duplicates("reviewer")["verdict"].tolist()
            pairs.extend(combinations(verdicts, 2))
    if not pairs:
        return {"pair_count": 0, "exact_agreement": None, "kappa": None}

    exact = sum(left == right for left, right in pairs) / len(pairs)
    left_pass = sum(left == "Pass" for left, _ in pairs) / len(pairs)
    right_pass = sum(right == "Pass" for _, right in pairs) / len(pairs)
    expected = left_pass * right_pass + (1 - left_pass) * (1 - right_pass)
    kappa = None if expected >= 1 else (exact - expected) / (1 - expected)
    return {"pair_count": len(pairs), "exact_agreement": exact, "kappa": kappa}

def create_export(scope_questions, reviews, assignments, adjudications, settings):
    if reviews.empty:
        return reviews.copy()
    export = reviews.merge(
        scope_questions[[
            "qid", "scenario", "qtype", "qtype_name", "task", "difficulty",
            "question_en", "question_zh", "gold_code", "notes", "rewrite_source",
            "expected_output",
        ]],
        on="qid",
        how="left",
    )
    if not adjudications.empty:
        export = export.merge(
            adjudications[["qid", "adjudicator", "final_verdict", "resolution_notes", "resolved_at"]],
            on="qid",
            how="left",
        )
    if not assignments.empty:
        assigned = (
            assignments.groupby("qid")["reviewer"]
            .apply(lambda values: "; ".join(sorted(set(values))))
            .rename("assigned_reviewers")
            .reset_index()
        )
        export = export.merge(assigned, on="qid", how="left")
    if not settings.empty:
        export = export.merge(
            settings[["qid", "review_mode", "target_reviews"]], on="qid", how="left"
        )
    return export.sort_values(["qid", "reviewer"])

def select_question(target_qid):
    st.session_state["selected_qid"] = target_qid
    st.session_state["review_started_qid"] = target_qid
    st.session_state["review_started_at"] = time.monotonic()

def next_unreviewed_question(current_qid, options, reviewed_qids):
    if not options:
        return current_qid
    current_index = options.index(current_qid) if current_qid in options else -1
    ordered = options[current_index + 1:] + options[:current_index + 1]
    return next((candidate for candidate in ordered if candidate not in reviewed_qids), current_qid)

def load_demo_question(target_qid, reviewer):
    st.session_state["selected_qid"] = target_qid
    if reviewer:
        apply_demo_values(target_qid, reviewer)
    st.session_state["flash_message"] = "Demonstration example loaded."
