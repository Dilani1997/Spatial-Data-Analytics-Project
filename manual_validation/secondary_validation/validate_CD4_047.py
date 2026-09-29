from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely.geometry import box


# ============================================================
# Paths / constants
# ============================================================

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "database"

SUPPLIED_RESULT = (
    ROOT
    / "geoquerybench_v0.1"
    / "gold_results"
    / "CD4-047.csv"
)

BBOX = (121.0, 122.0, -32.0, -30.5)

SOURCE_CRS = "EPSG:7844"
PROJECTED_CRS = "EPSG:7851"

CELL_SIZE = 10_000


print("=" * 70)
print("CD4-047 SECONDARY VALIDATION")
print("=" * 70)


# ============================================================
# 1. Load faults
# ============================================================

faults_all = gpd.read_parquet(
    DB / "B_surface" / "fault.parquet",
    columns=["geometry"],
)

print("\n" + "=" * 70)
print("1. SOURCE DATA")
print("=" * 70)

print("Total fault geometries:", len(faults_all))
print("Source CRS:", faults_all.crs)


# ============================================================
# 2. Reproduce the supplied gold method
# ============================================================

gold_faults = (
    faults_all
    .cx[
        BBOX[0]:BBOX[1],
        BBOX[2]:BBOX[3]
    ]
    .to_crs(PROJECTED_CRS)
    .copy()
)

gold_faults["length_m"] = (
    gold_faults.geometry.length
)

gold_faults["gx"] = (
    gold_faults.geometry.centroid.x
    // CELL_SIZE
).astype(int)

gold_faults["gy"] = (
    gold_faults.geometry.centroid.y
    // CELL_SIZE
).astype(int)

gold_res = (
    gold_faults
    .groupby(["gx", "gy"])
    .agg(
        n_segments=("length_m", "size"),
        total_length_m=("length_m", "sum"),
    )
    .reset_index()
)

gold_res["total_length_km"] = (
    gold_res["total_length_m"] / 1000
)

gold_res["cell_centre_e"] = (
    gold_res["gx"] * CELL_SIZE
    + CELL_SIZE / 2
)

gold_res["cell_centre_n"] = (
    gold_res["gy"] * CELL_SIZE
    + CELL_SIZE / 2
)

gold_top20 = (
    gold_res
    .sort_values(
        "total_length_km",
        ascending=False,
    )
    .head(20)
    .copy()
)

print("\n" + "=" * 70)
print("2. GOLD METHOD — CENTROID ASSIGNMENT")
print("=" * 70)

print("Selected fault geometries:", len(gold_faults))

print(
    "Total full fault length assigned:",
    round(
        gold_faults["length_m"].sum()
        / 1000,
        2,
    ),
    "km",
)

print("\nGold-method top 20:")

print(
    gold_top20[
        [
            "cell_centre_e",
            "cell_centre_n",
            "n_segments",
            "total_length_km",
        ]
    ]
    .round(
        {
            "total_length_km": 2,
        }
    )
    .to_string(index=False)
)


# ============================================================
# 3. Build exact Kalgoorlie bbox and project it
# ============================================================

bbox_geo = gpd.GeoDataFrame(
    {"name": ["Kalgoorlie box"]},
    geometry=[
        box(
            BBOX[0],
            BBOX[2],
            BBOX[1],
            BBOX[3],
        )
    ],
    crs=SOURCE_CRS,
)

bbox_proj = bbox_geo.to_crs(
    PROJECTED_CRS
)

bbox_geom = bbox_proj.geometry.iloc[0]

minx, miny, maxx, maxy = (
    bbox_geom.bounds
)

print("\n" + "=" * 70)
print("3. PROJECTED BBOX")
print("=" * 70)

print(
    "Projected bounds:",
    tuple(
        round(x, 2)
        for x in (
            minx,
            miny,
            maxx,
            maxy,
        )
    ),
)


# ============================================================
# 4. Clip faults to the actual Kalgoorlie bbox
# ============================================================

faults_proj = faults_all.to_crs(
    PROJECTED_CRS
)

faults_clip = gpd.clip(
    faults_proj,
    bbox_proj,
)

faults_clip = faults_clip[
    ~faults_clip.geometry.is_empty
].copy()

faults_clip["length_m"] = (
    faults_clip.geometry.length
)

gold_full_length_km = (
    gold_faults.geometry.length.sum()
    / 1000
)

clipped_length_km = (
    faults_clip.geometry.length.sum()
    / 1000
)

outside_length_km = (
    gold_full_length_km
    - clipped_length_km
)

print("\n" + "=" * 70)
print("4. BBOX CLIPPING CHECK")
print("=" * 70)

print(
    "Fault geometries after exact bbox clip:",
    len(faults_clip),
)

print(
    "Full selected geometry length:",
    round(
        gold_full_length_km,
        2,
    ),
    "km",
)

print(
    "Length actually inside bbox:",
    round(
        clipped_length_km,
        2,
    ),
    "km",
)

print(
    "Length outside bbox but included by gold method:",
    round(
        outside_length_km,
        2,
    ),
    "km",
)

if gold_full_length_km > 0:

    print(
        "Outside-length percentage:",
        round(
            100
            * outside_length_km
            / gold_full_length_km,
            2,
        ),
        "%",
    )


# ============================================================
# 5. Construct 10 km grid
#
# Important:
# Use the SAME 10 km origin implied by the gold code:
#
# gx = x // 10000
# gy = y // 10000
#
# This makes the comparison fair.
# ============================================================

gx_min = int(minx // CELL_SIZE)
gx_max = int(maxx // CELL_SIZE)

gy_min = int(miny // CELL_SIZE)
gy_max = int(maxy // CELL_SIZE)

grid_records = []

for gx in range(
    gx_min,
    gx_max + 1,
):

    for gy in range(
        gy_min,
        gy_max + 1,
    ):

        x0 = gx * CELL_SIZE
        y0 = gy * CELL_SIZE

        cell_geom = box(
            x0,
            y0,
            x0 + CELL_SIZE,
            y0 + CELL_SIZE,
        )

        # Only keep cells that intersect
        # the actual Kalgoorlie bbox.
        if not cell_geom.intersects(
            bbox_geom
        ):
            continue

        grid_records.append(
            {
                "gx": gx,
                "gy": gy,
                "geometry": cell_geom,
            }
        )

grid = gpd.GeoDataFrame(
    grid_records,
    geometry="geometry",
    crs=PROJECTED_CRS,
)

grid["cell_centre_e"] = (
    grid["gx"] * CELL_SIZE
    + CELL_SIZE / 2
)

grid["cell_centre_n"] = (
    grid["gy"] * CELL_SIZE
    + CELL_SIZE / 2
)

print("\n" + "=" * 70)
print("5. GRID")
print("=" * 70)

print(
    "10 km grid cells intersecting bbox:",
    len(grid),
)


# ============================================================
# 6. True per-cell fault length
#
# Intersect already-clipped faults with grid cells.
# This splits crossing faults at cell boundaries.
# ============================================================

fault_parts = gpd.overlay(
    faults_clip[
        ["geometry"]
    ],
    grid[
        [
            "gx",
            "gy",
            "cell_centre_e",
            "cell_centre_n",
            "geometry",
        ]
    ],
    how="intersection",
    keep_geom_type=False,
)

# Keep only linear pieces with positive length.
fault_parts["length_m"] = (
    fault_parts.geometry.length
)

fault_parts = fault_parts[
    fault_parts["length_m"] > 0
].copy()

true_res = (
    fault_parts
    .groupby(
        [
            "gx",
            "gy",
            "cell_centre_e",
            "cell_centre_n",
        ]
    )
    .agg(
        n_parts=("length_m", "size"),
        total_length_m=("length_m", "sum"),
    )
    .reset_index()
)

true_res["total_length_km"] = (
    true_res["total_length_m"]
    / 1000
)

true_top20 = (
    true_res
    .sort_values(
        "total_length_km",
        ascending=False,
    )
    .head(20)
    .copy()
)

print("\n" + "=" * 70)
print("6. TRUE GRID-INTERSECTION METHOD")
print("=" * 70)

print(
    "Fault pieces after grid intersection:",
    len(fault_parts),
)

print(
    "Total length across all grid cells:",
    round(
        true_res["total_length_km"].sum(),
        2,
    ),
    "km",
)

print("\nTrue-intersection top 20:")

print(
    true_top20[
        [
            "cell_centre_e",
            "cell_centre_n",
            "n_parts",
            "total_length_km",
        ]
    ]
    .round(
        {
            "total_length_km": 2,
        }
    )
    .to_string(index=False)
)


# ============================================================
# 7. Compare cell totals directly
# ============================================================

comparison = (
    gold_res[
        [
            "gx",
            "gy",
            "total_length_km",
        ]
    ]
    .rename(
        columns={
            "total_length_km":
                "gold_centroid_km"
        }
    )
    .merge(
        true_res[
            [
                "gx",
                "gy",
                "total_length_km",
            ]
        ].rename(
            columns={
                "total_length_km":
                    "true_intersection_km"
            }
        ),
        on=["gx", "gy"],
        how="outer",
    )
    .fillna(0)
)

comparison["difference_km"] = (
    comparison["gold_centroid_km"]
    - comparison["true_intersection_km"]
)

comparison["abs_difference_km"] = (
    comparison["difference_km"].abs()
)

comparison["cell_centre_e"] = (
    comparison["gx"]
    * CELL_SIZE
    + CELL_SIZE / 2
)

comparison["cell_centre_n"] = (
    comparison["gy"]
    * CELL_SIZE
    + CELL_SIZE / 2
)

comparison = (
    comparison
    .sort_values(
        "abs_difference_km",
        ascending=False,
    )
)

print("\n" + "=" * 70)
print("7. LARGEST CELL-LEVEL DIFFERENCES")
print("=" * 70)

print(
    comparison[
        [
            "cell_centre_e",
            "cell_centre_n",
            "gold_centroid_km",
            "true_intersection_km",
            "difference_km",
        ]
    ]
    .head(20)
    .round(2)
    .to_string(index=False)
)


# ============================================================
# 8. Compare top-20 membership
# ============================================================

gold_cells = set(
    zip(
        gold_top20["gx"],
        gold_top20["gy"],
    )
)

true_cells = set(
    zip(
        true_top20["gx"],
        true_top20["gy"],
    )
)

common_cells = (
    gold_cells
    & true_cells
)

gold_only = (
    gold_cells
    - true_cells
)

true_only = (
    true_cells
    - gold_cells
)

print("\n" + "=" * 70)
print("8. TOP-20 MEMBERSHIP COMPARISON")
print("=" * 70)

print(
    "Common top-20 cells:",
    len(common_cells),
)

print(
    "Gold-only top-20 cells:",
    len(gold_only),
)

print(
    "True-method-only top-20 cells:",
    len(true_only),
)

if gold_only:

    print(
        "\nGold-only cells:",
        sorted(gold_only),
    )

if true_only:

    print(
        "\nTrue-method-only cells:",
        sorted(true_only),
    )


# ============================================================
# 9. Overall numerical difference
# ============================================================

n_diff = int(
    (
        comparison[
            "abs_difference_km"
        ] > 0.01
    ).sum()
)

max_abs_diff = float(
    comparison[
        "abs_difference_km"
    ].max()
)

mean_abs_diff = float(
    comparison[
        "abs_difference_km"
    ].mean()
)

print("\n" + "=" * 70)
print("9. NUMERICAL DIFFERENCE SUMMARY")
print("=" * 70)

print(
    "Cells differing by >0.01 km:",
    n_diff,
)

print(
    "Maximum absolute cell difference:",
    round(
        max_abs_diff,
        2,
    ),
    "km",
)

print(
    "Mean absolute cell difference:",
    round(
        mean_abs_diff,
        2,
    ),
    "km",
)


# ============================================================
# 10. Supplied result
# ============================================================

print("\n" + "=" * 70)
print("10. SUPPLIED RESULT")
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
# 11. Diagnostic conclusion
# ============================================================

print("\n" + "=" * 70)
print("11. SECONDARY VALIDATION SUMMARY")
print("=" * 70)

if (
    len(gold_only) > 0
    or max_abs_diff > 1.0
):

    print(
        "⚠️ MATERIAL DIFFERENCE FOUND."
    )

    print(
        "Assigning each complete fault geometry "
        "to the cell containing its centroid does "
        "not reproduce actual fault length within "
        "each 10 km grid cell."
    )

    if outside_length_km > 0.01:

        print(
            "\nThe gold method also includes "
            "fault length lying outside the "
            "Kalgoorlie bounding box because "
            "intersecting geometries are selected "
            "but not clipped to the box."
        )

    print(
        "\nThe benchmark answer should be reviewed "
        "against a true grid-intersection / "
        "clipping calculation."
    )

else:

    print(
        "The centroid-assignment approximation "
        "produces only small differences for the "
        "current frozen dataset."
    )

    print(
        "Consider recording the methodological "
        "approximation as a review note."
    )