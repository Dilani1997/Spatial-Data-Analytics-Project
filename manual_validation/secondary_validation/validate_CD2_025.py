from pathlib import Path

import pandas as pd
import geopandas as gpd


# ============================================================
# Paths
# ============================================================

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "database"

SUPPLIED_RESULT = (
    ROOT
    / "geoquerybench_v0.1"
    / "gold_results"
    / "CD2-025.csv"
)


# ============================================================
# Load surface soil Au anomalies
# ============================================================

print("=" * 70)
print("CD2-025 SECONDARY VALIDATION")
print("=" * 70)

s = pd.read_parquet(
    DB / "B_surface" / "surface_sample.parquet",
    columns=[
        "uid",
        "medium",
        "longitude",
        "latitude",
    ],
)

a = pd.read_parquet(
    DB / "B_surface" / "surface_assay.parquet",
    columns=[
        "uid",
        "au_ppm",
    ],
)

soil = (
    s[s.medium == "soil"]
    .merge(a, on="uid")
)

# Question says "over 100 ppb".
# 100 ppb = 0.1 ppm.
anom = soil[
    soil.au_ppm > 0.1
].copy()

g = gpd.GeoDataFrame(
    anom,
    geometry=gpd.points_from_xy(
        anom.longitude,
        anom.latitude,
    ),
    crs="EPSG:7844",
).to_crs(epsg=9473)


# ============================================================
# Load drill-hole maximum Au
# ============================================================

maxg = gpd.read_parquet(
    DB
    / "B_surface"
    / "drillhole_maxgrade.parquet",
    columns=[
        "au_ppm",
        "geometry",
    ],
).rename(
    columns={
        "au_ppm": "hole_max_au",
    }
).to_crs(epsg=9473)

# Stable diagnostic identifier for each drill-hole row.
maxg = maxg.reset_index(
    names="hole_row_id"
)


# ============================================================
# Run nearest spatial join WITHOUT dropping ties
# ============================================================

near_all = gpd.sjoin_nearest(
    g,
    maxg[
        [
            "hole_row_id",
            "hole_max_au",
            "geometry",
        ]
    ],
    max_distance=1000,
    distance_col="d_m",
)


# ============================================================
# Basic population checks
# ============================================================

n_anomalies = len(g)

n_with_hole = (
    near_all["uid"]
    .nunique()
)

n_without_hole = (
    n_anomalies - n_with_hole
)

print("\n" + "=" * 70)
print("1. BASIC POPULATION CHECK")
print("=" * 70)

print(
    "Total soil Au anomalies (>100 ppb):",
    n_anomalies,
)

print(
    "Nearest-join rows:",
    len(near_all),
)

print(
    "Distinct anomalies with a hole <=1 km:",
    n_with_hole,
)

print(
    "Anomalies with no hole <=1 km:",
    n_without_hole,
)


# ============================================================
# Diagnose nearest-neighbour ties
# ============================================================

counts = (
    near_all
    .groupby("uid")
    .size()
)

tie_uids = (
    counts[counts > 1]
    .index
)

n_tied = len(tie_uids)

max_matches = (
    int(counts.max())
    if not counts.empty
    else 0
)

print("\n" + "=" * 70)
print("2. NEAREST-NEIGHBOUR TIES")
print("=" * 70)

print(
    "Samples with >1 equally-nearest match:",
    n_tied,
)

print(
    "Maximum nearest matches for one sample:",
    max_matches,
)


# ============================================================
# Analyse grade ambiguity in tied nearest holes
# ============================================================

tied = near_all[
    near_all["uid"].isin(
        tie_uids
    )
].copy()

n_different_grade = 0
n_cross_threshold = 0
crossing_ids = []

if not tied.empty:

    tie_stats = (
        tied
        .groupby("uid")["hole_max_au"]
        .agg(
            count="count",
            min_grade="min",
            max_grade="max",
            n_unique_grade="nunique",
        )
    )

    different_grade = (
        tie_stats[
            "n_unique_grade"
        ] > 1
    )

    # Question says "at least 1 gram per tonne".
    # 1 g/t Au = 1 ppm.
    cross_threshold = (
        (tie_stats["min_grade"] < 1.0)
        &
        (tie_stats["max_grade"] >= 1.0)
    )

    n_different_grade = int(
        different_grade.sum()
    )

    n_cross_threshold = int(
        cross_threshold.sum()
    )

    crossing_ids = list(
        tie_stats[
            cross_threshold
        ].index
    )

print("\n" + "=" * 70)
print("3. TIE GRADE AMBIGUITY")
print("=" * 70)

print(
    "Tied samples with different "
    "hole_max_au values:",
    n_different_grade,
)

print(
    "Tied samples crossing the 1 g/t threshold:",
    n_cross_threshold,
)


# ============================================================
# Show examples of classification-changing ties
# ============================================================

print("\n" + "=" * 70)
print("4. EXAMPLES OF THRESHOLD-CROSSING TIES")
print("=" * 70)

if crossing_ids:

    examples = (
        tied[
            tied["uid"].isin(
                crossing_ids[:20]
            )
        ][
            [
                "uid",
                "hole_row_id",
                "hole_max_au",
                "d_m",
            ]
        ]
        .sort_values(
            [
                "uid",
                "hole_max_au",
                "hole_row_id",
            ]
        )
    )

    print(
        examples.to_string(
            index=False
        )
    )

else:

    print(
        "No tied nearest-hole matches "
        "cross the 1 g/t threshold."
    )


# ============================================================
# Reproduce current arbitrary drop_duplicates behaviour
# ============================================================

current = (
    near_all
    .drop_duplicates("uid")
    .copy()
)

current_both = int(
    (
        current["hole_max_au"]
        >= 1.0
    ).sum()
)

current_surface_only = int(
    (
        current["hole_max_au"]
        < 1.0
    ).sum()
)

print("\n" + "=" * 70)
print("5. CURRENT GOLD-CODE CLASSIFICATION")
print("=" * 70)

print(
    "both_anomalous:",
    current_both,
)

print(
    "surface_only:",
    current_surface_only,
)

print(
    "no_hole_within_1km:",
    n_without_hole,
)

print(
    "Total:",
    (
        current_both
        + current_surface_only
        + n_without_hole
    ),
)


# ============================================================
# Deterministic diagnostic alternatives
# ============================================================

# ------------------------------------------------------------
# Policy A:
# smallest hole_row_id among tied nearest holes
# ------------------------------------------------------------

policy_a = (
    near_all
    .sort_values(
        [
            "uid",
            "hole_row_id",
        ]
    )
    .drop_duplicates(
        "uid"
    )
)

a_both = int(
    (
        policy_a["hole_max_au"]
        >= 1.0
    ).sum()
)

a_surface = int(
    (
        policy_a["hole_max_au"]
        < 1.0
    ).sum()
)


# ------------------------------------------------------------
# Policy B:
# classify as anomalous if ANY equally-nearest hole >=1 g/t
# ------------------------------------------------------------

policy_b = (
    near_all
    .groupby("uid")[
        "hole_max_au"
    ]
    .max()
)

b_both = int(
    (
        policy_b >= 1.0
    ).sum()
)

b_surface = int(
    (
        policy_b < 1.0
    ).sum()
)


# ------------------------------------------------------------
# Policy C:
# classify as anomalous only if ALL equally-nearest holes >=1
# ------------------------------------------------------------

policy_c = (
    near_all
    .groupby("uid")[
        "hole_max_au"
    ]
    .min()
)

c_both = int(
    (
        policy_c >= 1.0
    ).sum()
)

c_surface = int(
    (
        policy_c < 1.0
    ).sum()
)


print("\n" + "=" * 70)
print("6. DETERMINISTIC TIE-POLICY SENSITIVITY")
print("=" * 70)

print("\nPolicy A — smallest hole_row_id:")
print(
    "  both_anomalous:",
    a_both,
)
print(
    "  surface_only:",
    a_surface,
)

print(
    "\nPolicy B — ANY tied nearest hole >=1 g/t:"
)
print(
    "  both_anomalous:",
    b_both,
)
print(
    "  surface_only:",
    b_surface,
)

print(
    "\nPolicy C — ALL tied nearest holes >=1 g/t:"
)
print(
    "  both_anomalous:",
    c_both,
)
print(
    "  surface_only:",
    c_surface,
)


# ============================================================
# Supplied result
# ============================================================

print("\n" + "=" * 70)
print("7. SUPPLIED RESULT")
print("=" * 70)

if SUPPLIED_RESULT.exists():

    supplied = pd.read_csv(
        SUPPLIED_RESULT
    )

    print(
        supplied.to_string(
            index=False
        )
    )

else:

    print(
        "Supplied result not found:",
        SUPPLIED_RESULT
    )


# ============================================================
# Final diagnostic summary
# ============================================================

print("\n" + "=" * 70)
print("8. SECONDARY VALIDATION SUMMARY")
print("=" * 70)

if n_cross_threshold > 0:

    print(
        "⚠️ CLASSIFICATION-CHANGING "
        "NEAREST-NEIGHBOUR TIES FOUND."
    )

    print(
        f"{n_cross_threshold} soil anomalies "
        "have equally-nearest drill-hole matches "
        "on opposite sides of the 1 g/t threshold."
    )

    print(
        "\nThe use of:"
    )

    print(
        "    drop_duplicates('uid')"
    )

    print(
        "\ndoes not define which tied nearest "
        "hole should determine the classification."
    )

    print(
        "\nIf alternative deterministic policies "
        "produce different counts, the supplied "
        "gold answer depends on an undefined "
        "tie-handling rule."
    )

else:

    print(
        "✅ No nearest-neighbour ties were found "
        "that cross the 1 g/t classification "
        "threshold."
    )

    print(
        "The supplied-result mismatch must "
        "therefore be investigated elsewhere."
    )