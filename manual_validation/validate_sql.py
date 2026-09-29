import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


# ============================================================
# Paths
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

BENCHMARK = ROOT / "geoquerybench_v0.1"

QUESTION_FILE = (
    BENCHMARK
    / "questions"
    / "geoquerybench_questions_EN.csv"
)

DATABASE = ROOT / "database"

GOLD_RESULTS = BENCHMARK / "gold_results"

MANIFEST_FILE = GOLD_RESULTS / "_manifest.csv"

OUTPUT_DIR = ROOT / "validation_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Configuration
# ============================================================

# Diagnostic sentinel candidates.
# Finding these values does NOT automatically mean that
# the result is incorrect.
SENTINEL_CANDIDATES = {
    -99,
    -999,
    -9999,
    -99999,
    -999999,
    999,
    9999,
    99999,
    999999,
}


# ============================================================
# Utility functions
# ============================================================

def heading(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def format_metadata_value(value, default="None"):
    if pd.isna(value):
        return default

    value = str(value).strip()

    if not value:
        return default

    return value


# ============================================================
# Load question
# ============================================================

def load_question(qid):
    if not QUESTION_FILE.exists():
        raise FileNotFoundError(
            f"Question file was not found:\n{QUESTION_FILE}"
        )

    df = pd.read_csv(QUESTION_FILE)

    row = df[df["qid"].astype(str) == str(qid)]

    if row.empty:
        raise ValueError(
            f"Question {qid} was not found in:\n{QUESTION_FILE}"
        )

    return row.iloc[0]


# ============================================================
# Load manifest information
# ============================================================

def load_manifest_row(qid):
    if not MANIFEST_FILE.exists():
        return None

    manifest = pd.read_csv(MANIFEST_FILE)

    if "qid" not in manifest.columns:
        return None

    row = manifest[
        manifest["qid"].astype(str) == str(qid)
    ]

    if row.empty:
        return None

    return row.iloc[0]


def get_expected_rows(question, manifest_row):
    """
    Read the expected number of rows.

    Prefer the question metadata, then fall back
    to the manifest.
    """

    possible_columns = [
        "n_rows",
        "rows",
        "row_count",
        "result_rows",
    ]

    for source in [question, manifest_row]:

        if source is None:
            continue

        for column in possible_columns:

            if column in source.index:

                value = source[column]

                if pd.notna(value):

                    try:
                        return int(float(value))

                    except (TypeError, ValueError):
                        pass

    return None


# ============================================================
# Create DuckDB connection
# ============================================================

def create_connection():
    """
    Load all Parquet files from both frozen databases.

    A_subsurface = subsurface dataset
    B_surface    = surface dataset

    Loading both allows this validator to support
    NS, SS and CD SQL questions.
    """

    con = duckdb.connect()

    # Load DuckDB spatial extension for spatial SQL queries
    try:
        con.execute("LOAD spatial;")
    except Exception:
        print(
            "DuckDB spatial extension is not installed. "
            "Installing it now..."
        )
        con.execute("INSTALL spatial;")
        con.execute("LOAD spatial;")

    data_dirs = [
        DATABASE / "A_subsurface",
        DATABASE / "B_surface",
    ]

    parquet_count = 0

    for data_dir in data_dirs:

        if not data_dir.exists():
            raise FileNotFoundError(
                f"Database directory not found:\n{data_dir}"
            )

        for parquet_file in sorted(
            data_dir.glob("*.parquet")
        ):

            table_name = parquet_file.stem

            con.execute(
                f"""
                CREATE OR REPLACE VIEW "{table_name}" AS
                SELECT *
                FROM read_parquet(
                    '{parquet_file.as_posix()}'
                )
                """
            )

            parquet_count += 1

    if parquet_count == 0:
        raise FileNotFoundError(
            "No Parquet files were found under "
            "database/A_subsurface or database/B_surface."
        )

    return con


# ============================================================
# Execute supplied gold SQL
# ============================================================

def execute_gold(con, gold_code):
    return con.execute(str(gold_code)).df()


# ============================================================
# Find supplied gold CSV
# ============================================================

def find_gold_csv(qid):
    candidates = [
        GOLD_RESULTS / f"{qid}.csv",
        GOLD_RESULTS / f"{qid}_result.csv",
        GOLD_RESULTS / f"{qid}_gold.csv",
    ]

    for path in candidates:

        if path.exists():
            return path

    matches = list(
        GOLD_RESULTS.glob(f"*{qid}*.csv")
    )

    if len(matches) == 1:
        return matches[0]

    return None


# ============================================================
# Normalise comparable DataFrames
# ============================================================

def normalise_types(generated, provided):
    """
    CSV and Parquet/DuckDB can infer equivalent columns
    using different dtypes.

    If both versions of a column can safely be converted
    to numeric values, compare them numerically.
    """

    generated = generated.copy()
    provided = provided.copy()

    for column in generated.columns:

        gen_col = generated[column]
        gold_col = provided[column]

        gen_numeric = pd.to_numeric(
            gen_col,
            errors="coerce"
        )

        gold_numeric = pd.to_numeric(
            gold_col,
            errors="coerce"
        )

        gen_non_null = gen_col.notna()
        gold_non_null = gold_col.notna()

        gen_all_numeric = (
            gen_numeric[gen_non_null]
            .notna()
            .all()
        )

        gold_all_numeric = (
            gold_numeric[gold_non_null]
            .notna()
            .all()
        )

        if gen_all_numeric and gold_all_numeric:
            generated[column] = gen_numeric
            provided[column] = gold_numeric

    return generated, provided


# ============================================================
# Compare verification result with supplied gold result
# ============================================================

def compare_results(result, gold_path, ordered=False):

    heading("RESULT COMPARISON")

    comparison = {
        "gold_found": False,
        "supplied_rows": None,
        "verification_rows": len(result),
        "row_count_match": False,
        "column_match": False,
        "value_match": False,
        "ordering_note": "",
    }

    if gold_path is None:

        print(
            "⚠️ No matching supplied gold CSV was found."
        )

        return comparison, None

    comparison["gold_found"] = True

    print(
        f"Supplied result file: {gold_path.name}"
    )

    provided_original = pd.read_csv(gold_path)

    comparison["supplied_rows"] = len(
        provided_original
    )

    generated = result.copy()
    provided = provided_original.copy()

    print()
    print(
        "Verification shape:",
        generated.shape
    )

    print(
        "Supplied shape:    ",
        provided.shape
    )

    # --------------------------------------------------------
    # Row count check
    # --------------------------------------------------------

    comparison["row_count_match"] = (
        len(generated) == len(provided)
    )

    # --------------------------------------------------------
    # Column check
    # --------------------------------------------------------

    comparison["column_match"] = (
        list(generated.columns)
        == list(provided.columns)
    )

    print("\nVerification columns:")
    print(list(generated.columns))

    print("\nSupplied columns:")
    print(list(provided.columns))

    if not comparison["row_count_match"]:
        print("\n❌ Row count mismatch.")

    if not comparison["column_match"]:
        print("\n❌ Column mismatch.")

    if (
        not comparison["row_count_match"]
        or not comparison["column_match"]
    ):
        return comparison, provided_original

    # --------------------------------------------------------
    # Type normalisation
    # --------------------------------------------------------

    generated, provided = normalise_types(
        generated,
        provided
    )

    # --------------------------------------------------------
    # Ordering
    # --------------------------------------------------------

    if not ordered:

        sort_columns = list(
            generated.columns
        )

        try:

            generated = (
                generated
                .sort_values(
                    sort_columns,
                    na_position="last"
                )
                .reset_index(drop=True)
            )

            provided = (
                provided
                .sort_values(
                    sort_columns,
                    na_position="last"
                )
                .reset_index(drop=True)
            )

        except Exception:

            generated = (
                generated
                .reset_index(drop=True)
            )

            provided = (
                provided
                .reset_index(drop=True)
            )

        comparison["ordering_note"] = (
            "Row order ignored because the SQL "
            "does not contain ORDER BY."
        )

    else:

        generated = generated.reset_index(
            drop=True
        )

        provided = provided.reset_index(
            drop=True
        )

    # --------------------------------------------------------
    # Value comparison
    # --------------------------------------------------------

    try:

        pd.testing.assert_frame_equal(
            generated,
            provided,
            check_dtype=False,
            check_exact=False,
            rtol=1e-7,
            atol=1e-9,
        )

        comparison["value_match"] = True

        if ordered:

            print(
                "\n✅ Values and required ordering match."
            )

        else:

            print("\n✅ Values match.")

            print(
                "   Row order was ignored because "
                "no ORDER BY was specified."
            )

    except AssertionError as error:

        # ----------------------------------------------------
        # ORDER BY can still contain tied values.
        # Check whether the underlying rows are identical.
        # ----------------------------------------------------

        if ordered:

            try:

                sort_columns = list(
                    generated.columns
                )

                generated_unordered = (
                    generated
                    .sort_values(
                        sort_columns,
                        na_position="last"
                    )
                    .reset_index(drop=True)
                )

                provided_unordered = (
                    provided
                    .sort_values(
                        sort_columns,
                        na_position="last"
                    )
                    .reset_index(drop=True)
                )

                pd.testing.assert_frame_equal(
                    generated_unordered,
                    provided_unordered,
                    check_dtype=False,
                    check_exact=False,
                    rtol=1e-7,
                    atol=1e-9,
                )

                comparison["value_match"] = True

                comparison["ordering_note"] = (
                    "Same rows and values, but row "
                    "ordering differs. Check whether "
                    "ORDER BY contains tied values."
                )

                print(
                    "\n✅ Same rows and values."
                )

                print(
                    "⚠️ Ordering differs. This may "
                    "be caused by tied ORDER BY values."
                )

            except AssertionError:

                comparison["value_match"] = False

        if not comparison["value_match"]:

            print(
                "\n⚠️ Result values differ from "
                "the supplied gold result."
            )

            print("\nDifference:")

            print(
                str(error)[:2000]
            )

    return comparison, provided_original


# ============================================================
# Data-quality checks
# ============================================================

def analyse_data_quality(df):

    quality = {
        "duplicate_rows": 0,
        "missing_cells": 0,
        "missing_by_column": {},
        "negative_numeric_cells": 0,
        "negative_by_column": {},
        "sentinel_cells": 0,
        "sentinel_by_column": {},
    }

    # --------------------------------------------------------
    # Duplicate rows
    # --------------------------------------------------------

    quality["duplicate_rows"] = int(
        df.duplicated().sum()
    )

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    missing_counts = df.isna().sum()

    quality["missing_cells"] = int(
        missing_counts.sum()
    )

    quality["missing_by_column"] = {
        column: int(count)
        for column, count
        in missing_counts.items()
        if count > 0
    }

    # --------------------------------------------------------
    # Numeric diagnostics
    # --------------------------------------------------------

    numeric_df = df.select_dtypes(
        include=[np.number]
    )

    if not numeric_df.empty:

        negative_counts = (
            numeric_df.lt(0).sum()
        )

        quality[
            "negative_numeric_cells"
        ] = int(
            negative_counts.sum()
        )

        quality[
            "negative_by_column"
        ] = {
            column: int(count)
            for column, count
            in negative_counts.items()
            if count > 0
        }

        # ----------------------------------------------------
        # Sentinel candidates
        # ----------------------------------------------------

        sentinel_by_column = {}

        for column in numeric_df.columns:

            series = numeric_df[column]

            counts = {}

            for sentinel in SENTINEL_CANDIDATES:

                count = int(
                    (series == sentinel).sum()
                )

                if count > 0:
                    counts[sentinel] = count

            if counts:
                sentinel_by_column[column] = (
                    counts
                )

        quality[
            "sentinel_by_column"
        ] = sentinel_by_column

        quality[
            "sentinel_cells"
        ] = sum(
            count
            for column_values
            in sentinel_by_column.values()
            for count
            in column_values.values()
        )

    return quality


# ============================================================
# Print data-quality report
# ============================================================

def print_quality_report(title, quality):

    heading(title)

    print(
        "Duplicate rows:",
        quality["duplicate_rows"]
    )

    print(
        "Missing cells:",
        quality["missing_cells"]
    )

    if quality["missing_by_column"]:

        print(
            "\nMissing values by column:"
        )

        for column, count in (
            quality[
                "missing_by_column"
            ].items()
        ):
            print(
                f"  {column}: {count}"
            )

    else:

        print(
            "Missing values by column: None"
        )

    print(
        "\nNegative numeric cells:",
        quality[
            "negative_numeric_cells"
        ]
    )

    if quality["negative_by_column"]:

        print(
            "\nNegative values by column:"
        )

        for column, count in (
            quality[
                "negative_by_column"
            ].items()
        ):

            print(
                f"  {column}: {count}"
            )

    else:

        print(
            "Negative values by column: None"
        )

    print(
        "\nSentinel candidate cells:",
        quality["sentinel_cells"]
    )

    if quality["sentinel_by_column"]:

        print(
            "\nSentinel candidates by column:"
        )

        for column, values in (
            quality[
                "sentinel_by_column"
            ].items()
        ):

            print(
                f"  {column}: {values}"
            )

    else:

        print(
            "Sentinel candidates: None"
        )

    print(
        "\nNOTE: Negative and sentinel values are "
        "diagnostic only. They do not automatically "
        "mean the query is incorrect."
    )


# ============================================================
# Print All Query Reviews automated fields
# ============================================================

def print_report_summary(
    question,
    expected_rows,
    comparison,
    verification_quality,
):

    heading(
        "ALL QUERY REVIEWS — AUTOMATED FIELDS"
    )

    print(
        f"Query ID:             "
        f"{question.get('qid', '')}"
    )

    print(
        f"Domain:               "
        f"{question.get('scenario', '')}"
    )

    print(
        f"Method:               "
        f"{question.get('task', '')}"
    )

    print(
        f"Difficulty:           "
        f"{question.get('difficulty', '')}"
    )

    print(
        f"Question (EN):        "
        f"{question.get('question', '')}"
    )

    print(
        f"Expected rows:         "
        f"{expected_rows if expected_rows is not None else 'Unknown'}"
    )

    print(
        f"Supplied result:       "
        f"{'Found' if comparison['gold_found'] else 'Not found'}"
    )

    print(
        "Verification result:   Generated"
    )

    print(
        f"Supplied rows:         "
        f"{comparison['supplied_rows']}"
    )

    print(
        f"Verification rows:     "
        f"{comparison['verification_rows']}"
    )

    print(
        f"Row count match:       "
        f"{comparison['row_count_match']}"
    )

    print(
        f"Column match:          "
        f"{comparison['column_match']}"
    )

    print(
        f"Value/content match:   "
        f"{comparison['value_match']}"
    )

    print(
        f"Duplicate rows:        "
        f"{verification_quality['duplicate_rows']}"
    )

    print(
        f"Missing cells:         "
        f"{verification_quality['missing_cells']}"
    )

    print(
        f"Negative numeric cells: "
        f"{verification_quality['negative_numeric_cells']}"
    )

    print(
        "Negative values by column:",
        verification_quality[
            "negative_by_column"
        ]
        if verification_quality[
            "negative_by_column"
        ]
        else "None"
    )

    print(
        f"Sentinel values:       "
        f"{verification_quality['sentinel_cells']}"
    )

    print(
        "\nSupplied query runs:   PASS"
    )

    if comparison["ordering_note"]:

        print(
            "\nOrdering note:"
        )

        print(
            comparison["ordering_note"]
        )


# ============================================================
# Print manual-review checklist
# ============================================================

def print_manual_review():

    heading("MANUAL REVIEW REQUIRED")

    print(
        "[ ] Logic answers the question"
    )

    print(
        "[ ] Output / visualisation matches "
        "the question"
    )

    print(
        "[ ] Tables, fields and joins are correct"
    )

    print(
        "[ ] Units and thresholds are correct"
    )

    print(
        "[ ] Spatial / domain logic is correct"
    )

    print(
        "[ ] Robustness / ambiguity is handled "
        "correctly, if applicable"
    )

    print(
        "[ ] Decide whether client clarification "
        "or adjudication is required"
    )

    print(
        "\nOverall verdict: MANUAL REVIEW REQUIRED"
    )

    print(
        "\nDo NOT assign PASS only because the "
        "verification result matches the supplied "
        "gold result."
    )


# ============================================================
# Main
# ============================================================

def main():

    if len(sys.argv) != 2:

        print("Usage:")

        print(
            "python manual_validation/"
            "validate_sql.py CD1-034"
        )

        sys.exit(1)

    qid = sys.argv[1].strip()

    heading(
        f"VALIDATING {qid}"
    )

    # --------------------------------------------------------
    # Load question
    # --------------------------------------------------------

    try:

        question = load_question(qid)

    except Exception as error:

        print(
            "\n❌ Failed to load question."
        )

        print(error)

        sys.exit(1)

    manifest_row = load_manifest_row(qid)

    expected_rows = get_expected_rows(
        question,
        manifest_row
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    print("\nScenario:")

    print(
        format_metadata_value(
            question.get("scenario", "")
        )
    )

    print("\nQuestion type:")

    print(
        format_metadata_value(
            question.get(
                "qtype_name",
                question.get("qtype", "")
            )
        )
    )

    print("\nTask:")

    print(
        format_metadata_value(
            question.get("task", "")
        )
    )

    print("\nDifficulty:")

    print(
        format_metadata_value(
            question.get("difficulty", "")
        )
    )

    print("\nDifficulty score:")

    print(
        format_metadata_value(
            question.get(
                "difficulty_score",
                ""
            )
        )
    )

    print("\nRobustness:")

    print(
        format_metadata_value(
            question.get("robustness", "")
        )
    )

    print("\nExpected result:")

    print(
        format_metadata_value(
            question.get("expect", ""),
            default="Normal"
        )
    )

    print("\nExpected rows:")

    print(
        expected_rows
        if expected_rows is not None
        else "Unknown"
    )

    # --------------------------------------------------------
    # Correct field for the new EN CSV
    # --------------------------------------------------------

    print("\nQuestion:")

    print(
        format_metadata_value(
            question.get("question", "")
        )
    )

    print("\nGold code:")

    print(
        question["gold_code"]
    )

    # --------------------------------------------------------
    # Ensure SQL task
    # --------------------------------------------------------

    if (
        str(question["task"])
        .strip()
        .lower()
        != "sql"
    ):

        print(
            "\n❌ This validator supports "
            "SQL questions only."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Execute independently
    # --------------------------------------------------------

    heading(
        "EXECUTING GOLD CODE"
    )

    try:

        con = create_connection()

    except Exception as error:

        print(
            "\n❌ Failed to create database "
            "connection."
        )

        print(error)

        sys.exit(1)

    try:

        result = execute_gold(
            con,
            question["gold_code"]
        )

    except Exception as error:

        print(
            "\n❌ Supplied gold code failed "
            "to execute."
        )

        print(error)

        try:
            con.close()
        except Exception:
            pass

        sys.exit(1)

    finally:

        try:
            con.close()
        except Exception:
            pass

    print(
        "\n✅ Supplied gold code executed "
        "successfully."
    )

    print(
        "\nFirst 10 verification rows:"
    )

    print(
        result.head(10)
    )

    print(
        "\nVerification result shape:"
    )

    print(
        result.shape
    )

    # --------------------------------------------------------
    # Save independent rerun
    # --------------------------------------------------------

    output_file = (
        OUTPUT_DIR
        / f"{qid}_rerun.csv"
    )

    result.to_csv(
        output_file,
        index=False
    )

    print(
        "\nRerun saved to:"
    )

    print(
        output_file
    )

    # --------------------------------------------------------
    # Compare against supplied result
    # --------------------------------------------------------

    gold_path = find_gold_csv(qid)

    gold_code = str(
        question["gold_code"]
    )

    requires_order = (
        "order by"
        in gold_code.lower()
    )

    comparison, supplied_result = (
        compare_results(
            result,
            gold_path,
            ordered=requires_order
        )
    )

    # --------------------------------------------------------
    # Verification result quality
    # --------------------------------------------------------

    verification_quality = (
        analyse_data_quality(
            result
        )
    )

    print_quality_report(
        "VERIFICATION RESULT — DATA QUALITY",
        verification_quality
    )

    # --------------------------------------------------------
    # Supplied result quality
    # --------------------------------------------------------

    if supplied_result is not None:

        supplied_quality = (
            analyse_data_quality(
                supplied_result
            )
        )

        print_quality_report(
            "SUPPLIED RESULT — DATA QUALITY",
            supplied_quality
        )

    # --------------------------------------------------------
    # Automated report fields
    # --------------------------------------------------------

    print_report_summary(
        question,
        expected_rows,
        comparison,
        verification_quality,
    )

    # --------------------------------------------------------
    # Manual-review checklist
    # --------------------------------------------------------

    print_manual_review()

    # --------------------------------------------------------
    # Special warnings
    # --------------------------------------------------------

    robustness = format_metadata_value(
        question.get(
            "robustness",
            ""
        )
    )

    expect = format_metadata_value(
        question.get(
            "expect",
            ""
        ),
        default="Normal"
    )

    heading(
        "VALIDATION WARNINGS"
    )

    if expect.lower() == "empty":

        print(
            "⚠️ This question is explicitly "
            "marked expect='empty'."
        )

        print(
            "Confirm that the empty result is "
            "caused by correct query logic rather "
            "than an accidental filter or schema error."
        )

    else:

        print(
            "Expected-empty flag: No"
        )

    if robustness != "None":

        print(
            f"\n⚠️ Robustness item: "
            f"{robustness}"
        )

        print(
            "Review the question's ambiguity, "
            "schema assumptions, premise, "
            "paraphrasing or answerability "
            "as applicable."
        )

    else:

        print(
            "\nRobustness item: No"
        )

    print(
        "\nIMPORTANT:"
    )

    print(
        "Matching the supplied gold result "
        "proves reproducibility, not semantic "
        "correctness."
    )

    print(
        "Use the manual-review checks above "
        "before assigning the final "
        "PASS / FAIL verdict."
    )


if __name__ == "__main__":
    main()