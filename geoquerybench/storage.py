"""SQLite persistence, history, assignments and backups. Owner: Ziyue."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import re
import sqlite3
import uuid

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

@contextmanager
def database_connection():
    """Open a configured SQLite connection and always close it after use."""
    STORAGE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

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
    source = sqlite3.connect(DATABASE_FILE)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
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


# --- Expanded workspace storage and evidence (2026-09 update) ---
EXPANDED_ALLOWED_EXTENSIONS = frozenset({".csv", ".txt", ".json", ".geojson", ".png", ".jpg", ".jpeg"})
EXPANDED_MAX_BYTES = 10 * 1024 * 1024


def expanded_database_path(database_file=None):
    if database_file is not None:
        return Path(database_file).expanduser().resolve()
    configured = os.getenv("GQB_EXPANDED_DB", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = STORAGE_DIRECTORY / candidate
        return candidate.resolve()
    return (STORAGE_DIRECTORY / "expanded_reviews.sqlite3").resolve()


@contextmanager
def expanded_database_connection(database_file=None):
    """Open the expanded review database and always close it after use."""
    path = expanded_database_path(database_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA journal_mode=WAL")

    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS expanded_reviews ("
            "qid TEXT NOT NULL, reviewer TEXT NOT NULL, verdict TEXT NOT NULL, "
            "notes TEXT NOT NULL, uploaded_name TEXT, uploaded_sha256 TEXT, "
            "updated_at TEXT NOT NULL, PRIMARY KEY(qid, reviewer))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS expanded_assignments ("
            "qid TEXT PRIMARY KEY, reviewer TEXT NOT NULL)"
        )
        connection.commit()

        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def load_expanded_reviews(database_file=None):
    with expanded_database_connection(database_file) as connection:
        return pd.read_sql_query(
            "SELECT qid,reviewer,verdict,notes,uploaded_name,uploaded_sha256,updated_at "
            "FROM expanded_reviews ORDER BY qid, reviewer",
            connection,
        )


def load_expanded_assignments(database_file=None):
    with expanded_database_connection(database_file) as connection:
        return dict(connection.execute("SELECT qid, reviewer FROM expanded_assignments").fetchall())


def save_expanded_review(
    qid,
    reviewer,
    verdict,
    notes,
    uploaded_name=None,
    uploaded_sha256=None,
    database_file=None,
):
    now = datetime.now(timezone.utc).isoformat()
    with expanded_database_connection(database_file) as connection:
        connection.execute(
            "INSERT INTO expanded_reviews "
            "(qid,reviewer,verdict,notes,uploaded_name,uploaded_sha256,updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(qid,reviewer) DO UPDATE SET "
            "verdict=excluded.verdict,notes=excluded.notes,"
            "uploaded_name=excluded.uploaded_name,uploaded_sha256=excluded.uploaded_sha256,"
            "updated_at=excluded.updated_at",
            (
                str(qid),
                str(reviewer),
                str(verdict),
                str(notes).strip(),
                uploaded_name,
                uploaded_sha256,
                now,
            ),
        )
        connection.commit()
    return now


def save_expanded_assignment(qid, reviewer, database_file=None):
    with expanded_database_connection(database_file) as connection:
        connection.execute(
            "INSERT INTO expanded_assignments(qid,reviewer) VALUES (?,?) "
            "ON CONFLICT(qid) DO UPDATE SET reviewer=excluded.reviewer",
            (str(qid), str(reviewer)),
        )
        connection.commit()


def assign_unassigned_evenly(question_ids, reviewers, database_file=None):
    reviewers = [str(name) for name in reviewers if str(name).strip()]
    if not reviewers:
        return 0
    with expanded_database_connection(database_file) as connection:
        existing = dict(connection.execute("SELECT qid, reviewer FROM expanded_assignments").fetchall())
        counts = {name: sum(owner == name for owner in existing.values()) for name in reviewers}
        added = 0
        for qid in [str(value) for value in question_ids if str(value) not in existing]:
            member = min(reviewers, key=lambda name: (counts[name], reviewers.index(name)))
            connection.execute(
                "INSERT OR IGNORE INTO expanded_assignments(qid,reviewer) VALUES (?,?)",
                (qid, member),
            )
            counts[member] += 1
            added += 1
        connection.commit()
    return added


def expanded_evidence_directory(database_file=None, evidence_dir=None):
    if evidence_dir is not None:
        return Path(evidence_dir).expanduser().resolve()
    return expanded_database_path(database_file).parent / "evidence"


def expanded_evidence_path(digest, original_name, database_file=None, evidence_dir=None):
    suffix = Path(str(original_name or "")).suffix.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", str(digest or "")):
        return None
    if suffix not in EXPANDED_ALLOWED_EXTENSIONS:
        return None
    return expanded_evidence_directory(database_file, evidence_dir) / (str(digest) + suffix)


def persist_expanded_evidence(
    original_name,
    raw,
    database_file=None,
    evidence_dir=None,
    maximum_bytes=EXPANDED_MAX_BYTES,
):
    raw = bytes(raw)
    if not raw or len(raw) > int(maximum_bytes):
        raise ValueError("Uploaded evidence must be nonempty and no larger than 10 MB.")
    digest = hashlib.sha256(raw).hexdigest()
    path = expanded_evidence_path(digest, original_name, database_file, evidence_dir)
    if path is None:
        raise ValueError("Unsupported evidence file type.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.parent / ("." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return str(original_name), digest, path
