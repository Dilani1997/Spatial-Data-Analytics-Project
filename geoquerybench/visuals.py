"""Interactive query-output explorer. Owner: Thomas."""

from pathlib import Path
import mimetypes

import pandas as pd
import streamlit as st

from .review_visuals import (
    category_columns,
    column_profile,
    commodity_metric_columns,
    coordinate_columns,
    correlation_long,
    friendly_metric,
    numeric_columns,
    parse_result_evidence,
    prepare_pie_data,
)


def render_result_explorer(filename, mime, blob, key_prefix="result"):
    """Render an uploaded query result as an interactive, display-only explorer."""
    if not blob:
        st.info(
            "No output file is available yet. Run the client-supplied query in the approved "
            "environment, then upload its CSV, JSON/GeoJSON, PNG/JPG or text result here."
        )
        return
    filename = filename or "query-result"
    st.caption(
        f"Verified query output: {filename} · {len(blob) / 1024:.1f} KB · "
        "displayed only; no uploaded query or code is executed"
    )
    try:
        if mime and mime.startswith("image/"):
            st.image(blob, caption=filename, width="stretch")
        elif str(filename).lower().endswith((".csv", ".json", ".geojson")):
            frame, payload = parse_result_evidence(filename, blob)
            if frame.empty:
                st.warning("The result file was read successfully but contains no tabular records.")
                if payload is not None:
                    with st.expander("View structured result"):
                        st.json(payload, expanded=False)
                return

            palette = ["#0c8ed9", "#7657ff", "#08c4d8", "#ffb627", "#e88a5b", "#94a3b8"]
            controls_left, controls_middle, controls_right = st.columns([1.1, 1.1, 1])
            metric_columns = commodity_metric_columns(frame) or numeric_columns(frame)
            chosen_metric = None
            with controls_left:
                if metric_columns:
                    chosen_metric = st.selectbox(
                        "⛏️ Gold, copper or numeric measure",
                        metric_columns,
                        format_func=friendly_metric,
                        key=f"{key_prefix}_metric",
                    )
                else:
                    st.caption("No numeric commodity measure was detected.")

            filtered_frame = frame.copy()
            category_options = category_columns(frame)
            with controls_middle:
                selected_category = st.selectbox(
                    "🧩 Optional category filter",
                    ["None"] + category_options,
                    key=f"{key_prefix}_category",
                )
            if selected_category != "None":
                values = sorted(frame[selected_category].dropna().astype(str).unique().tolist())
                selected_values = st.multiselect(
                    f"Values in {selected_category}", values, default=values,
                    key=f"{key_prefix}_category_values",
                )
                filtered_frame = filtered_frame[
                    filtered_frame[selected_category].astype(str).isin(selected_values)
                ]

            if chosen_metric:
                metric_values = pd.to_numeric(frame[chosen_metric], errors="coerce").dropna()
                if not metric_values.empty:
                    low, high = float(metric_values.min()), float(metric_values.max())
                    if low < high:
                        chosen_range = st.slider(
                            f"Filter {friendly_metric(chosen_metric)}",
                            min_value=low,
                            max_value=high,
                            value=(low, high),
                            key=f"{key_prefix}_range",
                        )
                        numeric_values = pd.to_numeric(
                            filtered_frame[chosen_metric], errors="coerce"
                        )
                        filtered_frame = filtered_frame[
                            numeric_values.between(chosen_range[0], chosen_range[1], inclusive="both")
                        ]

            latitude, longitude = coordinate_columns(filtered_frame)
            chart_options = ["Table"]
            if category_options or chosen_metric:
                chart_options.append("Bar chart")
            if category_options:
                chart_options.append("Pie / donut")
            if chosen_metric:
                chart_options.extend(["Line chart", "Histogram", "Box plot"])
            numeric = numeric_columns(filtered_frame)
            if len(numeric) >= 2:
                chart_options.extend(["Scatter plot", "Correlation heatmap"])
            if latitude and longitude:
                chart_options.append("Map")
            with controls_right:
                chart_mode = st.selectbox(
                    "📊 Output view", chart_options,
                    key=f"{key_prefix}_chart_mode",
                )

            result_metrics = st.columns(4)
            result_metrics[0].metric("Rows shown", f"{len(filtered_frame):,}")
            result_metrics[1].metric("Columns", f"{len(filtered_frame.columns):,}")
            missing_cells = int(filtered_frame.isna().sum().sum())
            result_metrics[2].metric("Missing cells", f"{missing_cells:,}")
            if chosen_metric and not filtered_frame.empty:
                values = pd.to_numeric(filtered_frame[chosen_metric], errors="coerce")
                result_metrics[3].metric(
                    f"Average {chosen_metric}",
                    f"{values.mean():,.3g}" if values.notna().any() else "—",
                )
            else:
                result_metrics[3].metric(
                    "Mapped points", f"{len(filtered_frame):,}" if latitude else "—"
                )

            if chart_mode == "Map" and latitude and longitude:
                map_frame = filtered_frame[[latitude, longitude]].copy()
                map_frame.columns = ["latitude", "longitude"]
                map_frame["latitude"] = pd.to_numeric(map_frame["latitude"], errors="coerce")
                map_frame["longitude"] = pd.to_numeric(map_frame["longitude"], errors="coerce")
                map_frame = map_frame.dropna()
                if map_frame.empty:
                    st.info("No valid latitude/longitude pairs remain after filtering.")
                else:
                    st.caption(f"Point map · {len(map_frame):,} valid coordinates")
                    st.map(map_frame)
            elif chart_mode == "Bar chart":
                categories = category_columns(filtered_frame)
                if categories:
                    bar_left, bar_right = st.columns(2)
                    with bar_left:
                        group_column = st.selectbox(
                            "Group bars by", categories, key=f"{key_prefix}_bar_group"
                        )
                    bar_aggregations = ["Count rows"]
                    if chosen_metric:
                        bar_aggregations.extend(["Mean selected measure", "Sum selected measure"])
                    with bar_right:
                        bar_aggregation = st.selectbox(
                            "Bar value", bar_aggregations, key=f"{key_prefix}_bar_aggregation"
                        )
                    bar_working = filtered_frame.copy()
                    bar_working[group_column] = (
                        bar_working[group_column].fillna("Missing").astype(str)
                    )
                    if bar_aggregation == "Count rows":
                        chart_frame = (
                            bar_working.groupby(group_column).size().rename("Value").reset_index()
                        )
                        value_title = "Rows"
                    else:
                        bar_working["Value"] = pd.to_numeric(
                            bar_working[chosen_metric], errors="coerce"
                        )
                        reducer = "mean" if bar_aggregation.startswith("Mean") else "sum"
                        chart_frame = (
                            bar_working.groupby(group_column)["Value"]
                            .agg(reducer).dropna().reset_index()
                        )
                        value_title = f"{bar_aggregation.split()[0]} {chosen_metric}"
                    chart_frame = chart_frame.sort_values("Value", ascending=False).head(30)
                    st.caption("Ranked comparison · top 30 categories after filtering")
                    st.vega_lite_chart(
                        chart_frame,
                        {
                            "mark": {"type": "bar", "cornerRadiusEnd": 4, "color": palette[0]},
                            "encoding": {
                                "y": {
                                    "field": group_column,
                                    "type": "nominal",
                                    "sort": "-x",
                                    "title": group_column,
                                },
                                "x": {"field": "Value", "type": "quantitative", "title": value_title},
                                "tooltip": [
                                    {"field": group_column, "type": "nominal"},
                                    {"field": "Value", "type": "quantitative", "format": ",.3g"},
                                ],
                            },
                            "height": max(240, min(620, 26 * len(chart_frame))),
                        },
                        width="stretch",
                    )
                elif chosen_metric:
                    chart_frame = pd.DataFrame(
                        {
                            "Row": range(1, min(len(filtered_frame), 100) + 1),
                            "Value": pd.to_numeric(
                                filtered_frame[chosen_metric], errors="coerce"
                            ).head(100),
                        }
                    ).dropna()
                    st.vega_lite_chart(
                        chart_frame,
                        {
                            "mark": {"type": "bar", "color": palette[0]},
                            "encoding": {
                                "x": {"field": "Row", "type": "ordinal", "title": "Row order"},
                                "y": {"field": "Value", "type": "quantitative", "title": chosen_metric},
                                "tooltip": [
                                    {"field": "Row", "type": "ordinal"},
                                    {"field": "Value", "type": "quantitative", "format": ",.3g"},
                                ],
                            },
                        },
                        width="stretch",
                    )
                else:
                    st.info("This result needs a category or numeric field for a bar chart.")
            elif chart_mode == "Pie / donut" and category_options:
                pie_left, pie_middle, pie_right = st.columns([1.2, 1.1, 0.8])
                with pie_left:
                    pie_category = st.selectbox(
                        "Slice by", category_options, key=f"{key_prefix}_pie_category"
                    )
                pie_aggregations = ["Count rows"]
                if chosen_metric:
                    pie_aggregations.append("Sum selected measure")
                with pie_middle:
                    pie_aggregation = st.selectbox(
                        "Slice value", pie_aggregations, key=f"{key_prefix}_pie_aggregation"
                    )
                with pie_right:
                    maximum_slices = st.slider(
                        "Top slices", 3, 8, 5, key=f"{key_prefix}_pie_slices"
                    )
                pie_frame = prepare_pie_data(
                    filtered_frame,
                    pie_category,
                    chosen_metric,
                    pie_aggregation,
                    maximum_slices,
                )
                if pie_frame.empty:
                    st.info("No positive values are available for this part-to-whole view.")
                else:
                    st.caption("Part-to-whole view · smaller categories are combined as Other")
                    st.vega_lite_chart(
                        pie_frame,
                        {
                            "mark": {"type": "arc", "innerRadius": 58, "outerRadius": 112},
                            "encoding": {
                                "theta": {"field": "Value", "type": "quantitative", "stack": True},
                                "color": {
                                    "field": "Category",
                                    "type": "nominal",
                                    "scale": {"range": palette},
                                    "legend": {"orient": "bottom", "columns": 3},
                                },
                                "tooltip": [
                                    {"field": "Category", "type": "nominal"},
                                    {"field": "Value", "type": "quantitative", "format": ",.3g"},
                                ],
                            },
                            "height": 340,
                        },
                        width="stretch",
                    )
            elif chart_mode == "Line chart" and chosen_metric:
                line_x_options = ["Row order"] + [column for column in numeric if column != chosen_metric]
                line_x = st.selectbox(
                    "Horizontal axis", line_x_options, key=f"{key_prefix}_line_x"
                )
                line_frame = pd.DataFrame(
                    {
                        "X": (
                            range(1, len(filtered_frame) + 1)
                            if line_x == "Row order"
                            else pd.to_numeric(filtered_frame[line_x], errors="coerce")
                        ),
                        "Value": pd.to_numeric(filtered_frame[chosen_metric], errors="coerce"),
                    }
                ).dropna().head(1000).sort_values("X")
                st.caption("Trend view · first 1,000 complete records after filtering")
                st.vega_lite_chart(
                    line_frame,
                    {
                        "mark": {
                            "type": "line",
                            "color": palette[1],
                            "strokeWidth": 2.5,
                            "point": len(line_frame) <= 150,
                        },
                        "encoding": {
                            "x": {"field": "X", "type": "quantitative", "title": line_x},
                            "y": {"field": "Value", "type": "quantitative", "title": chosen_metric},
                            "tooltip": [
                                {"field": "X", "type": "quantitative", "format": ",.3g"},
                                {"field": "Value", "type": "quantitative", "format": ",.3g"},
                            ],
                        },
                        "height": 360,
                    },
                    width="stretch",
                )
            elif chart_mode == "Histogram" and chosen_metric:
                bins = st.slider("Histogram bins", 5, 50, 20, key=f"{key_prefix}_hist_bins")
                histogram_frame = pd.DataFrame(
                    {"Value": pd.to_numeric(filtered_frame[chosen_metric], errors="coerce")}
                ).dropna()
                if histogram_frame.empty:
                    st.info("No numeric values remain for this distribution.")
                else:
                    st.caption(
                        f"Distribution of {friendly_metric(chosen_metric)} · "
                        f"{len(histogram_frame):,} non-missing values"
                    )
                    st.vega_lite_chart(
                        histogram_frame,
                        {
                            "mark": {"type": "bar", "color": palette[2], "cornerRadiusEnd": 2},
                            "encoding": {
                                "x": {
                                    "bin": {"maxbins": bins},
                                    "field": "Value",
                                    "type": "quantitative",
                                    "title": chosen_metric,
                                },
                                "y": {"aggregate": "count", "title": "Records"},
                                "tooltip": [{"aggregate": "count", "type": "quantitative", "title": "Records"}],
                            },
                            "height": 360,
                        },
                        width="stretch",
                    )
            elif chart_mode == "Box plot" and chosen_metric:
                box_categories = category_columns(filtered_frame, maximum_unique=20)
                box_group = st.selectbox(
                    "Compare groups",
                    ["All records"] + box_categories,
                    key=f"{key_prefix}_box_group",
                )
                box_frame = pd.DataFrame(
                    {
                        "Group": (
                            "All records"
                            if box_group == "All records"
                            else filtered_frame[box_group].fillna("Missing").astype(str)
                        ),
                        "Value": pd.to_numeric(filtered_frame[chosen_metric], errors="coerce"),
                    }
                ).dropna()
                if box_frame.empty:
                    st.info("No numeric values remain for this spread comparison.")
                else:
                    st.caption("Spread and outliers · box shows the middle 50% of values")
                    st.vega_lite_chart(
                        box_frame,
                        {
                            "mark": {"type": "boxplot", "extent": 1.5, "color": palette[1]},
                            "encoding": {
                                "x": {
                                    "field": "Group",
                                    "type": "nominal",
                                    "title": box_group,
                                    "sort": "-y",
                                    "axis": {"labelAngle": -25},
                                },
                                "y": {"field": "Value", "type": "quantitative", "title": chosen_metric},
                            },
                            "height": 380,
                        },
                        width="stretch",
                    )
            elif chart_mode == "Scatter plot" and len(numeric) >= 2:
                scatter_x, scatter_y, scatter_color = st.columns(3)
                with scatter_x:
                    x_column = st.selectbox(
                        "X axis", numeric, key=f"{key_prefix}_scatter_x"
                    )
                with scatter_y:
                    y_default = 1 if len(numeric) > 1 else 0
                    y_column = st.selectbox(
                        "Y axis", numeric, index=y_default,
                        key=f"{key_prefix}_scatter_y",
                    )
                scatter_categories = category_columns(filtered_frame, maximum_unique=20)
                with scatter_color:
                    color_column = st.selectbox(
                        "Colour groups",
                        ["None"] + scatter_categories,
                        key=f"{key_prefix}_scatter_color",
                    )
                scatter_frame = pd.DataFrame(
                    {
                        "X": pd.to_numeric(filtered_frame[x_column], errors="coerce"),
                        "Y": pd.to_numeric(filtered_frame[y_column], errors="coerce"),
                        "Group": (
                            "All records"
                            if color_column == "None"
                            else filtered_frame[color_column].fillna("Missing").astype(str)
                        ),
                    }
                ).dropna(subset=["X", "Y"])
                if len(scatter_frame) < 8:
                    st.warning(
                        "Only a few complete pairs remain. A scatter plot could overstate a pattern, "
                        "so the underlying values are shown instead."
                    )
                    st.dataframe(scatter_frame, width="stretch", hide_index=True)
                else:
                    st.caption(
                        f"Relationship view · {len(scatter_frame):,} complete pairs; "
                        "look for clusters, outliers and non-linear patterns"
                    )
                    color_encoding = (
                        {
                            "field": "Group",
                            "type": "nominal",
                            "scale": {"range": palette},
                            "legend": {"orient": "bottom"},
                        }
                        if color_column != "None"
                        else {"value": palette[0]}
                    )
                    st.vega_lite_chart(
                        scatter_frame,
                        {
                            "mark": {"type": "circle", "size": 82, "opacity": 0.72},
                            "encoding": {
                                "x": {"field": "X", "type": "quantitative", "title": x_column, "scale": {"zero": False}},
                                "y": {"field": "Y", "type": "quantitative", "title": y_column, "scale": {"zero": False}},
                                "color": color_encoding,
                                "tooltip": [
                                    {"field": "X", "type": "quantitative", "title": x_column, "format": ",.4g"},
                                    {"field": "Y", "type": "quantitative", "title": y_column, "format": ",.4g"},
                                    {"field": "Group", "type": "nominal"},
                                ],
                            },
                            "height": 410,
                        },
                        width="stretch",
                    )
            elif chart_mode == "Correlation heatmap" and len(numeric) >= 2:
                correlation_frame = correlation_long(filtered_frame, maximum_columns=8)
                if correlation_frame.empty:
                    st.info(
                        "At least two numeric measures with three or more usable values are needed "
                        "for a correlation heatmap."
                    )
                else:
                    st.caption(
                        "Linear association from −1 to +1 · correlation is exploratory and does not prove causation"
                    )
                    st.vega_lite_chart(
                        correlation_frame,
                        {
                            "layer": [
                                {
                                    "mark": {"type": "rect", "cornerRadius": 3},
                                    "encoding": {
                                        "x": {"field": "Measure X", "type": "nominal", "axis": {"labelAngle": -30}, "title": None},
                                        "y": {"field": "Measure Y", "type": "nominal", "title": None},
                                        "color": {
                                            "field": "Correlation",
                                            "type": "quantitative",
                                            "scale": {
                                                "domain": [-1, 0, 1],
                                                "range": ["#e88a5b", "#f8fafc", "#0c8ed9"],
                                            },
                                            "legend": {"title": "Correlation"},
                                        },
                                        "tooltip": [
                                            {"field": "Measure X", "type": "nominal"},
                                            {"field": "Measure Y", "type": "nominal"},
                                            {"field": "Correlation", "type": "quantitative", "format": ".2f"},
                                        ],
                                    },
                                },
                                {
                                    "mark": {"type": "text", "fontSize": 12},
                                    "encoding": {
                                        "x": {"field": "Measure X", "type": "nominal"},
                                        "y": {"field": "Measure Y", "type": "nominal"},
                                        "text": {"field": "Correlation", "type": "quantitative", "format": ".2f"},
                                        "color": {
                                            "condition": {"test": "abs(datum.Correlation) > 0.55", "value": "white"},
                                            "value": "#172033",
                                        },
                                    },
                                },
                            ],
                            "height": 430,
                        },
                        width="stretch",
                    )
            else:
                st.dataframe(filtered_frame, width="stretch", hide_index=True)

            with st.expander("🔎 Data profile and summary"):
                st.caption(
                    "Use this profile to spot missing values, low-cardinality fields and suspicious ranges "
                    "before accepting a visual conclusion."
                )
                st.dataframe(column_profile(filtered_frame), width="stretch", hide_index=True)

            if payload is not None:
                with st.expander("View structured JSON / GeoJSON"):
                    st.json(payload, expanded=False)
        else:
            text = blob.decode("utf-8", errors="replace")
            st.code(text[:10000], language="text")
            if len(text) > 10000:
                st.caption("Preview truncated to the first 10,000 characters.")
    except Exception as error:
        st.warning(f"The file was saved, but its preview could not be rendered: {error}")

def render_evidence(filename, mime, blob):
    """Backward-compatible wrapper used by stored-review previews."""
    render_result_explorer(filename, mime, blob, key_prefix="stored_result")


# --- Expanded result preview safety (2026-09 update) ---
SUPPORTED_RESULT_EXTENSIONS = frozenset({".csv", ".txt", ".json", ".geojson", ".png", ".jpg", ".jpeg"})
MAX_RESULT_PREVIEW_BYTES = 10 * 1024 * 1024


def validate_result_blob(filename, blob, maximum_bytes=MAX_RESULT_PREVIEW_BYTES):
    """Validate one display-only result payload before Streamlit renders it."""
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in SUPPORTED_RESULT_EXTENSIONS:
        raise ValueError("Unsupported result file type.")
    if not blob:
        raise ValueError("Result file is empty.")
    if len(blob) > int(maximum_bytes):
        raise ValueError("Result file exceeds the 10 MB preview limit.")
    return suffix


def render_expanded_result(path_or_bytes, filename, key_prefix="expanded_result"):
    """Render the same safe result types used by the current expanded workspace."""
    raw = path_or_bytes.read_bytes() if isinstance(path_or_bytes, Path) else bytes(path_or_bytes)
    suffix = validate_result_blob(filename, raw)
    if suffix in {".png", ".jpg", ".jpeg"}:
        st.image(raw, caption=filename, width="stretch")
        return
    mime = mimetypes.guess_type(str(filename))[0] or "application/octet-stream"
    render_result_explorer(filename, mime, raw, key_prefix=key_prefix)
