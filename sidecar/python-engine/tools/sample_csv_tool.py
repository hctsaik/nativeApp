from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


st.set_page_config(page_title="Sample CSV Analyzer", layout="wide")
st.title("Sample CSV Analyzer")


def host_selected_paths() -> list[str]:
    selected_paths_file = os.environ.get("CIM_SELECTED_PATHS_FILE")
    if not selected_paths_file:
        return []
    try:
        data = json.loads(Path(selected_paths_file).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    paths = data.get("paths", [])
    return [path for path in paths if isinstance(path, str)]


def read_dataframe() -> pd.DataFrame | None:
    csv_paths = [path for path in host_selected_paths() if path.lower().endswith(".csv")]

    if csv_paths:
        st.subheader("Host-selected files")
        selected_path = st.selectbox("CSV file", csv_paths)
        try:
            return pd.read_csv(selected_path)
        except Exception as exc:
            st.error(f"Unable to read host-selected CSV: {exc}")
            return None

    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded_file is None:
        st.info("Select a CSV file from the host portal or upload one here.")
        return None

    try:
        return pd.read_csv(uploaded_file)
    except Exception as exc:
        st.error(f"Unable to read uploaded CSV: {exc}")
        return None


df = read_dataframe()

if df is None:
    st.stop()


st.subheader("Preview")
st.dataframe(df.head(100), use_container_width=True)

st.subheader("Summary")
st.dataframe(df.describe(include="all").transpose(), use_container_width=True)

numeric_columns = df.select_dtypes(include="number").columns.tolist()

if not numeric_columns:
    st.warning("No numeric columns were found for charting.")
    st.stop()

selected_column = st.selectbox("Chart column", numeric_columns)

fig, ax = plt.subplots(figsize=(8, 4))
df[selected_column].dropna().head(200).plot(ax=ax)
ax.set_title(selected_column)
ax.set_xlabel("Row")
ax.set_ylabel("Value")
st.pyplot(fig)
