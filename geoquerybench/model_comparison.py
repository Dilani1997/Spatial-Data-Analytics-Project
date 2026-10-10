"""Reproducible comparison of two SQL example-retrieval algorithms.

Evaluation uses deterministic wording changes derived from existing benchmark
questions. It tests retrieval of the originating question ID, not SQL execution
accuracy or performance on independent user questions.
"""
import re
import pandas as pd
import streamlit as st
from geoquerybench.user_features import _similarity, _improved_similarity


def paraphrase(question: str) -> str:
    swaps = [
        (r"\bwhich\b", "show"), (r"\bshow\b", "list"),
        (r"\bdrillholes\b", "holes"), (r"\bdrill holes\b", "drillholes"),
        (r"\bhighest\b", "top"), (r"\bmaximum\b", "highest"),
        (r"\bhow many\b", "count"), (r"\bgold\b", "Au"),
    ]
    text = str(question)
    for pattern, replacement in swaps:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def evaluate_retrievers(questions: pd.DataFrame, n: int = 40):
    required = {"qid", "question_en", "task", "gold_code"}
    if questions is None or not required.issubset(questions.columns):
        return pd.DataFrame()
    frame = questions.copy()
    frame = frame[frame["task"].fillna("").astype(str).str.lower().eq("sql")
                  & frame["gold_code"].fillna("").astype(str).str.strip().ne("")
                  & frame["question_en"].fillna("").astype(str).str.strip().ne("")]
    frame = frame.drop_duplicates("qid").sort_values("qid").reset_index(drop=True)
    if len(frame) < 2:
        return pd.DataFrame()
    cases = frame.head(min(n, len(frame)))
    candidates = list(zip(frame.qid.astype(str), frame.question_en.astype(str)))
    results = []
    for _, row in cases.iterrows():
        question = paraphrase(str(row.question_en))
        if question.strip().lower() == str(row.question_en).strip().lower():
            continue
        for name, scorer in [("Original lexical baseline", _similarity),
                             ("Improved intent-aware retrieval", _improved_similarity)]:
            ranking = sorted(((scorer(question, q), qid) for qid, q in candidates),
                             key=lambda item: (-item[0], item[1]))
            rank = next((i + 1 for i, (_, qid) in enumerate(ranking)
                         if qid == str(row.qid)), None)
            results.append({"Method": name, "Original query ID": str(row.qid),
                            "Test wording": question, "Target rank": rank,
                            "Top-1 correct": int(rank == 1),
                            "Top-3 correct": int(rank is not None and rank <= 3),
                            "Reciprocal rank": 1.0 / rank if rank else 0.0,
                            "Top retrieved ID": ranking[0][1]})
    return pd.DataFrame(results)


def render_model_comparison(questions: pd.DataFrame):
    st.markdown("## ⚖️ SQL retrieval method comparison")
    st.write("Compare the original lexical matcher against the improved intent-aware "
             "matcher on the same SQL benchmark questions.")
    st.caption("Evaluation uses deterministic synthetic paraphrases. Targets are original "
               "question IDs; this is NOT SQL execution accuracy, nor a held-out human evaluation.")
    size = st.select_slider("Test questions", options=[10, 20, 40, 60],
                            value=20, key="model_comparison_size")
    if not st.button("Run reproducible comparison", key="run_model_comparison"):
        return
    with st.spinner("Evaluating both retrieval approaches..."):
        records = evaluate_retrievers(questions, size)
    if records.empty:
        st.warning("Not enough SQL examples or paraphrasable questions for comparison.")
        return
    metrics = records.groupby("Method", as_index=False).agg(
        Cases=("Top-1 correct", "size"),
        **{"Top-1 accuracy": ("Top-1 correct", "mean"),
           "Recall@3": ("Top-3 correct", "mean"),
           "MRR": ("Reciprocal rank", "mean")})
    st.dataframe(metrics, hide_index=True, use_container_width=True,
                 column_config={"Top-1 accuracy": st.column_config.NumberColumn(format="%.1%%"),
                                "Recall@3": st.column_config.NumberColumn(format="%.1%%"),
                                "MRR": st.column_config.NumberColumn(format="%.3f")})
    st.bar_chart(metrics.set_index("Method")[["Top-1 accuracy", "Recall@3"]])
    st.write("### Case-level audit")
    st.dataframe(records, hide_index=True, use_container_width=True)
    st.download_button("Download comparison CSV", records.to_csv(index=False).encode("utf-8"),
                       "geoquerybench_retrieval_comparison.csv", "text/csv")
    st.info("Top-1 = original benchmark query ranked first. Recall@3 = target appears "
            "among first three. MRR = mean reciprocal rank. These metrics estimate "
            "retrieval behavior only and must not be described as generated-SQL correctness.")
