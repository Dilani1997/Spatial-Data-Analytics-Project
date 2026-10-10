"""User-facing analytics and natural-language-to-SQL features for GeoQueryBench.

These features are intentionally deterministic and offline:
- Query accuracy is derived from saved human Pass/Fail reviews.
- Natural-language-to-SQL retrieves the closest validated SQL examples from
  the existing GeoQueryBench benchmark instead of inventing unverified SQL.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re

import pandas as pd
import streamlit as st


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "give",
    "how", "in", "is", "it", "list", "of", "on", "or", "show", "that", "the",
    "their", "to", "what", "which", "with",
}


def _normalise_text(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", _normalise_text(value))
        if len(token) > 1 and token not in _STOPWORDS
    }


def _similarity(left: object, right: object) -> float:
    """Blend token overlap with sequence similarity for lightweight retrieval."""
    left_text = _normalise_text(left)
    right_text = _normalise_text(right)
    if not left_text or not right_text:
        return 0.0

    left_tokens = _tokens(left_text)
    right_tokens = _tokens(right_text)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left_text, right_text).ratio()
    return 0.7 * jaccard + 0.3 * sequence


def _improved_similarity(prompt: str, question: str) -> float:
    synonyms = {'drillholes':'drillhole','holes':'drillhole','hole':'drillhole','grades':'grade','highest':'maximum','top':'maximum','lowest':'minimum','gold':'au','deepest':'depth'}
    a = {synonyms.get(t,t) for t in _tokens(prompt)}
    b = {synonyms.get(t,t) for t in _tokens(question)}
    if not a or not b:
        return 0.0
    score = 0.6*len(a & b)/len(a) + 0.4*len(a & b)/len(a | b)
    ops = {'maximum','minimum','median','average','count','sum'}
    if (a & ops) != (b & ops):
        score *= 0.6
    if ('economic' in a) != ('economic' in b):
        score *= 0.65
    return min(1.0, score)

def rank_sql_matches(questions: pd.DataFrame, prompt: str, limit: int = 5) -> pd.DataFrame:
    """Return the closest validated SQL benchmark questions to a user prompt."""
    required = {"qid", "question_en", "task", "gold_code"}
    if questions is None or questions.empty or not required.issubset(questions.columns):
        return pd.DataFrame(
            columns=["qid", "question_en", "task", "difficulty", "gold_code", "match_score"]
        )

    candidates = questions.copy()
    candidates["task"] = candidates["task"].astype(str)
    candidates["gold_code"] = candidates["gold_code"].fillna("").astype(str)
    candidates = candidates[
        candidates["task"].str.strip().str.lower().eq("sql")
        & candidates["gold_code"].str.strip().ne("")
    ].copy()

    if candidates.empty or not str(prompt).strip():
        return candidates.head(0)

    candidates["match_score"] = candidates["question_en"].map(
        lambda value: _improved_similarity(prompt, value)
    )
    if "difficulty" not in candidates.columns:
        candidates["difficulty"] = ""
    return (
        candidates.sort_values(["match_score", "qid"], ascending=[False, True])
        .head(max(1, int(limit)))
        [["qid", "question_en", "task", "difficulty", "gold_code", "match_score"]]
        .reset_index(drop=True)
    )


def build_query_accuracy(completed_reviews: pd.DataFrame, questions: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Summarise review-derived query accuracy at question level.

    Each reviewed question receives a consensus state from its available Pass/Fail
    reviews. Tied Pass/Fail questions are reported as disagreements and excluded
    from the accuracy denominator.
    """
    empty_summary = {
        "reviewed_questions": 0,
        "decided_questions": 0,
        "pass_questions": 0,
        "fail_questions": 0,
        "disagreement_questions": 0,
        "accuracy": None,
        "coverage": 0.0,
    }
    if completed_reviews is None or completed_reviews.empty:
        return empty_summary, pd.DataFrame()

    work = completed_reviews.copy()
    work = work[work["verdict"].isin(["Pass", "Fail"])].copy()
    if work.empty:
        return empty_summary, pd.DataFrame()

    counts = (
        work.assign(
            pass_vote=(work["verdict"] == "Pass").astype(int),
            fail_vote=(work["verdict"] == "Fail").astype(int),
        )
        .groupby("qid", as_index=False)
        .agg(
            review_count=("verdict", "size"),
            pass_votes=("pass_vote", "sum"),
            fail_votes=("fail_vote", "sum"),
        )
    )

    counts["consensus"] = "Disagreement"
    counts.loc[counts["pass_votes"] > counts["fail_votes"], "consensus"] = "Pass"
    counts.loc[counts["fail_votes"] > counts["pass_votes"], "consensus"] = "Fail"

    question_cols = [
        col for col in ["qid", "task", "difficulty", "qtype", "qtype_name", "question_en"]
        if questions is not None and col in questions.columns
    ]
    if questions is not None and not questions.empty and "qid" in question_cols:
        counts = counts.merge(
            questions[question_cols].drop_duplicates("qid"),
            on="qid",
            how="left",
        )

    decided = counts[counts["consensus"].isin(["Pass", "Fail"])]
    pass_count = int((decided["consensus"] == "Pass").sum())
    fail_count = int((decided["consensus"] == "Fail").sum())
    disagreement_count = int((counts["consensus"] == "Disagreement").sum())
    decided_count = len(decided)
    total_questions = len(questions) if questions is not None else 0

    summary = {
        "reviewed_questions": int(len(counts)),
        "decided_questions": int(decided_count),
        "pass_questions": pass_count,
        "fail_questions": fail_count,
        "disagreement_questions": disagreement_count,
        "accuracy": (pass_count / decided_count) if decided_count else None,
        "coverage": (len(counts) / total_questions) if total_questions else 0.0,
    }
    return summary, counts


def _breakdown_table(consensus: pd.DataFrame, field: str) -> pd.DataFrame:
    if consensus.empty or field not in consensus.columns:
        return pd.DataFrame()
    data = consensus.copy()
    data[field] = data[field].fillna("Unknown").astype(str).replace("", "Unknown")
    rows = []
    for label, group in data.groupby(field, dropna=False):
        decided = group[group["consensus"].isin(["Pass", "Fail"])]
        passed = int((decided["consensus"] == "Pass").sum())
        failed = int((decided["consensus"] == "Fail").sum())
        disagreements = int((group["consensus"] == "Disagreement").sum())
        rows.append(
            {
                field.replace("_", " ").title(): label,
                "Reviewed": len(group),
                "Pass": passed,
                "Fail": failed,
                "Disagreement": disagreements,
                "Accuracy": round(100 * passed / len(decided), 1) if len(decided) else pd.NA,
            }
        )
    return pd.DataFrame(rows).sort_values(["Reviewed"], ascending=False).reset_index(drop=True)


def render_query_accuracy(completed_reviews: pd.DataFrame, questions: pd.DataFrame) -> None:
    st.markdown("## 🎯 Query accuracy")
    st.write(
        "Track how often reviewed benchmark queries are verified as correct. "
        "Accuracy is calculated from saved human Pass/Fail reviews at question level."
    )

    summary, consensus = build_query_accuracy(completed_reviews, questions)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(
        "Verified accuracy",
        f"{summary['accuracy']:.1%}" if summary["accuracy"] is not None else "—",
    )
    m2.metric("Passed queries", summary["pass_questions"])
    m3.metric("Failed queries", summary["fail_questions"])
    m4.metric("Disagreements", summary["disagreement_questions"])
    m5.metric("Review coverage", f"{summary['coverage']:.1%}")

    st.caption(
        "Definition: a query is counted as Pass or Fail using the majority of its "
        "completed reviewer verdicts. Exact ties are shown as disagreements and are "
        "excluded from the accuracy denominator. This is review-derived accuracy, "
        "not an automatically generated ground-truth score."
    )

    if consensus.empty:
        st.info("No completed Pass/Fail reviews are available yet.")
        return

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("### Accuracy by task")
        task_table = _breakdown_table(consensus, "task")
        if task_table.empty:
            st.info("Task metadata is not available.")
        else:
            st.dataframe(task_table, width="stretch", hide_index=True)

    with right:
        st.markdown("### Accuracy by difficulty")
        difficulty_table = _breakdown_table(consensus, "difficulty")
        if difficulty_table.empty:
            st.info("Difficulty metadata is not available.")
        else:
            st.dataframe(difficulty_table, width="stretch", hide_index=True)

    st.markdown("### Question-level accuracy audit")
    audit_cols = [
        col for col in [
            "qid", "task", "difficulty", "review_count", "pass_votes",
            "fail_votes", "consensus", "question_en"
        ] if col in consensus.columns
    ]
    st.dataframe(
        consensus[audit_cols].sort_values(["consensus", "qid"]),
        width="stretch",
        hide_index=True,
    )


def render_nl_to_sql(questions: pd.DataFrame) -> None:
    st.markdown("## 💬 Natural language → SQL")
    st.write(
        "Describe a data question in ordinary English. GeoQueryBench will retrieve "
        "the closest validated SQL example from the benchmark and show its reference SQL."
    )

    prompt = st.text_area(
        "What do you want to ask?",
        placeholder=(
            "Example: Which drilling methods have the deepest median hole depth, "
            "and how many holes use each method?"
        ),
        height=100,
        key="nl_to_sql_prompt",
    )
    top_k = st.slider("Number of validated matches", 1, 5, 3, key="nl_to_sql_top_k")

    st.caption(
        "This feature is validation-first: it retrieves existing benchmark SQL rather "
        "than inventing a new unverified query. If no close benchmark example exists, "
        "the interface will say so instead of fabricating SQL."
    )

    if not st.button("🔎 Find validated SQL", type="primary", key="nl_to_sql_find"):
        return
    if not prompt.strip():
        st.warning("Enter a natural-language request first.")
        return

    matches = rank_sql_matches(questions, prompt, top_k)
    if matches.empty:
        st.error("No validated SQL examples are available in the current dataset.")
        return

    best = matches.iloc[0]
    best_score = float(best["match_score"])
    if best_score < 0.55:
        st.warning(
            "Low relevance: the closest SQL may not answer your question. Examples are "
            "shown below, but they should not be treated as a direct answer."
        )
    else:
        st.success(
            f"Closest benchmark example: {best['qid']} · similarity {best_score:.0%}"
        )

    st.caption("Similarity is text relevance, not SQL correctness or an accuracy percentage.")
    st.markdown("### Closest benchmark SQL example")
    asked = _tokens(prompt)
    found = _tokens(str(best["question_en"]))
    st.write("**Shared words:** " + (", ".join(sorted(asked & found)) or "None"))
    st.write("**Question words absent from example:** " + (", ".join(sorted(asked - found)) or "None"))
    if "economic" in found and "economic" not in asked:
        st.warning("This example adds an economic-grade condition not requested.")
    if re.search(r"\bwhere\b", str(best["gold_code"]), re.I):
        st.info("This SQL applies filters. Verify that they match your intended question.")
    st.write(str(best["question_en"]))
    meta = st.columns(3)
    meta[0].metric("Query ID", str(best["qid"]))
    meta[1].metric("Difficulty", str(best.get("difficulty", "") or "—"))
    meta[2].metric("Similarity", f"{best_score:.0%}")
    st.code(str(best["gold_code"]), language="sql")

    if len(matches) > 1:
        st.markdown("### Alternative validated matches")
        for _, row in matches.iloc[1:].iterrows():
            with st.expander(
                f"{row['qid']} · {float(row['match_score']):.0%} match · "
                f"{str(row.get('difficulty', '') or 'difficulty n/a')}"
            ):
                st.write(str(row["question_en"]))
                st.code(str(row["gold_code"]), language="sql")
