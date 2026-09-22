"""SQLite persistence, history, assignments and backups. Owner: Ziyue."""

from datetime import datetime
import sqlite3

import pandas as pd

from .config import BACKUP_DIRECTORY, DATABASE_FILE, PERSISTENT_STORAGE, STORAGE_DIRECTORY
from .data_loader import clean


def storage_diagnostics():
    try:
        STORAGE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        probe = STORAGE_DIRECTORY / ".gqb_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    return {
        "directory": str(STORAGE_DIRECTORY),
        "writable": writable,
        "persistent": PERSISTENT_STORAGE,
        "database_exists": DATABASE_FILE.exists(),
        "database_bytes": DATABASE_FILE.stat().st_size if DATABASE_FILE.exists() else 0,
    }

def database_connection():
    STORAGE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection

def table_exists(connection, table_name):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None

def ensure_columns(connection, table_name, definitions):
    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for name, definition in definitions.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")

def initialize_database():
    with database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                qid TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                candidate_output TEXT,
                result_evidence TEXT,
                rewrite_applicable INTEGER DEFAULT 0,
                rewritten_query TEXT,
                rewrite_equivalence TEXT,
                rewrite_comments TEXT,
                translation_quality TEXT,
                evidence_filename TEXT,
                evidence_mime TEXT,
                evidence_blob BLOB,
                executability TEXT,
                schema_use TEXT,
                logic TEXT,
                domain_correctness TEXT,
                output_compliance TEXT,
                verdict TEXT,
                comments TEXT,
                needs_clarification INTEGER DEFAULT 0,
                review_seconds REAL DEFAULT 0,
                review_version INTEGER DEFAULT 1,
                updated_at TEXT,
                PRIMARY KEY (qid, reviewer)
            );

            CREATE TABLE IF NOT EXISTS review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qid TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                candidate_output TEXT,
                result_evidence TEXT,
                rewrite_applicable INTEGER DEFAULT 0,
                rewritten_query TEXT,
                rewrite_equivalence TEXT,
                rewrite_comments TEXT,
                translation_quality TEXT,
                evidence_filename TEXT,
                executability TEXT,
                schema_use TEXT,
                logic TEXT,
                domain_correctness TEXT,
                output_compliance TEXT,
                verdict TEXT,
                comments TEXT,
                needs_clarification INTEGER DEFAULT 0,
                review_seconds REAL DEFAULT 0,
                version INTEGER NOT NULL,
                saved_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assignments (
                qid TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                PRIMARY KEY (qid, reviewer)
            );

            CREATE TABLE IF NOT EXISTS adjudications (
                qid TEXT PRIMARY KEY,
                adjudicator TEXT NOT NULL,
                final_verdict TEXT NOT NULL,
                resolution_notes TEXT NOT NULL,
                resolved_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_settings (
                qid TEXT PRIMARY KEY,
                review_mode TEXT NOT NULL DEFAULT 'Standard single review',
                target_reviews INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """
        )

        new_review_columns = {
            "rewrite_applicable": "INTEGER DEFAULT 0",
            "rewritten_query": "TEXT",
            "rewrite_equivalence": "TEXT",
            "rewrite_comments": "TEXT",
            "translation_quality": "TEXT",
            "review_seconds": "REAL DEFAULT 0",
        }
        ensure_columns(connection, "reviews", new_review_columns)
        ensure_columns(connection, "review_history", new_review_columns)

        # Preserve records made with the earlier single-review prototype.
        if table_exists(connection, "annotations"):
            review_count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            if review_count == 0:
                legacy_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(annotations)").fetchall()
                }
                required = {
                    "qid", "reviewer", "candidate_output", "result_evidence",
                    "executability", "schema_use", "logic", "domain_correctness",
                    "output_compliance", "verdict", "comments", "updated_at",
                }
                if required.issubset(legacy_columns):
                    legacy_rows = connection.execute(
                        """
                        SELECT qid, reviewer, candidate_output, result_evidence,
                               executability, schema_use, logic, domain_correctness,
                               output_compliance, verdict, comments, updated_at
                        FROM annotations
                        """
                    ).fetchall()
                    for row in legacy_rows:
                        reviewer = clean(row["reviewer"], "Legacy reviewer")
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO reviews (
                                qid, reviewer, candidate_output, result_evidence,
                                executability, schema_use, logic, domain_correctness,
                                output_compliance, verdict, comments,
                                review_version, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                            """,
                            (
                                row["qid"], reviewer, row["candidate_output"],
                                row["result_evidence"], row["executability"],
                                row["schema_use"], row["logic"],
                                row["domain_correctness"], row["output_compliance"],
                                row["verdict"], row["comments"], row["updated_at"],
                            ),
                        )

def backup_database():
    if not DATABASE_FILE.exists():
        return None
    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = BACKUP_DIRECTORY / f"annotations_{stamp}.db"
    with sqlite3.connect(DATABASE_FILE) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination

def load_reviews():
    with database_connection() as connection:
        return pd.read_sql_query(
            """
            SELECT qid, reviewer, candidate_output, result_evidence,
                   rewrite_applicable, rewritten_query, rewrite_equivalence,
                   rewrite_comments, translation_quality,
                   evidence_filename, evidence_mime, executability, schema_use,
                   logic, domain_correctness, output_compliance, verdict,
                   comments, needs_clarification, review_seconds,
                   review_version, updated_at
            FROM reviews ORDER BY updated_at DESC
            """,
            connection,
        )

def load_history():
    with database_connection() as connection:
        return pd.read_sql_query(
            "SELECT * FROM review_history ORDER BY saved_at DESC, id DESC",
            connection,
        )

def load_assignments():
    with database_connection() as connection:
        return pd.read_sql_query(
            "SELECT qid, reviewer, assigned_at FROM assignments ORDER BY qid, reviewer",
            connection,
        )

def load_adjudications():
    with database_connection() as connection:
        return pd.read_sql_query(
            "SELECT * FROM adjudications ORDER BY resolved_at DESC",
            connection,
        )

def load_question_settings():
    with database_connection() as connection:
        return pd.read_sql_query(
            "SELECT qid, review_mode, target_reviews, updated_at FROM question_settings",
            connection,
        )

def get_review(qid, reviewer):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM reviews WHERE qid=? AND reviewer=?",
            (qid, reviewer),
        ).fetchone()
    return dict(row) if row else {}

def save_review(qid, reviewer, values, evidence):
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_review(qid, reviewer)
    filename = evidence.get("filename") if evidence else existing.get("evidence_filename")
    mime = evidence.get("mime") if evidence else existing.get("evidence_mime")
    blob = evidence.get("blob") if evidence else existing.get("evidence_blob")

    with database_connection() as connection:
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM review_history WHERE qid=? AND reviewer=?",
            (qid, reviewer),
        ).fetchone()[0]

        connection.execute(
            """
            INSERT INTO reviews (
                qid, reviewer, candidate_output, result_evidence,
                rewrite_applicable, rewritten_query, rewrite_equivalence,
                rewrite_comments, translation_quality,
                evidence_filename, evidence_mime, evidence_blob,
                executability, schema_use, logic, domain_correctness,
                output_compliance, verdict, comments, needs_clarification,
                review_seconds, review_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(qid, reviewer) DO UPDATE SET
                candidate_output=excluded.candidate_output,
                result_evidence=excluded.result_evidence,
                rewrite_applicable=excluded.rewrite_applicable,
                rewritten_query=excluded.rewritten_query,
                rewrite_equivalence=excluded.rewrite_equivalence,
                rewrite_comments=excluded.rewrite_comments,
                translation_quality=excluded.translation_quality,
                evidence_filename=excluded.evidence_filename,
                evidence_mime=excluded.evidence_mime,
                evidence_blob=excluded.evidence_blob,
                executability=excluded.executability,
                schema_use=excluded.schema_use,
                logic=excluded.logic,
                domain_correctness=excluded.domain_correctness,
                output_compliance=excluded.output_compliance,
                verdict=excluded.verdict,
                comments=excluded.comments,
                needs_clarification=excluded.needs_clarification,
                review_seconds=excluded.review_seconds,
                review_version=excluded.review_version,
                updated_at=excluded.updated_at
            """,
            (
                qid, reviewer, values["candidate_output"], values["result_evidence"],
                int(values["rewrite_applicable"]), values["rewritten_query"],
                values["rewrite_equivalence"], values["rewrite_comments"],
                values["translation_quality"],
                filename, mime, blob, values["executability"], values["schema_use"],
                values["logic"], values["domain_correctness"],
                values["output_compliance"], values["verdict"], values["comments"],
                int(values["needs_clarification"]), float(values.get("review_seconds", 0)),
                version, now,
            ),
        )
        connection.execute(
            """
            INSERT INTO review_history (
                qid, reviewer, candidate_output, result_evidence,
                rewrite_applicable, rewritten_query, rewrite_equivalence,
                rewrite_comments, translation_quality,
                evidence_filename, executability, schema_use, logic,
                domain_correctness, output_compliance, verdict, comments,
                needs_clarification, review_seconds, version, saved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qid, reviewer, values["candidate_output"], values["result_evidence"],
                int(values["rewrite_applicable"]), values["rewritten_query"],
                values["rewrite_equivalence"], values["rewrite_comments"],
                values["translation_quality"],
                filename, values["executability"], values["schema_use"],
                values["logic"], values["domain_correctness"],
                values["output_compliance"], values["verdict"], values["comments"],
                int(values["needs_clarification"]), float(values.get("review_seconds", 0)),
                version, now,
            ),
        )
    backup_database()

def save_assignments(qid, reviewers):
    now = datetime.now().isoformat(timespec="seconds")
    with database_connection() as connection:
        connection.execute("DELETE FROM assignments WHERE qid=?", (qid,))
        connection.executemany(
            "INSERT INTO assignments (qid, reviewer, assigned_at) VALUES (?, ?, ?)",
            [(qid, reviewer, now) for reviewer in reviewers],
        )
    backup_database()

def save_question_setting(qid, review_mode, target_reviews):
    now = datetime.now().isoformat(timespec="seconds")
    target_reviews = max(1, min(int(target_reviews), 3))
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO question_settings (qid, review_mode, target_reviews, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(qid) DO UPDATE SET
                review_mode=excluded.review_mode,
                target_reviews=excluded.target_reviews,
                updated_at=excluded.updated_at
            """,
            (qid, review_mode, target_reviews, now),
        )
    backup_database()

def save_adjudication(qid, adjudicator, verdict, notes):
    now = datetime.now().isoformat(timespec="seconds")
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO adjudications (qid, adjudicator, final_verdict, resolution_notes, resolved_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(qid) DO UPDATE SET
                adjudicator=excluded.adjudicator,
                final_verdict=excluded.final_verdict,
                resolution_notes=excluded.resolution_notes,
                resolved_at=excluded.resolved_at
            """,
            (qid, adjudicator, verdict, notes, now),
        )
    backup_database()
