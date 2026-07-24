import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import BytesIO

# ----------------------------- Helpers -----------------------------------

@st.cache_data
def load_excel(file, sheet_name,headerrow):
    return pd.read_excel(file, sheet_name=sheet_name, header=headerrow-1, engine="openpyxl")

@st.cache_data
def get_sheet_names(file):
    xls = pd.ExcelFile(file, engine="openpyxl")
    return xls.sheet_names

def detect_column_types(df, date_success_threshold=0.8):
    """Classify each column as numeric, date, categorical, or text."""
    col_types = {}
    for col in df.columns:
        series = df[col]

        if pd.api.types.is_datetime64_any_dtype(series):
            col_types[col] = "date"
            continue

        if pd.api.types.is_numeric_dtype(series):
            col_types[col] = "numeric"
            continue

        # Try parsing non-numeric, non-datetime columns as dates.
        # (Deliberately not gated on dtype == object: pandas can load text
        # columns as a dedicated "str" dtype, not classic "object".)
        sample = series.dropna().astype(str)
        if len(sample) > 0:
            sample = sample.sample(min(50, len(sample)), random_state=1).reset_index(drop=True)
            try:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
            except ValueError:
                # pandas' format="mixed" can raise "cannot assemble with duplicate keys"
                # when the sample contains duplicate numeric-like values that it tries
                # to interpret as time units. In this case, treat as non-date.
                parsed = pd.Series([pd.NaT] * len(sample))
            success_rate = parsed.notna().mean()
            if success_rate >= date_success_threshold:
                col_types[col] = "date"
                continue

        # Categorical vs free text based on cardinality
        nunique = series.nunique(dropna=True)
        if nunique <= max(50, int(0.5 * len(series))):
            col_types[col] = "categorical"
        else:
            col_types[col] = "text"

    return col_types

def coerce_dates(df, col_types, min_year=1900, max_year=2100):
    """Convert columns detected/overridden as date (but not yet datetime) into datetime.
    Tries format='mixed' first, then falls back to dayfirst parsing if that parses poorly.
    Any parsed date outside [min_year, max_year] is treated as invalid (set to NaT) —
    this catches mis-parsed ambiguous values (e.g. a stray '1-5-25' becoming year 0001)
    that would otherwise crash Streamlit's date_input widget."""
    def _sane(parsed):
        # pd.to_datetime can return Series, DatetimeIndex, or Index — 
        # convert to Series for uniform dt accessor handling
        if not isinstance(parsed, pd.Series):
            parsed = pd.Series(parsed)
        return parsed.where(parsed.dt.year.between(min_year, max_year))

    for col, t in col_types.items():
        if t == "date" and not pd.api.types.is_datetime64_any_dtype(df[col]):
            try:
                parsed = _sane(pd.to_datetime(df[col].to_numpy(), errors="coerce", format="mixed"))
            except ValueError:
                parsed = _sane(pd.to_datetime(df[col].to_numpy(), errors="coerce", dayfirst=True))
            if parsed.notna().mean() < 0.5:
                try:
                    alt = _sane(pd.to_datetime(df[col].to_numpy(), errors="coerce", dayfirst=True))
                except ValueError:
                    alt = parsed
                if alt.notna().mean() > parsed.notna().mean():
                    parsed = alt
            df[col] = parsed
    return df

def coerce_numeric(df, col_types):
    """Convert columns overridden to numeric (but stored as object) into numeric dtype."""
    for col, t in col_types.items():
        if t == "numeric" and not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def sanitize_date_columns(df, date_cols, min_year=1900, max_year=2100):
    """Set any out-of-range datetime value to NaT, regardless of whether the column
    was natively datetime or converted. Protects against corrupt values (e.g. Excel
    date-serial glitches) that would otherwise crash Streamlit's date_input widget."""
    for col in date_cols:
        if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].where(df[col].dt.year.between(min_year, max_year))
    return df

def to_excel_bytes(df):
    output = BytesIO()
    df = df.copy()
    # Flatten MultiIndex columns (can happen with pivot tables) so Excel export works
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ["_".join(str(x) for x in tup if str(x) != "").strip("_") for tup in df.columns]
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
    return output.getvalue()

def cols_by_type(col_types, wanted):
    if isinstance(wanted, str):
        wanted = [wanted]
    return [c for c, t in col_types.items() if t in wanted]

# ----------------------------- Sidebar: Upload -----------------------------

st.sidebar.title("📁 Data Source")
uploaded_file = st.sidebar.file_uploader("Upload an Excel file", type=["xlsx", "xls"],key="file_uploader", help="Upload an Excel file to explore its data. Only .xlsx formats are supported.")

if uploaded_file is None:
    #st.title("📊 Excel Data Explorer")
    st.info("Upload an Excel file from the sidebar to get started.")
    #st.stop()
else:
    sheet_names = get_sheet_names(uploaded_file)
    sheet = sheet_names[0]
    if len(sheet_names) > 1:
        sheet = st.sidebar.selectbox("Select Sheet", sheet_names)
    headerrow= st.sidebar.number_input("Select Header Row",key=f"headerrow_{sheet}",min_value=1,max_value=999,value=1,help="Row number containing the column headers")

    df_raw = load_excel(uploaded_file, sheet,headerrow).copy()
    # Strip whitespace and deduplicate column names to avoid duplicate-key issues
    seen = {}
    new_cols = []
    for c in df_raw.columns:
        c_stripped = str(c).strip()
        if c_stripped in seen:
            seen[c_stripped] += 1
            new_cols.append(f"{c_stripped}_{seen[c_stripped]}")
        else:
            seen[c_stripped] = 0
            new_cols.append(c_stripped)
    df_raw.columns = new_cols

    col_types = detect_column_types(df_raw)
    df_raw = coerce_dates(df_raw, col_types)

    # ----------------------------- Sidebar: Column Type Override -----------------------------

    st.sidebar.title("🛠️ Column Types")
    with st.sidebar.expander("Adjust detected column types", expanded=False):
        st.caption("Override auto-detected types (e.g. force a high-cardinality text column like 'Name' to Categorical).")
        type_options = ["numeric", "date", "categorical", "text"]
        overridden_col_types = {}
        for col in df_raw.columns:
            default_type = col_types.get(col, "text")
            chosen = st.selectbox(
                col,
                type_options,
                index=type_options.index(default_type),
                key=f"type_override_{col}",
            )
            overridden_col_types[col] = chosen
        col_types = overridden_col_types

    # Re-coerce dates and numerics in case a column's type was overridden
    df_raw = coerce_dates(df_raw, col_types)
    df_raw = coerce_numeric(df_raw, col_types)

    numeric_cols = cols_by_type(col_types, "numeric")
    date_cols = cols_by_type(col_types, "date")
    cat_cols = cols_by_type(col_types, "categorical")
    text_cols = cols_by_type(col_types, "text")

    df_raw = sanitize_date_columns(df_raw, date_cols)

    # ----------------------------- Sidebar: Filters -----------------------------

    st.sidebar.title("🔎 Filters")
    filtered_df = df_raw.copy()

    with st.sidebar.expander("Filter data", expanded=False):
        for col in cat_cols:
            options = sorted(df_raw[col].dropna().unique().tolist(), key=str)
            selected = st.multiselect(f"{col}", options, default=[], key=f"filter_cat_{col}")
            if selected:
                filtered_df = filtered_df[filtered_df[col].isin(selected)]

        for col in numeric_cols:
            col_data = df_raw[col].dropna()
            if col_data.empty:
                st.caption(f"⚠️ **{col}**: no numeric values after conversion — check column type.")
                continue
            cmin, cmax = float(col_data.min()), float(col_data.max())
            if pd.isna(cmin) or pd.isna(cmax):
                st.caption(f"⚠️ **{col}**: could not determine a numeric range.")
                continue
            if cmin == cmax:
                st.caption(f"{col}: single value ({cmin}), no range filter needed.")
                continue
            rng = st.slider(f"{col}", cmin, cmax, (cmin, cmax), key=f"filter_num_{col}")
            filtered_df = filtered_df[(filtered_df[col] >= rng[0]) & (filtered_df[col] <= rng[1])]

        for col in date_cols:
            valid_dates = df_raw[col].dropna()
            if valid_dates.empty:
                st.caption(f"⚠️ **{col}**: no valid dates could be parsed from this column — "
                        f"if this was overridden to Date, the underlying values may not be date-formatted.")
                continue
            dmin, dmax = valid_dates.min().date(), valid_dates.max().date()
            if pd.isna(dmin) or pd.isna(dmax):
                st.caption(f"⚠️ **{col}**: could not determine a date range.")
                continue
            if dmin == dmax:
                st.caption(f"{col}: single date ({dmin}), no range filter needed.")
                continue
            drange = st.date_input(f"{col}", (dmin, dmax), key=f"filter_date_{col}")
            if isinstance(drange, tuple) and len(drange) == 2:
                filtered_df = filtered_df[
                    (filtered_df[col] >= pd.Timestamp(drange[0])) &
                    (filtered_df[col] <= pd.Timestamp(drange[1]))
                ]

    st.sidebar.caption(f"Rows after filtering: {len(filtered_df)} / {len(df_raw)}")

    # ----------------------------- Main -----------------------------

    st.caption(f"Sheet: **{sheet}** | Rows: {len(df_raw)} | Columns: {len(df_raw.columns)}")

    tab_overview, tab_charts, tab_pivot = st.tabs(["🔍 Overview", "📈 Charts", "🧮 Pivot Table"])

    # ---- Overview Tab ----
    with tab_overview:
        st.subheader("Data Preview")
        st.dataframe(filtered_df.head(200), width='stretch')

        if numeric_cols:
            st.subheader("Summary Statistics (numeric columns)")
            st.dataframe(filtered_df[numeric_cols].describe().T, width='stretch')
        st.subheader("Detected Schema")
        schema_df = pd.DataFrame({
            "Column": list(col_types.keys()),
            "Detected Type": list(col_types.values()),
            "Unique Values": [df_raw[c].nunique(dropna=True) for c in col_types],
            "Missing": [df_raw[c].isna().sum() for c in col_types],
        })
        st.dataframe(schema_df, width='stretch')

        st.download_button(
            "⬇️ Download filtered data (CSV)",
            filtered_df.to_csv(index=False).encode("utf-8"),
            file_name="filtered_data.csv",
            mime="text/csv",
            key="overview_download",
        )

    # ---- Charts Tab ----
    with tab_charts:
        st.subheader("Build a Chart")

        chart_type = st.selectbox(
            "Chart type",
            ["Bar", "Line", "Scatter", "Histogram", "Box", "Pie", "Area", "Combo (Bar + Line)", "Correlation Heatmap"],
            key="chart_type_select",
        )

        title_col, table_col, border_col = st.columns([3, 1, 1])
        with title_col:
            chart_title = st.text_input("Chart title (optional — auto-generated if left blank)",
                                        value="", key="chart_title_input")
        with table_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            show_data_table = st.checkbox("Show data table", value=False, key="chart_show_table")
        with border_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            show_border = st.checkbox("Chart border", value=True, key="chart_show_border")

        plottable_x = date_cols + cat_cols + numeric_cols
        agg_options = ["sum", "mean", "count", "min", "max"]
        agg_options_extended = agg_options + ["median", "std"]

        def render_chart(fig, default_title, table_df):
            fig.update_layout(title=chart_title.strip() if chart_title.strip() else default_title)
            if show_border:
                fig.update_xaxes(showline=True, linewidth=1.5, linecolor="rgba(60,60,60,0.7)", mirror=True)
                fig.update_yaxes(showline=True, linewidth=1.5, linecolor="rgba(60,60,60,0.7)", mirror=True)
                fig.update_layout(
                    plot_bgcolor="white",
                    margin=dict(l=40, r=20, t=60, b=40),
                )
            with st.container(border=True):
                st.plotly_chart(fig)
            if show_data_table:
                st.dataframe(table_df, width='stretch')

        if chart_type == "Correlation Heatmap":
            if len(numeric_cols) < 2:
                st.warning("Need at least 2 numeric columns for a correlation heatmap.")
            else:
                corr = filtered_df[numeric_cols].corr()
                fig = px.imshow(corr, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r")
                render_chart(fig, "Correlation Heatmap", corr)

        elif chart_type == "Combo (Bar + Line)":
            if not numeric_cols or not plottable_x:
                st.warning("Need at least one numeric column and one X-axis column for a combo chart.")
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    combo_x = st.selectbox("X-axis", plottable_x, key="combo_x")
                with c2:
                    combo_bar_cols = st.multiselect(
                        "Bar column(s)", numeric_cols, default=numeric_cols[:1], key="combo_bar_cols"
                    )
                with c3:
                    combo_line_cols = st.multiselect(
                        "Line column(s)", [c for c in numeric_cols if c not in combo_bar_cols],
                        key="combo_line_cols",
                    )

                c4, c5 = st.columns(2)
                with c4:
                    combo_agg = st.selectbox("Aggregation (applied to all selected columns)",
                                            agg_options, index=0, key="combo_agg")
                with c5:
                    combo_secondary = st.checkbox(
                        "Plot line column(s) on a secondary Y-axis",
                        value=True, key="combo_secondary_axis",
                        help="Useful when bar and line values are on very different scales.",
                    )

                combo_cols = combo_bar_cols + combo_line_cols
                if not combo_cols:
                    st.info("Select at least one Bar or Line column.")
                else:
                    grouped = (
                        filtered_df.groupby(combo_x)[combo_cols]
                        .agg(combo_agg)
                        .reset_index()
                        .sort_values(combo_x)
                    )
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    for c in combo_bar_cols:
                        fig.add_trace(go.Bar(x=grouped[combo_x], y=grouped[c], name=c), secondary_y=False)
                    for c in combo_line_cols:
                        fig.add_trace(
                            go.Scatter(x=grouped[combo_x], y=grouped[c], name=c, mode="lines+markers"),
                            secondary_y=combo_secondary,
                        )
                    if combo_bar_cols:
                        fig.update_yaxes(title_text=" / ".join(combo_bar_cols), secondary_y=False)
                    if combo_line_cols:
                        fig.update_yaxes(title_text=" / ".join(combo_line_cols), secondary_y=combo_secondary)
                    fig.update_xaxes(title_text=combo_x)
                    render_chart(fig, f"{', '.join(combo_cols)} by {combo_x}", grouped)

        elif chart_type == "Histogram":
            if not numeric_cols:
                st.warning("No numeric columns available for a histogram.")
            else:
                hist_cols = st.multiselect("Column(s)", numeric_cols, default=numeric_cols[:1], key="hist_cols")
                bins = st.slider("Bins", 5, 100, 30, key="hist_bins")
                if hist_cols:
                    melted = filtered_df[hist_cols].melt(var_name="Column", value_name="Value")
                    fig = px.histogram(
                        melted, x="Value", color="Column" if len(hist_cols) > 1 else None,
                        nbins=bins, barmode="overlay", opacity=0.7 if len(hist_cols) > 1 else 1.0,
                    )
                    render_chart(fig, f"Distribution of {', '.join(hist_cols)}", filtered_df[hist_cols])

        elif chart_type == "Box":
            if not numeric_cols:
                st.warning("No numeric columns available for a box plot.")
            else:
                box_cols = st.multiselect("Column(s)", numeric_cols, default=numeric_cols[:1], key="box_cols")
                if box_cols:
                    melted = filtered_df[box_cols].melt(var_name="Column", value_name="Value")
                    fig = px.box(melted, x="Column", y="Value")
                    render_chart(fig, f"Box Plot of {', '.join(box_cols)}", filtered_df[box_cols])

        elif chart_type == "Pie":
            if not cat_cols or not numeric_cols:
                st.warning("Pie chart needs a categorical column and a numeric column.")
            else:
                names_col = st.selectbox("Category (names)", cat_cols, key="pie_names")
                values_col = st.selectbox("Values", numeric_cols, key="pie_values")
                agg = st.selectbox("Aggregation", agg_options, index=0, key="pie_agg")
                data = filtered_df.groupby(names_col)[values_col].agg(agg).reset_index()
                fig = px.pie(data, names=names_col, values=values_col)
                render_chart(fig, f"{values_col} ({agg}) by {names_col}", data)

        else:  # Bar, Line, Scatter, Area
            col1, col2, col3 = st.columns(3)
            with col1:
                x_cols = st.multiselect(
                    "X-axis (1 or more)",
                    plottable_x if plottable_x else df_raw.columns.tolist(),
                    default=[plottable_x[0]] if plottable_x else [],
                    key="xyz_x",
                )
            with col2:
                y_options = numeric_cols if numeric_cols else df_raw.columns.tolist()
                y_cols = st.multiselect(
                    "Y-axis (1 or more)", y_options, default=[y_options[0]] if y_options else [], key="xyz_y"
                )
            with col3:
                if len(y_cols) > 1:
                    st.caption("Color is auto-assigned per Y column when multiple Y columns are selected.")
                    color_col = None
                else:
                    color_col = st.selectbox("Color (optional)", ["None"] + cat_cols, key="xyz_color")
                    color_col = None if color_col == "None" else color_col

            if not x_cols or not y_cols:
                st.info("Select at least one X-axis and one Y-axis column.")
            else:
                default_aggregate = any(col_types.get(c) in ["categorical", "date"] for c in x_cols)
                aggregate = st.checkbox(
                    "Aggregate Y by X",
                    value=default_aggregate,
                    key="xyz_aggregate_toggle",
                    help=(
                        "When multiple rows share the same X value (e.g. several rows per Region or per Date), "
                        "this collapses them into one summary point per X using the aggregation you choose below "
                        "(sum/mean/etc). Leave unchecked to plot every raw row as-is — useful for Scatter plots "
                        "or when X is already unique per row. For Line/Bar/Area with repeated X values, leaving "
                        "this off usually produces a messy, overlapping chart."
                    ),
                )

                plot_df = filtered_df
                y_numeric = [c for c in y_cols if c in numeric_cols]
                y_arg_cols = y_cols

                if aggregate and y_numeric:
                    st.markdown("**Aggregation per Y column** — pick one or more stats for each:")
                    agg_map = {}
                    agg_ui_cols = st.columns(len(y_numeric))
                    for i, ycol in enumerate(y_numeric):
                        with agg_ui_cols[i]:
                            chosen = st.multiselect(
                                f"{ycol}", agg_options_extended, default=["sum"], key=f"chart_agg_{ycol}"
                            )
                            if chosen:
                                agg_map[ycol] = chosen

                    group_cols = x_cols + ([color_col] if color_col else [])
                    if agg_map:
                        grouped = filtered_df.groupby(group_cols).agg(agg_map)
                        grouped.columns = [f"{c}_{a}" for c, a in grouped.columns]
                        plot_df = grouped.reset_index()
                        y_arg_cols = list(grouped.columns)
                    else:
                        st.info("Pick at least one aggregation per Y column.")
                        plot_df = filtered_df.groupby(group_cols, as_index=False)[y_numeric].sum()
                        y_arg_cols = y_numeric

                # Combine multiple X columns into a single plottable axis
                if len(x_cols) > 1:
                    plot_df = plot_df.copy()
                    plot_df["X (combined)"] = plot_df[x_cols].astype(str).agg(" | ".join, axis=1)
                    x_field = "X (combined)"
                else:
                    x_field = x_cols[0]

                plot_df = plot_df.sort_values(by=x_field) if x_field in plot_df.columns else plot_df

                barmode = "group"
                orientation = "v"
                if chart_type == "Bar":
                    bar_ctrl1, bar_ctrl2 = st.columns(2)
                    with bar_ctrl1:
                        if len(y_arg_cols) > 1 or color_col:
                            bar_mode_choice = st.radio(
                                "Bar mode", ["Grouped (side-by-side)", "Stacked"],
                                horizontal=True, key="bar_mode_toggle",
                            )
                            barmode = "stack" if bar_mode_choice == "Stacked" else "group"
                    with bar_ctrl2:
                        orientation_choice = st.radio(
                            "Orientation", ["Vertical", "Horizontal"], horizontal=True, key="bar_orientation_toggle"
                        )
                        orientation = "h" if orientation_choice == "Horizontal" else "v"

                chart_fn = {"Bar": px.bar, "Line": px.line, "Scatter": px.scatter, "Area": px.area}[chart_type]
                try:
                    y_arg = y_arg_cols if len(y_arg_cols) > 1 else y_arg_cols[0]
                    extra_kwargs = {"barmode": barmode} if chart_type == "Bar" else {}
                    if chart_type == "Bar" and orientation == "h":
                        # Horizontal bar: swap axes roles (categories on Y, values on X)
                        fig = chart_fn(plot_df, x=y_arg, y=x_field, color=color_col,
                                    orientation="h", **extra_kwargs)
                    else:
                        fig = chart_fn(plot_df, x=x_field, y=y_arg, color=color_col, **extra_kwargs)
                    default_title = f"{', '.join(y_arg_cols)} by {x_field}"
                    render_chart(fig, default_title, plot_df)
                except Exception as e:
                    st.error(f"Could not render chart: {e}")

    # ---- Pivot Table Tab ----
    with tab_pivot:
        st.subheader("Build a Pivot Table")

        row_options = cat_cols + date_cols
        if not row_options or not numeric_cols:
            st.warning("Need at least one categorical/date column and one numeric column to build a pivot table.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                rows = st.multiselect("Rows", row_options, default=row_options[:1], key="pivot_rows")
            with c2:
                columns = st.multiselect(
                    "Columns", [c for c in cat_cols if c not in rows], key="pivot_columns"
                )
            with c3:
                value_cols = st.multiselect(
                    "Value column(s)", numeric_cols, default=numeric_cols[:1], key="pivot_value_cols"
                )

            st.markdown("**Aggregation per value column** — pick one or more stats for each value field:")
            agg_choices = ["sum", "mean", "count", "min", "max", "median", "std"]
            agg_map = {}
            if value_cols:
                agg_cols_ui = st.columns(len(value_cols))
                for i, vcol in enumerate(value_cols):
                    with agg_cols_ui[i]:
                        chosen_aggs = st.multiselect(
                            f"{vcol}",
                            agg_choices,
                            default=["sum"],
                            key=f"pivot_agg_{vcol}",
                        )
                        if chosen_aggs:
                            agg_map[vcol] = chosen_aggs

            if rows and agg_map:
                try:
                    pivot = pd.pivot_table(
                        filtered_df,
                        index=rows,
                        columns=columns if columns else None,
                        aggfunc=agg_map,
                        fill_value=0,
                    )
                    st.dataframe(pivot, width='stretch')

                    st.download_button(
                        "⬇️ Download pivot table (Excel)",
                        to_excel_bytes(pivot.reset_index()),
                        file_name="pivot_table.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="pivot_download",
                    )

                    if st.checkbox("Visualize pivot table", key="pivot_visualize_toggle"):
                        pivot_flat = pivot.reset_index()
                        pivot_flat.columns = [
                            "_".join(str(x) for x in c if str(x) != "").strip("_") if isinstance(c, tuple) else str(c)
                            for c in pivot_flat.columns
                        ]
                        melt_value_cols = [c for c in pivot_flat.columns if c not in rows]
                        melted = pivot_flat.melt(id_vars=rows, value_vars=melt_value_cols,
                                                var_name="Metric", value_name="Value")
                        fig = px.bar(melted, x=rows[0], y="Value", color="Metric", barmode="group")
                        st.plotly_chart(fig, width='stretch')
                except Exception as e:
                    st.error(f"Could not build pivot table: {e}")
            else:
                st.info("Select at least one row field, one value column, and one aggregation.")