from pathlib import Path
import sys
import traceback

import numpy as np
import pandas as pd
import geopandas as gpd


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
DB = DATABASE

GOLD_RESULTS = BENCHMARK / "gold_results"

MANIFEST_FILE = GOLD_RESULTS / "_manifest.csv"

OUTPUT_DIR = ROOT / "validation_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Sentinel candidates
# ============================================================

# Diagnostic only.
# A value appearing here does NOT automatically mean that
# the value is invalid for a particular field.
SENTINEL_CANDIDATES = {
    -999999,
    -99999,
    -9999,
    -999,
    -99,
    -9,
    999,
    9999,
    99999,
    999999,
}


# ============================================================
# Load question metadata
# ============================================================

def load_question(qid):

    df = pd.read_csv(QUESTION_FILE)

    row = df[
        df["qid"].astype(str) == str(qid)
    ]

    if row.empty:
        raise ValueError(
            f"Question {qid} not found in "
            f"{QUESTION_FILE.name}."
        )

    return row.iloc[0]


# ============================================================
# Load manifest
# ============================================================

def load_manifest():

    if not MANIFEST_FILE.exists():
        return None

    return pd.read_csv(MANIFEST_FILE)


def get_manifest_row(qid, manifest):

    if manifest is None:
        return None

    if "qid" not in manifest.columns:
        return None

    row = manifest[
        manifest["qid"].astype(str) == str(qid)
    ]

    if row.empty:
        return None

    return row.iloc[0]


# ============================================================
# Find supplied result
# ============================================================

def find_supplied_result(qid, question=None, manifest_row=None):

    # --------------------------------------------------------
    # 1. Prefer explicit output_file from question metadata
    # --------------------------------------------------------

    if question is not None:

        output_file = question.get(
            "output_file",
            None
        )

        if (
            output_file is not None
            and not pd.isna(output_file)
        ):

            path = GOLD_RESULTS / str(output_file)

            if path.exists():
                return path

    # --------------------------------------------------------
    # 2. Try manifest
    # --------------------------------------------------------

    if manifest_row is not None:

        for column in [
            "output_file",
            "file",
            "filename",
            "result_file",
        ]:

            if column in manifest_row.index:

                value = manifest_row[column]

                if (
                    value is not None
                    and not pd.isna(value)
                ):

                    path = (
                        GOLD_RESULTS
                        / str(value)
                    )

                    if path.exists():
                        return path

    # --------------------------------------------------------
    # 3. Standard CSV fallback
    # --------------------------------------------------------

    path = GOLD_RESULTS / f"{qid}.csv"

    if path.exists():
        return path

    return None


# ============================================================
# Execute GeoPandas gold code
# ============================================================

def execute_gold(gold_code):

    namespace = {
        "__builtins__": __builtins__,
        "DB": DATABASE,
        "DATABASE": DATABASE,
        "ROOT": ROOT,
        "BENCHMARK": BENCHMARK,
        "pd": pd,
        "np": np,
        "gpd": gpd,
        "Path": Path,
    }

    exec(
        str(gold_code),
        namespace
    )

    if "result" not in namespace:
        raise ValueError(
            "Gold code executed but did not create "
            "a variable named 'result'."
        )

    result = namespace["result"]

    if isinstance(result, pd.Series):
        result = result.to_frame()

    # GeoDataFrame is also a pandas DataFrame subclass,
    # so this accepts both DataFrame and GeoDataFrame.
    if not isinstance(result, pd.DataFrame):
        raise TypeError(
            "Expected result to be a pandas DataFrame "
            "or GeoPandas GeoDataFrame, but got "
            f"{type(result).__name__}."
        )

    return result


# ============================================================
# Convert geometry for CSV comparison if necessary
# ============================================================

def prepare_for_csv(df):

    """
    Convert geometry-like columns to stable string
    representations before saving/comparing with supplied CSV.

    This preserves ordinary non-spatial columns unchanged.
    """

    out = df.copy()

    # --------------------------------------------------------
    # Active GeoDataFrame geometry
    # --------------------------------------------------------

    if isinstance(out, gpd.GeoDataFrame):

        geometry_name = (
            out.geometry.name
            if out.geometry is not None
            else None
        )

        if (
            geometry_name is not None
            and geometry_name in out.columns
        ):

            out[geometry_name] = (
                out[geometry_name]
                .apply(
                    lambda x:
                    x.wkt
                    if x is not None
                    and not pd.isna(x)
                    else None
                )
            )

            out = pd.DataFrame(out)

    # --------------------------------------------------------
    # Other object columns containing shapely geometries
    # --------------------------------------------------------

    for column in out.columns:

        if out[column].dtype != "object":
            continue

        non_null = out[column].dropna()

        if non_null.empty:
            continue

        sample = non_null.iloc[0]

        if hasattr(sample, "wkt"):

            out[column] = out[column].apply(
                lambda x:
                x.wkt
                if x is not None
                and not pd.isna(x)
                else None
            )

    return out


# ============================================================
# Normalise comparable values
# ============================================================

def normalise_types(left, right):

    left = left.copy()
    right = right.copy()

    for column in left.columns:

        left_numeric = pd.to_numeric(
            left[column],
            errors="coerce"
        )

        right_numeric = pd.to_numeric(
            right[column],
            errors="coerce"
        )

        left_non_null = left[column].notna()
        right_non_null = right[column].notna()

        left_all_numeric = (
            left_numeric[left_non_null]
            .notna()
            .all()
        )

        right_all_numeric = (
            right_numeric[right_non_null]
            .notna()
            .all()
        )

        if (
            left_all_numeric
            and right_all_numeric
        ):

            left[column] = left_numeric
            right[column] = right_numeric

    return left, right


# ============================================================
# Compare results
# ============================================================

def compare_results(result, supplied_path):

    print("\n" + "=" * 70)
    print("RESULT COMPARISON")
    print("=" * 70)

    comparison = {
        "supplied_found": False,
        "row_count_match": False,
        "column_match": False,
        "value_match": False,
        "ordering_match": False,
        "supplied_rows": None,
        "verification_rows": len(result),
    }

    if supplied_path is None:

        print(
            "⚠️ No supplied result CSV found."
        )

        return comparison

    comparison["supplied_found"] = True

    print(
        f"Supplied result file: "
        f"{supplied_path.name}"
    )

    supplied = pd.read_csv(
        supplied_path
    )

    verification = prepare_for_csv(
        result
    )

    comparison["supplied_rows"] = len(
        supplied
    )

    print()
    print(
        "Verification shape:",
        verification.shape
    )

    print(
        "Supplied shape:    ",
        supplied.shape
    )

    print()
    print("Verification columns:")
    print(list(verification.columns))

    print("\nSupplied columns:")
    print(list(supplied.columns))

    # --------------------------------------------------------
    # Row count
    # --------------------------------------------------------

    comparison["row_count_match"] = (
        len(verification)
        == len(supplied)
    )

    # --------------------------------------------------------
    # Columns
    # --------------------------------------------------------

    comparison["column_match"] = (
        list(verification.columns)
        == list(supplied.columns)
    )

    if not comparison["row_count_match"]:

        print("\n❌ Row count mismatch.")
        return comparison

    if not comparison["column_match"]:

        print("\n❌ Column mismatch.")
        return comparison

    # --------------------------------------------------------
    # Empty result
    # --------------------------------------------------------

    if (
        verification.empty
        and supplied.empty
    ):

        comparison["value_match"] = True
        comparison["ordering_match"] = True

        print(
            "\n✅ Both verification and supplied "
            "results are empty."
        )

        print(
            "⚠️ Empty-result correctness must still "
            "be checked manually."
        )

        return comparison

    # --------------------------------------------------------
    # Normalise types
    # --------------------------------------------------------

    verification, supplied = normalise_types(
        verification,
        supplied
    )

    # --------------------------------------------------------
    # First try exact row ordering
    # --------------------------------------------------------

    verification_ordered = (
        verification
        .reset_index(drop=True)
    )

    supplied_ordered = (
        supplied
        .reset_index(drop=True)
    )

    try:

        pd.testing.assert_frame_equal(
            verification_ordered,
            supplied_ordered,
            check_dtype=False,
            check_exact=False,
            rtol=1e-7,
            atol=1e-9,
        )

        comparison["value_match"] = True
        comparison["ordering_match"] = True

        print(
            "\n✅ Values and row ordering match."
        )

        return comparison

    except AssertionError:

        pass

    # --------------------------------------------------------
    # Fallback: compare unordered rows
    # --------------------------------------------------------

    try:

        columns = list(
            verification.columns
        )

        verification_unordered = (
            verification
            .sort_values(
                columns,
                na_position="last"
            )
            .reset_index(drop=True)
        )

        supplied_unordered = (
            supplied
            .sort_values(
                columns,
                na_position="last"
            )
            .reset_index(drop=True)
        )

        pd.testing.assert_frame_equal(
            verification_unordered,
            supplied_unordered,
            check_dtype=False,
            check_exact=False,
            rtol=1e-7,
            atol=1e-9,
        )

        comparison["value_match"] = True
        comparison["ordering_match"] = False

        print(
            "\n✅ Same rows and values."
        )

        print(
            "⚠️ Row ordering differs."
        )

        return comparison

    except Exception as error:

        comparison["value_match"] = False
        comparison["ordering_match"] = False

        print(
            "\n⚠️ Result values differ from "
            "the supplied result."
        )

        print("\nDifference:")
        print(str(error)[:1500])

        return comparison


# ============================================================
# Data-quality diagnostics
# ============================================================

def analyse_data_quality(df):

    df = prepare_for_csv(df)

    report = {
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

    report["duplicate_rows"] = int(
        df.duplicated().sum()
    )

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    missing = df.isna().sum()

    report["missing_cells"] = int(
        missing.sum()
    )

    report["missing_by_column"] = {
        column: int(count)
        for column, count
        in missing.items()
        if count > 0
    }

    # --------------------------------------------------------
    # Numeric diagnostics
    # --------------------------------------------------------

    for column in df.columns:

        numeric = pd.to_numeric(
            df[column],
            errors="coerce"
        )

        valid_numeric = numeric.dropna()

        if valid_numeric.empty:
            continue

        # Negative values
        negative_count = int(
            (valid_numeric < 0).sum()
        )

        if negative_count > 0:

            report[
                "negative_by_column"
            ][column] = negative_count

            report[
                "negative_numeric_cells"
            ] += negative_count

        # Sentinel candidates
        sentinel_mask = (
            valid_numeric
            .isin(SENTINEL_CANDIDATES)
        )

        sentinel_count = int(
            sentinel_mask.sum()
        )

        if sentinel_count > 0:

            values = (
                valid_numeric[
                    sentinel_mask
                ]
                .value_counts()
                .sort_index()
            )

            report[
                "sentinel_by_column"
            ][column] = {
                str(value): int(count)
                for value, count
                in values.items()
            }

            report[
                "sentinel_cells"
            ] += sentinel_count

    return report


def print_data_quality(
    title,
    report,
):

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print(
        f"Duplicate rows: "
        f"{report['duplicate_rows']}"
    )

    print(
        f"Missing cells: "
        f"{report['missing_cells']}"
    )

    if report["missing_by_column"]:

        print("\nMissing values by column:")

        for column, count in (
            report[
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

    print()
    print(
        "Negative numeric cells:",
        report[
            "negative_numeric_cells"
        ]
    )

    if report["negative_by_column"]:

        print(
            "Negative values by column:"
        )

        for column, count in (
            report[
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

    print()
    print(
        "Sentinel candidate cells:",
        report["sentinel_cells"]
    )

    if report["sentinel_by_column"]:

        print("Sentinel candidates:")

        for column, values in (
            report[
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

    print()
    print(
        "NOTE: Negative and sentinel values "
        "are diagnostic only. They do not "
        "automatically mean the query is incorrect."
    )


# ============================================================
# Question metadata helpers
# ============================================================

def clean_metadata_value(
    value,
    default="None",
):

    if value is None:
        return default

    try:

        if pd.isna(value):
            return default

    except Exception:
        pass

    return str(value)


def get_expected_rows(
    question,
    manifest_row=None,
):

    # Prefer n_rows from the question file.
    if "n_rows" in question.index:

        value = question["n_rows"]

        if not pd.isna(value):

            try:
                return int(value)

            except Exception:
                return value

    # Fallback to manifest.
    if manifest_row is not None:

        for column in [
            "n_rows",
            "rows",
            "row_count",
        ]:

            if column in manifest_row.index:

                value = (
                    manifest_row[column]
                )

                if not pd.isna(value):

                    try:
                        return int(value)

                    except Exception:
                        return value

    return None


def is_expected_empty(question):

    expect = clean_metadata_value(
        question.get(
            "expect",
            None
        ),
        default="",
    ).lower()

    n_rows = question.get(
        "n_rows",
        None
    )

    if (
        n_rows is not None
        and not pd.isna(n_rows)
    ):

        try:

            if int(n_rows) == 0:
                return True

        except Exception:
            pass

    return (
        "empty" in expect
        or "zero" in expect
    )


def is_robustness_item(question):

    robustness = clean_metadata_value(
        question.get(
            "robustness",
            None
        ),
        default="",
    ).strip()

    return (
        robustness != ""
        and robustness.lower()
        not in {
            "none",
            "nan",
            "na",
            "n/a",
        }
    )


# ============================================================
# Automated review summary
# ============================================================

def print_automated_fields(
    qid,
    question,
    expected_rows,
    supplied_path,
    rerun_path,
    comparison,
    verification_quality,
):

    print("\n" + "=" * 70)
    print(
        "ALL QUERY REVIEWS — "
        "AUTOMATED FIELDS"
    )
    print("=" * 70)

    print(
        f"Query ID:             {qid}"
    )

    print(
        "Domain:              ",
        clean_metadata_value(
            question.get(
                "scenario",
                None
            )
        ),
    )

    print(
        "Method:              ",
        clean_metadata_value(
            question.get(
                "task",
                None
            )
        ),
    )

    print(
        "Difficulty:          ",
        clean_metadata_value(
            question.get(
                "difficulty",
                None
            )
        ),
    )

    print(
        "Question (EN):       ",
        clean_metadata_value(
            question.get(
                "question",
                None
            )
        ),
    )

    print(
        "Expected rows:        ",
        expected_rows,
    )

    print(
        "Supplied result:      ",
        (
            supplied_path.name
            if supplied_path
            else "Not found"
        ),
    )

    print(
        "Verification result:  ",
        rerun_path.name,
    )

    print(
        "Supplied rows:        ",
        comparison[
            "supplied_rows"
        ],
    )

    print(
        "Verification rows:    ",
        comparison[
            "verification_rows"
        ],
    )

    print(
        "Row count match:      ",
        comparison[
            "row_count_match"
        ],
    )

    print(
        "Column match:         ",
        comparison[
            "column_match"
        ],
    )

    print(
        "Value/content match:  ",
        comparison[
            "value_match"
        ],
    )

    print(
        "Duplicate rows:       ",
        verification_quality[
            "duplicate_rows"
        ],
    )

    print(
        "Missing cells:        ",
        verification_quality[
            "missing_cells"
        ],
    )

    print(
        "Negative numeric cells:",
        verification_quality[
            "negative_numeric_cells"
        ],
    )

    print(
        "Negative values by column:",
        (
            verification_quality[
                "negative_by_column"
            ]
            if verification_quality[
                "negative_by_column"
            ]
            else "None"
        ),
    )

    print(
        "Sentinel values:      ",
        verification_quality[
            "sentinel_cells"
        ],
    )

    supplied_query_runs = (
        comparison[
            "supplied_found"
        ]
        and comparison[
            "row_count_match"
        ]
        and comparison[
            "column_match"
        ]
        and comparison[
            "value_match"
        ]
    )

    print()
    print(
        "Supplied query runs:  ",
        (
            "PASS"
            if supplied_query_runs
            else "CHECK REQUIRED"
        ),
    )


# ============================================================
# Manual-review reminder
# ============================================================

def print_manual_review():

    print("\n" + "=" * 70)
    print("MANUAL REVIEW REQUIRED")
    print("=" * 70)

    checks = [
        "Logic answers the question",
        (
            "Output / visualisation "
            "matches the question"
        ),
        (
            "Tables, fields and joins "
            "are correct"
        ),
        (
            "Units and thresholds "
            "are correct"
        ),
        (
            "Spatial / domain logic "
            "is correct"
        ),
        (
            "CRS and spatial operations "
            "are correct"
        ),
        (
            "Spatial predicates, distance "
            "and area logic are correct"
        ),
        (
            "Robustness / ambiguity is "
            "handled correctly, if applicable"
        ),
        (
            "Decide whether client "
            "clarification or adjudication "
            "is required"
        ),
    ]

    for check in checks:
        print(f"[ ] {check}")

    print(
        "\nOverall verdict: "
        "MANUAL REVIEW REQUIRED"
    )

    print(
        "\nDo NOT assign PASS only because "
        "the verification result matches "
        "the supplied gold result."
    )


# ============================================================
# Validation warnings
# ============================================================

def print_warnings(
    question,
    comparison,
):

    print("\n" + "=" * 70)
    print("VALIDATION WARNINGS")
    print("=" * 70)

    expected_empty = (
        is_expected_empty(question)
    )

    robustness_item = (
        is_robustness_item(question)
    )

    print(
        "Expected-empty flag:",
        "Yes" if expected_empty else "No",
    )

    print()

    if robustness_item:

        print(
            "⚠️ Robustness item:",
            clean_metadata_value(
                question.get(
                    "robustness",
                    None
                )
            ),
        )

        print(
            "Review the question's ambiguity, "
            "schema assumptions, premise, "
            "paraphrasing or answerability "
            "as applicable."
        )

    else:

        print(
            "Robustness item: No"
        )

    if (
        comparison["value_match"]
        and not comparison[
            "ordering_match"
        ]
    ):

        print()
        print(
            "⚠️ Verification and supplied "
            "results contain the same rows "
            "and values, but row ordering "
            "differs."
        )

        print(
            "Check whether the gold code "
            "defines a deterministic ordering "
            "or whether tied values make the "
            "difference acceptable."
        )

    print()
    print(
        "IMPORTANT:\n"
        "Matching the supplied gold result "
        "proves reproducibility, not semantic "
        "correctness.\n"
        "Use the manual-review checks above "
        "before assigning the final PASS / "
        "FAIL verdict."
    )


# ============================================================
# Main
# ============================================================

def main():

    if len(sys.argv) != 2:

        print(
            "Usage: python "
            "manual_validation/"
            "validate_geopandas.py <QID>"
        )

        sys.exit(1)

    qid = str(sys.argv[1])

    # --------------------------------------------------------
    # Load metadata
    # --------------------------------------------------------

    question = load_question(qid)

    manifest = load_manifest()

    manifest_row = get_manifest_row(
        qid,
        manifest
    )

    task = clean_metadata_value(
        question.get(
            "task",
            None
        ),
        default="",
    ).lower()

    if task != "geopandas":

        raise ValueError(
            f"{qid} has task='{task}', "
            "not 'geopandas'."
        )

    expected_rows = get_expected_rows(
        question,
        manifest_row
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print(f"VALIDATING {qid}")
    print("=" * 70)

    print("\nScenario:")
    print(
        clean_metadata_value(
            question.get(
                "scenario",
                None
            )
        )
    )

    print("\nQuestion type:")
    print(
        clean_metadata_value(
            question.get(
                "qtype_name",
                question.get(
                    "qtype",
                    None
                )
            )
        )
    )

    print("\nTask:")
    print(
        clean_metadata_value(
            question.get(
                "task",
                None
            )
        )
    )

    print("\nDifficulty:")
    print(
        clean_metadata_value(
            question.get(
                "difficulty",
                None
            )
        )
    )

    print("\nDifficulty score:")
    print(
        clean_metadata_value(
            question.get(
                "difficulty_score",
                None
            )
        )
    )

    print("\nRobustness:")
    print(
        clean_metadata_value(
            question.get(
                "robustness",
                None
            )
        )
    )

    print("\nExpected result:")
    print(
        clean_metadata_value(
            question.get(
                "expect",
                None
            )
        )
    )

    print("\nExpected rows:")
    print(expected_rows)

    print("\nQuestion:")
    print(
        clean_metadata_value(
            question.get(
                "question",
                None
            )
        )
    )

    print("\nGold code:")
    print(
        question["gold_code"]
    )

    # --------------------------------------------------------
    # Execute
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("EXECUTING GOLD CODE")
    print("=" * 70)

    try:

        result = execute_gold(
            question["gold_code"]
        )

        print(
            "\n✅ Supplied gold code "
            "executed successfully."
        )

        display_result = prepare_for_csv(
            result
        )

        print(
            "\nFirst 10 verification rows:"
        )

        print(
            display_result.head(10)
        )

        print(
            "\nVerification result shape:"
        )

        print(
            display_result.shape
        )

        # ----------------------------------------------------
        # Save rerun
        # ----------------------------------------------------

        rerun_path = (
            OUTPUT_DIR
            / f"{qid}_rerun.csv"
        )

        display_result.to_csv(
            rerun_path,
            index=False
        )

        print(
            "\nRerun saved to:"
        )

        print(rerun_path)

        # ----------------------------------------------------
        # Supplied result
        # ----------------------------------------------------

        supplied_path = (
            find_supplied_result(
                qid,
                question,
                manifest_row
            )
        )

        # ----------------------------------------------------
        # Compare
        # ----------------------------------------------------

        comparison = compare_results(
            display_result,
            supplied_path
        )

        # ----------------------------------------------------
        # Data-quality diagnostics
        # ----------------------------------------------------

        verification_quality = (
            analyse_data_quality(
                display_result
            )
        )

        print_data_quality(
            (
                "VERIFICATION RESULT — "
                "DATA QUALITY"
            ),
            verification_quality,
        )

        if supplied_path is not None:

            supplied_df = pd.read_csv(
                supplied_path
            )

            supplied_quality = (
                analyse_data_quality(
                    supplied_df
                )
            )

            print_data_quality(
                (
                    "SUPPLIED RESULT — "
                    "DATA QUALITY"
                ),
                supplied_quality,
            )

        # ----------------------------------------------------
        # Automated report fields
        # ----------------------------------------------------

        print_automated_fields(
            qid=qid,
            question=question,
            expected_rows=expected_rows,
            supplied_path=supplied_path,
            rerun_path=rerun_path,
            comparison=comparison,
            verification_quality=(
                verification_quality
            ),
        )

        # ----------------------------------------------------
        # Manual review
        # ----------------------------------------------------

        print_manual_review()

        # ----------------------------------------------------
        # Warnings
        # ----------------------------------------------------

        print_warnings(
            question,
            comparison
        )

    except Exception:

        print(
            "\n❌ Supplied gold code "
            "execution failed.\n"
        )

        traceback.print_exc()

        print("\n" + "=" * 70)
        print(
            "AUTOMATED CHECK SUMMARY"
        )
        print("=" * 70)

        print(
            "Supplied query runs: FAIL"
        )

        print(
            "\nIMPORTANT: An execution failure "
            "does not automatically prove that "
            "the benchmark question itself is "
            "semantically incorrect. Check "
            "whether the failure comes from the "
            "validator environment, missing "
            "imports, package versions, paths, "
            "CRS support or the supplied code."
        )


if __name__ == "__main__":
    main()