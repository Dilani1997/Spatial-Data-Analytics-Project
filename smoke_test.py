"""Small integration smoke test for the modular GeoQueryBench package."""
from pathlib import Path
import tempfile

import pandas as pd

from geoquerybench.data_loader import load_expanded_questions, load_gold_manifest, expected_result_file
from geoquerybench.navigation_reporting import next_pending_assigned
from geoquerybench.review_workflow import review_errors
from geoquerybench.storage import (
    assign_unassigned_evenly,
    load_expanded_assignments,
    load_expanded_reviews,
    persist_expanded_evidence,
    save_expanded_review,
)
from geoquerybench.visuals import validate_result_blob


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        questions_path = root / "questions.csv"
        pd.DataFrame([
            {"qid": "Q1", "question_en": "Question 1", "question_zh": "问题1", "gold_code": "SELECT 1"},
            {"qid": "Q2", "question_en": "Question 2", "question_zh": "问题2", "gold_code": "SELECT 2"},
        ]).to_csv(questions_path, index=False)
        questions = load_expanded_questions(questions_path)
        assert len(questions) == 2

        (root / "Q1.csv").write_text("value\n1\n", encoding="utf-8")
        pd.DataFrame([{"qid": "Q1", "filename": "Q1.csv"}]).to_csv(root / "_manifest.csv", index=False)
        manifest = load_gold_manifest(root)
        assert expected_result_file("Q1", root, manifest).name == "Q1.csv"

        db = root / "reviews.sqlite3"
        assert assign_unassigned_evenly(["Q1", "Q2"], ["A", "B"], database_file=db) == 2
        assignments = load_expanded_assignments(db)
        assert set(assignments) == {"Q1", "Q2"}

        assert review_errors("Pass", "", True, False, True) == []
        assert review_errors("Fail", "different", True, True) == []
        assert next_pending_assigned(["Q1", "Q2"], assignments, assignments["Q1"], {}, None) is not None

        validate_result_blob("result.csv", b"value\n2\n")
        name, digest, evidence_path = persist_expanded_evidence(
            "result.csv", b"value\n2\n", database_file=db
        )
        assert evidence_path.is_file()
        save_expanded_review("Q1", "A", "Fail", "different", name, digest, database_file=db)
        saved = load_expanded_reviews(db)
        assert len(saved) == 1 and saved.loc[0, "verdict"] == "Fail"

    print("GeoQueryBench modular integration smoke test: PASS")


if __name__ == "__main__":
    main()
