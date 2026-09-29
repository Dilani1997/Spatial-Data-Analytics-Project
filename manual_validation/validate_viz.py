from pathlib import Path
import sys
import traceback
import warnings

import pandas as pd
import numpy as np
import geopandas as gpd

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from PIL import Image, ImageChops


# ============================================================
# Paths
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATABASE = ROOT / "database"
DB = DATABASE

BENCHMARK = ROOT / "geoquerybench_v0.1"

QUESTION_FILE = (
    BENCHMARK
    / "questions"
    / "geoquerybench_questions_EN.csv"
)

GOLD_RESULTS = (
    BENCHMARK
    / "gold_results"
)

OUTPUT_DIR = (
    ROOT
    / "validation_results"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# Load question
# ============================================================

def load_question(qid):

    df = pd.read_csv(QUESTION_FILE)

    row = df[
        df["qid"].astype(str) == str(qid)
    ]

    if row.empty:

        raise ValueError(
            f"Question {qid} not found in "
            f"{QUESTION_FILE}"
        )

    return row.iloc[0]


# ============================================================
# Find supplied gold image
# ============================================================

def find_gold_image(qid, question):

    # --------------------------------------------------------
    # First try output_file from question CSV
    # --------------------------------------------------------

    if "output_file" in question.index:

        output_file = question["output_file"]

        if pd.notna(output_file):

            output_file = str(output_file).strip()

            if output_file:

                candidate = (
                    GOLD_RESULTS
                    / output_file
                )

                if candidate.exists():

                    return candidate

    # --------------------------------------------------------
    # Standard QID.png
    # --------------------------------------------------------

    candidate = (
        GOLD_RESULTS
        / f"{qid}.png"
    )

    if candidate.exists():

        return candidate

    # --------------------------------------------------------
    # Fallback search
    # --------------------------------------------------------

    matches = list(
        GOLD_RESULTS.glob(
            f"*{qid}*.png"
        )
    )

    if len(matches) == 1:

        return matches[0]

    if len(matches) > 1:

        print(
            "\n⚠️ Multiple possible supplied "
            "PNG files found:"
        )

        for path in matches:

            print(
                " -",
                path.name
            )

    return None


# ============================================================
# Execute visualization gold code
# ============================================================

def execute_gold_code(code):

    # Close figures left by previous runs
    plt.close("all")

    namespace = {

        # Paths
        "ROOT": ROOT,
        "DATABASE": DATABASE,
        "DB": DB,
        "BENCHMARK": BENCHMARK,

        # Data libraries
        "pd": pd,
        "np": np,
        "gpd": gpd,

        # Plotting
        "plt": plt,

        # Utilities
        "Path": Path,
    }

    with warnings.catch_warnings():

        warnings.simplefilter(
            "default"
        )

        exec(
            code,
            namespace
        )

    # --------------------------------------------------------
    # Prefer explicitly created fig
    # --------------------------------------------------------

    if "fig" in namespace:

        fig = namespace["fig"]

        if hasattr(
            fig,
            "savefig"
        ):

            return fig, namespace

    # --------------------------------------------------------
    # Otherwise get latest matplotlib figure
    # --------------------------------------------------------

    fig_numbers = (
        plt.get_fignums()
    )

    if not fig_numbers:

        raise ValueError(
            "Gold visualization code executed "
            "but did not create a matplotlib "
            "figure."
        )

    fig = plt.figure(
        fig_numbers[-1]
    )

    return fig, namespace


# ============================================================
# Helper: safely get text
# ============================================================

def safe_text(value):

    try:

        text = str(value)

        return (
            text
            if text
            else "None"
        )

    except Exception:

        return "Unavailable"


# ============================================================
# Inspect matplotlib figure structure
# ============================================================

def inspect_figure(fig):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "FIGURE STRUCTURE"
    )

    print(
        "=" * 70
    )

    axes = fig.get_axes()

    print(
        "\nNumber of axes:",
        len(axes)
    )

    for i, ax in enumerate(
        axes,
        start=1
    ):

        print(
            f"\n--- Axis {i} ---"
        )

        # ----------------------------------------------------
        # Labels
        # ----------------------------------------------------

        print(
            "Title:",
            safe_text(
                ax.get_title()
            )
        )

        print(
            "X label:",
            safe_text(
                ax.get_xlabel()
            )
        )

        print(
            "Y label:",
            safe_text(
                ax.get_ylabel()
            )
        )

        # ----------------------------------------------------
        # Limits
        # ----------------------------------------------------

        try:

            print(
                "X limits:",
                tuple(
                    round(float(x), 4)
                    for x in ax.get_xlim()
                )
            )

        except Exception:

            print(
                "X limits: unavailable"
            )

        try:

            print(
                "Y limits:",
                tuple(
                    round(float(y), 4)
                    for y in ax.get_ylim()
                )
            )

        except Exception:

            print(
                "Y limits: unavailable"
            )

        # ----------------------------------------------------
        # Scales
        # ----------------------------------------------------

        try:

            print(
                "X scale:",
                ax.get_xscale()
            )

        except Exception:

            pass

        try:

            print(
                "Y scale:",
                ax.get_yscale()
            )

        except Exception:

            pass

        # ----------------------------------------------------
        # Plot objects
        # ----------------------------------------------------

        print(
            "Number of patches:",
            len(ax.patches)
        )

        print(
            "Number of lines:",
            len(ax.lines)
        )

        print(
            "Number of collections:",
            len(ax.collections)
        )

        print(
            "Number of images:",
            len(ax.images)
        )

        print(
            "Number of text annotations:",
            len(ax.texts)
        )

        # ----------------------------------------------------
        # Legend
        # ----------------------------------------------------

        legend = ax.get_legend()

        if legend is None:

            print(
                "Legend: None"
            )

        else:

            try:

                labels = [
                    text.get_text()
                    for text
                    in legend.get_texts()
                ]

                print(
                    "Legend labels:",
                    labels
                )

            except Exception:

                print(
                    "Legend: Present"
                )

        # ----------------------------------------------------
        # Tick labels
        # ----------------------------------------------------

        try:

            x_tick_labels = [
                t.get_text()
                for t
                in ax.get_xticklabels()
                if t.get_text()
            ]

            if x_tick_labels:

                print(
                    "X tick labels "
                    "(first 20):",
                    x_tick_labels[:20]
                )

        except Exception:

            pass

        try:

            y_tick_labels = [
                t.get_text()
                for t
                in ax.get_yticklabels()
                if t.get_text()
            ]

            if y_tick_labels:

                print(
                    "Y tick labels "
                    "(first 20):",
                    y_tick_labels[:20]
                )

        except Exception:

            pass


# ============================================================
# Inspect line data
# ============================================================

def inspect_line_data(fig):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "LINE DATA DIAGNOSTICS"
    )

    print(
        "=" * 70
    )

    found = False

    for axis_number, ax in enumerate(
        fig.get_axes(),
        start=1
    ):

        for line_number, line in enumerate(
            ax.lines,
            start=1
        ):

            found = True

            try:

                x = np.asarray(
                    line.get_xdata()
                )

                y = np.asarray(
                    line.get_ydata()
                )

                print(
                    f"\nAxis {axis_number}, "
                    f"Line {line_number}"
                )

                print(
                    "Label:",
                    line.get_label()
                )

                print(
                    "Number of points:",
                    len(x)
                )

                if (
                    len(x) > 0
                    and np.issubdtype(
                        x.dtype,
                        np.number
                    )
                ):

                    finite_x = x[
                        np.isfinite(x)
                    ]

                    if len(finite_x):

                        print(
                            "X range:",
                            float(
                                finite_x.min()
                            ),
                            "to",
                            float(
                                finite_x.max()
                            )
                        )

                if (
                    len(y) > 0
                    and np.issubdtype(
                        y.dtype,
                        np.number
                    )
                ):

                    finite_y = y[
                        np.isfinite(y)
                    ]

                    if len(finite_y):

                        print(
                            "Y range:",
                            float(
                                finite_y.min()
                            ),
                            "to",
                            float(
                                finite_y.max()
                            )
                        )

            except Exception as exc:

                print(
                    "Could not inspect line:",
                    exc
                )

    if not found:

        print(
            "\nNo line objects found."
        )


# ============================================================
# Inspect scatter / collection data
# ============================================================

def inspect_collection_data(fig):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "COLLECTION / SCATTER DIAGNOSTICS"
    )

    print(
        "=" * 70
    )

    found = False

    for axis_number, ax in enumerate(
        fig.get_axes(),
        start=1
    ):

        for collection_number, collection in enumerate(
            ax.collections,
            start=1
        ):

            found = True

            print(
                f"\nAxis {axis_number}, "
                f"Collection {collection_number}"
            )

            try:

                offsets = (
                    collection.get_offsets()
                )

                print(
                    "Number of offsets:",
                    len(offsets)
                )

                if len(offsets):

                    arr = np.asarray(
                        offsets,
                        dtype=float
                    )

                    finite = np.isfinite(
                        arr
                    ).all(axis=1)

                    arr = arr[
                        finite
                    ]

                    if len(arr):

                        print(
                            "X range:",
                            float(
                                arr[:, 0].min()
                            ),
                            "to",
                            float(
                                arr[:, 0].max()
                            )
                        )

                        print(
                            "Y range:",
                            float(
                                arr[:, 1].min()
                            ),
                            "to",
                            float(
                                arr[:, 1].max()
                            )
                        )

            except Exception:

                pass

            try:

                values = (
                    collection.get_array()
                )

                if values is not None:

                    values = np.asarray(
                        values
                    )

                    finite = values[
                        np.isfinite(values)
                    ]

                    print(
                        "Colour/value count:",
                        len(values)
                    )

                    if len(finite):

                        print(
                            "Colour/value range:",
                            float(
                                finite.min()
                            ),
                            "to",
                            float(
                                finite.max()
                            )
                        )

            except Exception:

                pass

    if not found:

        print(
            "\nNo collection objects found."
        )


# ============================================================
# Inspect bar / patch data
# ============================================================

def inspect_patch_data(fig):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "BAR / PATCH DIAGNOSTICS"
    )

    print(
        "=" * 70
    )

    total_patches = sum(
        len(ax.patches)
        for ax
        in fig.get_axes()
    )

    print(
        "\nTotal patches:",
        total_patches
    )

    if total_patches == 0:

        print(
            "No patch objects found."
        )

        return

    for axis_number, ax in enumerate(
        fig.get_axes(),
        start=1
    ):

        if not ax.patches:

            continue

        heights = []

        widths = []

        for patch in ax.patches:

            try:

                heights.append(
                    float(
                        patch.get_height()
                    )
                )

            except Exception:

                pass

            try:

                widths.append(
                    float(
                        patch.get_width()
                    )
                )

            except Exception:

                pass

        print(
            f"\nAxis {axis_number}:"
        )

        print(
            "Patch count:",
            len(ax.patches)
        )

        if heights:

            finite = [
                x
                for x in heights
                if np.isfinite(x)
            ]

            if finite:

                print(
                    "Height range:",
                    min(finite),
                    "to",
                    max(finite)
                )

        if widths:

            finite = [
                x
                for x in widths
                if np.isfinite(x)
            ]

            if finite:

                print(
                    "Width range:",
                    min(finite),
                    "to",
                    max(finite)
                )


# ============================================================
# Image comparison
# ============================================================

def inspect_images(
    rerun_path,
    gold_path
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "IMAGE COMPARISON"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Rerun
    # --------------------------------------------------------

    rerun = Image.open(
        rerun_path
    )

    print(
        "\nGenerated image:"
    )

    print(
        "Path:",
        rerun_path.name
    )

    print(
        "Size:",
        rerun.size
    )

    print(
        "Mode:",
        rerun.mode
    )

    # --------------------------------------------------------
    # Supplied image
    # --------------------------------------------------------

    if gold_path is None:

        print(
            "\n⚠️ No supplied gold PNG found."
        )

        return {
            "found": False,
            "same_size": None,
            "pixel_equal": None,
        }

    gold = Image.open(
        gold_path
    )

    print(
        "\nSupplied image:"
    )

    print(
        "Path:",
        gold_path.name
    )

    print(
        "Size:",
        gold.size
    )

    print(
        "Mode:",
        gold.mode
    )

    same_size = (
        rerun.size == gold.size
    )

    print(
        "\nSame pixel dimensions:",
        same_size
    )

    # --------------------------------------------------------
    # Optional exact pixel diagnostic
    #
    # Pixel equality is diagnostic only.
    # Different DPI / metadata / rendering can differ while
    # being semantically identical.
    # --------------------------------------------------------

    pixel_equal = False

    try:

        rerun_rgba = (
            rerun.convert("RGBA")
        )

        gold_rgba = (
            gold.convert("RGBA")
        )

        if (
            rerun_rgba.size
            == gold_rgba.size
        ):

            diff = ImageChops.difference(
                rerun_rgba,
                gold_rgba
            )

            pixel_equal = (
                diff.getbbox()
                is None
            )

    except Exception:

        pixel_equal = False

    print(
        "Exact pixel equality:",
        pixel_equal
    )

    print(
        "\nNOTE:"
    )

    print(
        "Exact pixel equality is diagnostic only "
        "and is NOT required for a visualization "
        "to pass."
    )

    print(
        "Manual semantic comparison is still "
        "required."
    )

    return {
        "found": True,
        "same_size": same_size,
        "pixel_equal": pixel_equal,
    }


# ============================================================
# Inspect namespace outputs
# ============================================================

def inspect_namespace(
    namespace
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "GOLD CODE OUTPUT OBJECTS"
    )

    print(
        "=" * 70
    )

    interesting = []

    ignored = {
        "ROOT",
        "DATABASE",
        "DB",
        "BENCHMARK",
        "pd",
        "np",
        "gpd",
        "plt",
        "Path",
        "__builtins__",
    }

    for name, value in namespace.items():

        if name in ignored:

            continue

        if isinstance(
            value,
            (
                pd.DataFrame,
                pd.Series,
                gpd.GeoDataFrame,
                gpd.GeoSeries,
            )
        ):

            interesting.append(
                (
                    name,
                    value
                )
            )

    if not interesting:

        print(
            "\nNo DataFrame/Series output "
            "objects detected."
        )

        return

    for name, value in interesting:

        print(
            f"\n{name}:"
        )

        try:

            print(
                "Type:",
                type(value).__name__
            )

            print(
                "Shape:",
                value.shape
            )

            if hasattr(
                value,
                "columns"
            ):

                print(
                    "Columns:",
                    list(
                        value.columns
                    )
                )

            print(
                "First rows:"
            )

            print(
                value.head(
                    5
                ).to_string()
            )

        except Exception as exc:

            print(
                "Could not inspect:",
                exc
            )


# ============================================================
# Print manual-review template
# ============================================================

def print_manual_review(
    qid,
    question,
    output_path,
    gold_path,
    image_info
):

    print(
        "\n"
        + "=" * 70
    )

    print(
        "ALL QUERY REVIEWS — AUTOMATED FIELDS"
    )

    print(
        "=" * 70
    )

    print(
        f"Query ID:             {qid}"
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
        "Expected rows:         "
        f"{question.get('n_rows', '')}"
    )

    if gold_path is not None:

        print(
            "Supplied result:       "
            f"{gold_path.name}"
        )

    else:

        print(
            "Supplied result:       "
            "NOT FOUND"
        )

    print(
        "Verification result:   "
        f"{output_path.name}"
    )

    print(
        "Supplied query runs:   PASS"
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "MANUAL VISUALISATION REVIEW REQUIRED"
    )

    print(
        "=" * 70
    )

    checks = [

        "Underlying data and filters are correct",

        "Aggregation / statistical logic is correct",

        "Sentinel and invalid values are handled correctly",

        "Units and conversions are correct",

        "Spatial logic and CRS are correct, if applicable",

        "Chart / map type answers the question",

        "Title accurately describes the figure",

        "X-axis label and units are correct",

        "Y-axis label and units are correct",

        "Legend / colourbar labels are correct",

        "Log scales are used correctly where required",

        "Categories / bins / thresholds are correct",

        "Layer ordering is correct for maps",

        "Required annotations or reference lines are present",

        "Visual encoding matches the underlying values",

        "No important information is hidden or misleading",

        "The supplied and rerun figures are semantically consistent",

        "The figure actually answers the question",

        "Client clarification / adjudication is not required",
    ]

    for check in checks:

        print(
            f"[ ] {check}"
        )

    print(
        "\nOverall verdict: "
        "MANUAL REVIEW REQUIRED"
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "Successful execution and a visually "
        "similar PNG prove reproducibility, "
        "not semantic correctness."
    )

    print(
        "Do NOT assign PASS until the chart/map "
        "logic and visual interpretation have "
        "been manually reviewed."
    )


# ============================================================
# Main
# ============================================================

def main():

    if len(sys.argv) != 2:

        print(
            "Usage: python "
            "manual_validation/"
            "validate_viz.py <QID>"
        )

        sys.exit(1)

    qid = str(
        sys.argv[1]
    ).strip()

    # --------------------------------------------------------
    # Load question
    # --------------------------------------------------------

    try:

        question = (
            load_question(qid)
        )

    except Exception:

        print(
            "\n❌ Failed to load question.\n"
        )

        traceback.print_exc()

        sys.exit(1)

    print(
        "\n"
        + "=" * 70
    )

    print(
        f"VALIDATING {qid}"
    )

    print(
        "=" * 70
    )

    print(
        "\nScenario:"
    )

    print(
        question.get(
            "scenario",
            ""
        )
    )

    if "qtype_name" in question.index:

        print(
            "\nQuestion type:"
        )

        print(
            question.get(
                "qtype_name",
                ""
            )
        )

    print(
        "\nTask:"
    )

    print(
        question.get(
            "task",
            ""
        )
    )

    print(
        "\nDifficulty:"
    )

    print(
        question.get(
            "difficulty",
            ""
        )
    )

    if "difficulty_score" in question.index:

        print(
            "\nDifficulty score:"
        )

        print(
            question.get(
                "difficulty_score",
                ""
            )
        )

    if "robustness" in question.index:

        print(
            "\nRobustness:"
        )

        robustness = question.get(
            "robustness",
            None
        )

        if pd.isna(
            robustness
        ):

            robustness = "None"

        print(
            robustness
        )

    if "expect" in question.index:

        print(
            "\nExpected result:"
        )

        expect = question.get(
            "expect",
            None
        )

        if pd.isna(
            expect
        ):

            expect = "None"

        print(
            expect
        )

    if "n_rows" in question.index:

        print(
            "\nExpected rows:"
        )

        print(
            question.get(
                "n_rows",
                ""
            )
        )

    print(
        "\nQuestion:"
    )

    print(
        question.get(
            "question",
            ""
        )
    )

    print(
        "\nGold code:"
    )

    print(
        question.get(
            "gold_code",
            ""
        )
    )

    # --------------------------------------------------------
    # Ensure task is viz
    # --------------------------------------------------------

    task = str(
        question.get(
            "task",
            ""
        )
    ).lower()

    if task != "viz":

        print(
            "\n❌ This validator is intended "
            "for visualization questions only."
        )

        print(
            "Question task:",
            task
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Execute gold code
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "EXECUTING GOLD CODE"
    )

    print(
        "=" * 70
    )

    try:

        fig, namespace = (
            execute_gold_code(
                str(
                    question[
                        "gold_code"
                    ]
                )
            )
        )

        print(
            "\n✅ Supplied gold visualization "
            "code executed successfully."
        )

        # ----------------------------------------------------
        # Figure diagnostics
        # ----------------------------------------------------

        inspect_figure(
            fig
        )

        inspect_line_data(
            fig
        )

        inspect_collection_data(
            fig
        )

        inspect_patch_data(
            fig
        )

        inspect_namespace(
            namespace
        )

        # ----------------------------------------------------
        # Save rerun
        # ----------------------------------------------------

        output_path = (
            OUTPUT_DIR
            / f"{qid}_rerun.png"
        )

        fig.savefig(
            output_path,
            dpi=150,
            bbox_inches="tight"
        )

        print(
            "\nRerun visualization saved to:"
        )

        print(
            output_path
        )

        # ----------------------------------------------------
        # Find supplied image
        # ----------------------------------------------------

        gold_path = (
            find_gold_image(
                qid,
                question
            )
        )

        # ----------------------------------------------------
        # Image comparison
        # ----------------------------------------------------

        image_info = (
            inspect_images(
                output_path,
                gold_path
            )
        )

        # ----------------------------------------------------
        # Automated summary
        # ----------------------------------------------------

        print(
            "\n"
            + "=" * 70
        )

        print(
            "AUTOMATED CHECK SUMMARY"
        )

        print(
            "=" * 70
        )

        print(
            "\nExecutable: YES"
        )

        print(
            "Rerun image generated: YES"
        )

        if image_info["found"]:

            print(
                "Supplied gold image found: YES"
            )

            print(
                "Same image dimensions:",
                image_info[
                    "same_size"
                ]
            )

            print(
                "Exact pixel equality:",
                image_info[
                    "pixel_equal"
                ]
            )

        else:

            print(
                "Supplied gold image found: "
                "CHECK REQUIRED"
            )

        # ----------------------------------------------------
        # Manual review
        # ----------------------------------------------------

        print_manual_review(
            qid,
            question,
            output_path,
            gold_path,
            image_info
        )

        # ----------------------------------------------------
        # Close
        # ----------------------------------------------------

        plt.close(
            fig
        )

    except Exception:

        print(
            "\n❌ Gold visualization code "
            "execution failed.\n"
        )

        traceback.print_exc()

        print(
            "\n"
            + "=" * 70
        )

        print(
            "AUTOMATED CHECK SUMMARY"
        )

        print(
            "=" * 70
        )

        print(
            "\nExecutable: NO"
        )

        print(
            "Rerun image generated: NO"
        )

        print(
            "Provided gold image found: "
            "NOT CHECKED"
        )

        print(
            "\nOverall verdict: "
            "MANUAL REVIEW REQUIRED"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()