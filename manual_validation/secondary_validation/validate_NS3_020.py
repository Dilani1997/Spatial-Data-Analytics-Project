from pathlib import Path

import pandas as pd
import geopandas as gpd


ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "database"

TARGET = "WIDGIEMOOLTHA"


print("=" * 70)
print("NS3-020 SECONDARY VALIDATION")
print("=" * 70)


# ------------------------------------------------------------
# Load data
# ------------------------------------------------------------

sheets = gpd.read_parquet(
    DB / "B_surface" / "map_sheet.parquet",
    columns=["name", "geometry"],
).to_crs(9473)

samples = pd.read_parquet(
    DB / "B_surface" / "surface_sample.parquet",
    columns=["uid", "longitude", "latitude"],
)

g = gpd.GeoDataFrame(
    samples,
    geometry=gpd.points_from_xy(
        samples.longitude,
        samples.latitude,
    ),
    crs="EPSG:7844",
).to_crs(9473)


print("\nMap-sheet polygons:", len(sheets))
print("Distinct sheet names:", sheets["name"].nunique())
print("Surface samples:", len(g))


# ------------------------------------------------------------
# 1. Reproduce current join
# ------------------------------------------------------------

hit = gpd.sjoin(
    g[["uid", "geometry"]],
    sheets[["name", "geometry"]],
    predicate="within",
)

print("\n" + "=" * 70)
print("1. WITHIN JOIN")
print("=" * 70)

print("Join rows:", len(hit))
print("Distinct matched samples:", hit["uid"].nunique())

multi = (
    hit.groupby("uid")
       .agg(
           n_matches=("name", "size"),
           n_sheet_names=("name", "nunique"),
       )
)

multi = multi[
    multi["n_sheet_names"] > 1
]

print(
    "Samples matching >1 distinct sheet:",
    len(multi),
)


# ------------------------------------------------------------
# 2. Check WIDGIEMOOLTHA directly
# ------------------------------------------------------------

target = sheets[
    sheets["name"] == TARGET
].copy()

print("\n" + "=" * 70)
print("2. WIDGIEMOOLTHA")
print("=" * 70)

print("Polygons with this name:", len(target))

# Dissolve in case a named sheet has multiple polygons.
target_dissolved = target.dissolve(by="name").reset_index()

within_target = gpd.sjoin(
    g[["uid", "geometry"]],
    target_dissolved[["name", "geometry"]],
    predicate="within",
)

intersects_target = gpd.sjoin(
    g[["uid", "geometry"]],
    target_dissolved[["name", "geometry"]],
    predicate="intersects",
)

print(
    "Distinct samples WITHIN WIDGIEMOOLTHA:",
    within_target["uid"].nunique(),
)

print(
    "Distinct samples INTERSECTING WIDGIEMOOLTHA:",
    intersects_target["uid"].nunique(),
)

boundary_only = (
    set(intersects_target["uid"])
    - set(within_target["uid"])
)

print(
    "Boundary-only samples:",
    len(boundary_only),
)


# ------------------------------------------------------------
# 3. Compare direct count with gold drop_duplicates method
# ------------------------------------------------------------

gold_like = (
    hit.drop_duplicates("uid")
       .groupby("name")
       .size()
)

gold_like_count = int(
    gold_like.get(TARGET, 0)
)

direct_count = int(
    within_target["uid"].nunique()
)

print("\n" + "=" * 70)
print("3. ASSIGNMENT COMPARISON")
print("=" * 70)

print(
    "Gold-like count after global drop_duplicates(uid):",
    gold_like_count,
)

print(
    "Direct distinct WITHIN count:",
    direct_count,
)

print(
    "Difference:",
    direct_count - gold_like_count,
)


# ------------------------------------------------------------
# 4. Find WIDGIEMOOLTHA samples also matched to other sheets
# ------------------------------------------------------------

target_uids = set(
    hit.loc[
        hit["name"] == TARGET,
        "uid",
    ]
)

target_multi = hit[
    hit["uid"].isin(target_uids)
].groupby("uid").agg(
    n_rows=("name", "size"),
    n_names=("name", "nunique"),
    names=("name", lambda x: sorted(set(x))),
)

target_multi = target_multi[
    target_multi["n_names"] > 1
]

print("\n" + "=" * 70)
print("4. OVERLAPPING-SHEET CHECK")
print("=" * 70)

print(
    "WIDGIEMOOLTHA samples also within another sheet:",
    len(target_multi),
)

if len(target_multi):

    print("\nExamples:")

    print(
        target_multi.head(20).to_string()
    )


# ------------------------------------------------------------
# 5. Check duplicate polygons / names
# ------------------------------------------------------------

sheet_name_counts = (
    sheets.groupby("name")
          .size()
          .sort_values(ascending=False)
)

print("\n" + "=" * 70)
print("5. MAP-SHEET GEOMETRY STRUCTURE")
print("=" * 70)

print(
    "Names represented by >1 polygon:",
    int((sheet_name_counts > 1).sum()),
)

print(
    "WIDGIEMOOLTHA polygon count:",
    int(sheet_name_counts.get(TARGET, 0)),
)


# ------------------------------------------------------------
# 6. Check all top-sheet counts using a safer method
#
# Count distinct uid within each sheet name rather than globally
# dropping uid before grouping.
# ------------------------------------------------------------

safe_counts = (
    hit.groupby("name")["uid"]
       .nunique()
       .rename("safe_n_samples")
)

gold_counts = (
    hit.drop_duplicates("uid")
       .groupby("name")
       .size()
       .rename("gold_n_samples")
)

compare = pd.concat(
    [gold_counts, safe_counts],
    axis=1,
).fillna(0)

compare["difference"] = (
    compare["safe_n_samples"]
    - compare["gold_n_samples"]
)

changed = compare[
    compare["difference"] != 0
].sort_values(
    "difference",
    ascending=False,
)

print("\n" + "=" * 70)
print("6. GLOBAL DROP_DUPLICATES EFFECT")
print("=" * 70)

print(
    "Sheet names whose counts change:",
    len(changed),
)

if len(changed):

    print(
        changed.head(30).to_string()
    )


print("\n" + "=" * 70)
print("7. INTERPRETATION")
print("=" * 70)

if len(multi) > 0:

    print(
        "Multi-sheet sample matches exist. "
        "The global drop_duplicates('uid') step can therefore "
        "make sheet assignment depend on join row ordering."
    )

else:

    print(
        "No sample is within more than one distinct map sheet; "
        "global drop_duplicates('uid') does not affect sheet assignment."
    )

if len(boundary_only) > 0:

    print(
        f"{len(boundary_only)} sample(s) intersect WIDGIEMOOLTHA "
        "but are not strictly within it, indicating boundary cases."
    )

print(
    "\nSupplied WIDGIEMOOLTHA count: 409277"
)

print(
    "Current rerun WIDGIEMOOLTHA count: 409281"
)