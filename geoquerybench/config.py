"""Shared application configuration. Owner: Chaitanya."""

from pathlib import Path
import os

APP_VERSION = "1.3.0-modular"
APP_DIRECTORY = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = APP_DIRECTORY / "data"
DATA_FILE_CANDIDATES = [
    DATA_DIRECTORY / "geoquerybench_questions.csv",
    DATA_DIRECTORY / "geoquerybench_seed_pairs_v0.1.csv",
]
configured_storage = Path(os.getenv("GQB_STORAGE_DIR", "runtime")).expanduser()
STORAGE_DIRECTORY = (
    configured_storage if configured_storage.is_absolute()
    else APP_DIRECTORY / configured_storage
).resolve()
DATABASE_FILE = STORAGE_DIRECTORY / "annotations.db"
BACKUP_DIRECTORY = STORAGE_DIRECTORY / "backups"
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
PERSISTENT_STORAGE = os.getenv("GQB_PERSISTENT_STORAGE", "false").strip().lower() in {
    "1", "true", "yes", "on",
}
TEAM_MEMBERS = [
    "Chaitanya Neerukattu",
    "Dilani Gunathilaka Mapitigamage",
    "Sarwesh Kattel",
    "Thomas Ouyang",
    "Ziyue Xu",
]

ASSESSMENT_OPTIONS = ["Not assessed", "Pass", "Fail"]
VERDICT_OPTIONS = ["Not assessed", "Pass", "Fail"]
REVIEW_MODES = ["Standard single review", "Agreement sample (2â€“3 reviewers)"]

QUALITY_GUIDE = [
    {
        "Check": "Executability",
        "Pass when": "The client-supplied query runs successfully in the intended verification environment.",
        "Fail when": "The supplied query contains invalid syntax, missing inputs, unsupported functions or cannot run as written.",
        "Evidence to record": "Parser/runtime result, error message, or a concise manual verification note.",
    },
    {
        "Check": "Schema and table usage",
        "Pass when": "All required tables, fields, keys and joins match the supplied data model.",
        "Fail when": "A required join/table is missing or a field is invented, misplaced or incorrectly linked.",
        "Evidence to record": "Tables/columns checked and the key relationship used.",
    },
    {
        "Check": "Query or code logic",
        "Pass when": "The supplied query's filters, ordering, aggregation, limits and transformations answer the stated question.",
        "Fail when": "The method changes a condition, threshold, grouping, requested entity or intended meaning.",
        "Evidence to record": "The decisive clause or comparison with the verified answer.",
    },
    {
        "Check": "Spatial and domain correctness",
        "Pass when": "Spatial operations, units, coordinate assumptions and geoscience meaning are appropriate.",
        "Fail when": "The supplied query/output uses the wrong spatial relation, unit, geological concept or domain interpretation.",
        "Evidence to record": "Relevant unit, geometry, domain rule or spatial operation.",
    },
    {
        "Check": "Requested output compliance",
        "Pass when": "The query output contains the requested fields, format, table, chart, map or summary.",
        "Fail when": "Required columns, labels, visual output or result detail are absent or materially different.",
        "Evidence to record": "A result summary or attached CSV/TXT/PNG/JPG proof.",
    },
    {
        "Check": "Overall verdict",
        "Pass when": "The supplied query and its verified output are materially correct across the required checks.",
        "Fail when": "Any material error makes the query/output unreliable; explain the primary reason.",
        "Evidence to record": "A short decision justification linked to the most important evidence.",
    },
]

# The client may use slightly different headers in the expanded bilingual file.
# The app maps common alternatives to one stable internal schema.
COLUMN_ALIASES = {
    "qid": ["qid", "question_id", "id"],
    "scenario": ["scenario", "subset", "category"],
    "qtype": ["qtype", "question_type", "type"],
    "qtype_name": ["qtype_name", "question_type_name", "type_name"],
    "task": ["task", "language", "answer_type"],
    "difficulty": ["difficulty", "difficulty_level"],
    "question_en": ["question_en", "english_question", "question_english", "question"],
    "question_zh": ["question_zh", "question_cn", "chinese_question", "question_chinese"],
    "gold_code": ["gold_code", "gold_query", "reference_code", "reference_query", "answer"],
    "notes": ["notes", "annotation_notes", "gold_notes"],
    "rewrite_source": [
        "rewrite_source", "rewritten_query", "query_rewrite", "modified_query",
        "rewritten_question_en",
    ],
    "expected_output": [
        "expected_output", "gold_output", "reference_output", "expected_result",
        "output_metadata",
    ],
}
