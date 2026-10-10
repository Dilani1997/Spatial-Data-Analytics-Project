import pandas as pd

from geoquerybench.user_features import build_query_accuracy, rank_sql_matches


def test_query_accuracy_uses_question_level_consensus():
    questions = pd.DataFrame(
        [
            {"qid": "Q1", "task": "sql", "difficulty": "easy"},
            {"qid": "Q2", "task": "sql", "difficulty": "hard"},
            {"qid": "Q3", "task": "python", "difficulty": "medium"},
        ]
    )
    reviews = pd.DataFrame(
        [
            {"qid": "Q1", "reviewer": "A", "verdict": "Pass"},
            {"qid": "Q1", "reviewer": "B", "verdict": "Pass"},
            {"qid": "Q2", "reviewer": "A", "verdict": "Pass"},
            {"qid": "Q2", "reviewer": "B", "verdict": "Fail"},
            {"qid": "Q3", "reviewer": "A", "verdict": "Fail"},
        ]
    )

    summary, consensus = build_query_accuracy(reviews, questions)

    assert summary["reviewed_questions"] == 3
    assert summary["decided_questions"] == 2
    assert summary["pass_questions"] == 1
    assert summary["fail_questions"] == 1
    assert summary["disagreement_questions"] == 1
    assert summary["accuracy"] == 0.5
    assert summary["coverage"] == 1.0
    assert set(consensus["consensus"]) == {"Pass", "Fail", "Disagreement"}


def test_natural_language_to_sql_retrieval_prefers_closest_question():
    questions = pd.DataFrame(
        [
            {
                "qid": "SQL-1",
                "question_en": "How many drill holes are deeper than 100 metres?",
                "task": "sql",
                "difficulty": "easy",
                "gold_code": "SELECT count(*) FROM collar WHERE max_depth_m > 100;",
            },
            {
                "qid": "SQL-2",
                "question_en": "List the top ten samples by gold grade.",
                "task": "sql",
                "difficulty": "medium",
                "gold_code": "SELECT * FROM assay ORDER BY au_ppm DESC LIMIT 10;",
            },
            {
                "qid": "PY-1",
                "question_en": "How many drill holes are deeper than 100 metres?",
                "task": "python",
                "difficulty": "easy",
                "gold_code": "print('not SQL')",
            },
        ]
    )

    result = rank_sql_matches(
        questions,
        "count drill holes deeper than 100 metres",
        limit=2,
    )

    assert len(result) == 2
    assert result.iloc[0]["qid"] == "SQL-1"
    assert "SELECT count(*)" in result.iloc[0]["gold_code"]
    assert "PY-1" not in set(result["qid"])
