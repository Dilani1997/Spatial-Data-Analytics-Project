from pathlib import Path
import sys
import re
import pandas as pd


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database"
BENCHMARK = ROOT / "geoquerybench_v0.1"
QUESTION_FILE = (
    BENCHMARK / "questions" / "geoquerybench_questions_EN.csv"
)


# ============================================================
# HELPERS
# ============================================================

def print_header(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def get_question(qid):
    questions = pd.read_csv(QUESTION_FILE)

    row = questions.loc[questions["qid"] == qid]

    if row.empty:
        raise ValueError(f"Query ID not found: {qid}")

    return row.iloc[0]


def tokenize_question(question):
    """
    Extract useful words from the natural-language question.
    Generic words are removed so schema matching is less noisy.
    """

    stopwords = {
        "how", "many", "of", "the", "were", "was", "is", "are",
        "by", "each", "a", "an", "and", "or", "to", "from",
        "in", "on", "for", "with", "it", "its", "this", "that",
        "break", "down", "name", "names", "show", "give",
        "me", "what", "which", "where", "when"
    }

    words = re.findall(r"[A-Za-z0-9_]+", str(question).lower())

    return sorted({
        w for w in words
        if len(w) >= 3 and w not in stopwords
    })


def expand_keywords(tokens):
    """
    Add a small number of common schema synonyms.

    This is only for discovery. A keyword match does NOT prove
    that the question is answerable.
    """

    synonym_map = {
        "company": {
            "company", "organisation", "organization",
            "operator", "owner", "client", "agency",
            "contractor", "collector"
        },
        "companies": {
            "company", "organisation", "organization",
            "operator", "owner", "client", "agency",
            "contractor", "collector"
        },
        "sample": {
            "sample", "sampling", "specimen"
        },
        "samples": {
            "sample", "sampling", "specimen"
        },
        "surface": {
            "surface"
        },
        "report": {
            "report", "document"
        },
    }

    expanded = set(tokens)

    for token in tokens:
        expanded.update(synonym_map.get(token, set()))

    return sorted(expanded)


def read_parquet_schema(path):
    """
    Read only parquet metadata/schema where possible.
    Falls back to pandas if necessary.
    """

    try:
        import pyarrow.parquet as pq

        schema = pq.read_schema(path)
        return list(schema.names)

    except Exception:
        # Fallback: pandas
        df = pd.read_parquet(path)
        return list(df.columns)


def scan_database():
    """
    Return:
        {
            Path(...): [column1, column2, ...],
            ...
        }
    """

    schemas = {}

    for path in sorted(DATABASE.rglob("*.parquet")):
        try:
            schemas[path] = read_parquet_schema(path)
        except Exception as e:
            print(f"WARNING: Could not read {path}: {e}")

    return schemas


def find_keyword_matches(schemas, keywords):
    matches = []

    for path, columns in schemas.items():
        for col in columns:
            col_lower = col.lower()

            matched = [
                keyword
                for keyword in keywords
                if keyword in col_lower
            ]

            if matched:
                matches.append({
                    "file": path,
                    "column": col,
                    "keywords": matched
                })

    return matches


def find_possible_join_keys(schemas):
    """
    Show columns that look like identifiers / possible join keys.
    This does NOT claim that the joins are valid.
    """

    key_patterns = (
        "uid",
        "id",
        "_id",
        "code",
        "report",
        "project",
        "source",
        "dataset",
        "site",
        "sample"
    )

    results = []

    for path, columns in schemas.items():

        candidates = []

        for col in columns:
            c = col.lower()

            if (
                c == "uid"
                or c == "id"
                or c.endswith("_id")
                or c.endswith("_code")
                or any(pattern in c for pattern in key_patterns)
            ):
                candidates.append(col)

        if candidates:
            results.append((path, candidates))

    return results


def short_path(path):
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


# ============================================================
# MAIN
# ============================================================

def main(qid):

    row = get_question(qid)

    task = str(row.get("task", ""))

    if task.lower() != "refusal":
        print(
            f"WARNING: {qid} has task='{task}', "
            "not 'refusal'."
        )

    question = row.get("question", "")
    gold_code = row.get("gold_code", "")

    # --------------------------------------------------------
    # QUERY INFORMATION
    # --------------------------------------------------------

    print_header(f"VALIDATING REFUSAL: {qid}")

    print(f"Scenario:          {row.get('scenario', '')}")
    print(f"Task:              {task}")
    print(f"Difficulty:        {row.get('difficulty', '')}")
    print(f"Robustness:        {row.get('robustness', '')}")

    print("\nQuestion:")
    print(question)

    print("\nGold refusal / gold code:")
    print(gold_code)


    # --------------------------------------------------------
    # QUESTION KEYWORDS
    # --------------------------------------------------------

    print_header("QUESTION / SCHEMA KEYWORDS")

    tokens = tokenize_question(question)
    keywords = expand_keywords(tokens)

    print("Question tokens:")
    print(", ".join(tokens))

    print("\nExpanded schema-search keywords:")
    print(", ".join(keywords))


    # --------------------------------------------------------
    # DATABASE SCAN
    # --------------------------------------------------------

    print_header("SCANNING FROZEN DATABASE")

    schemas = scan_database()

    print(f"Parquet files scanned: {len(schemas)}")


    # --------------------------------------------------------
    # DIRECT / RELATED FIELD MATCHES
    # --------------------------------------------------------

    print_header("POTENTIALLY RELEVANT FIELDS")

    matches = find_keyword_matches(schemas, keywords)

    if not matches:
        print("No keyword-related schema fields found.")

    else:
        current_file = None

        for match in matches:

            if match["file"] != current_file:
                current_file = match["file"]
                print(f"\n{short_path(current_file)}")

            print(
                f"  {match['column']}"
                f"    [matched: {', '.join(match['keywords'])}]"
            )


    # --------------------------------------------------------
    # POSSIBLE JOIN KEYS
    # --------------------------------------------------------

    print_header("POSSIBLE JOIN / IDENTIFIER FIELDS")

    joins = find_possible_join_keys(schemas)

    for path, columns in joins:
        print(f"\n{short_path(path)}")
        print("  " + ", ".join(columns))


    # --------------------------------------------------------
    # FULL SCHEMA OF HIGH-RELEVANCE FILES
    # --------------------------------------------------------

    print_header("SCHEMAS OF MATCHED FILES")

    matched_files = sorted({
        match["file"]
        for match in matches
    })

    if not matched_files:
        print("No matched files.")

    else:
        for path in matched_files:
            print(f"\n{short_path(path)}")
            print("  " + ", ".join(schemas[path]))


    # --------------------------------------------------------
    # MANUAL REVIEW
    # --------------------------------------------------------

    print_header("MANUAL REFUSAL REVIEW REQUIRED")

    print(
        "[ ] Requested attribute exists directly in the frozen data\n"
        "[ ] Requested attribute may exist under another field name\n"
        "[ ] Requested attribute exists in a related table\n"
        "[ ] A reliable join path exists from the requested entity\n"
        "    to that attribute\n"
        "[ ] Join cardinality / duplicates have been checked\n"
        "[ ] The requested aggregation can be computed reliably\n"
        "[ ] Gold refusal accurately describes the data limitation\n"
        "[ ] Refusal is preferable to inventing or assuming data\n"
        "[ ] Client clarification / adjudication is not required"
    )

    print("\nOverall verdict: MANUAL REVIEW REQUIRED")

    print(
        "\nIMPORTANT:\n"
        "Absence of an obvious column name does NOT by itself prove "
        "that the question is unanswerable.\n"
        "Check related tables and possible join paths before assigning PASS."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage:\n"
            "  python manual_validation/validate_refusal.py <QID>"
        )
        sys.exit(1)

    main(sys.argv[1])