import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


SETTINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "settings.json"


def read_settings_text() -> str:
    return SETTINGS_PATH.read_text(encoding="utf-8")


def parse_json(json_text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"

    if not isinstance(parsed, dict):
        return None, "settings.json must contain a JSON object at the top level."

    return parsed, None


def pretty_json(settings: dict[str, Any]) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False)


def value_type(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return type(value).__name__


def display_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def summarize_value(value: Any) -> str:
    if isinstance(value, dict):
        return f"{len(value)} key(s)"
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    if value is None:
        return ""
    return str(value)


def build_tasks_summary(settings: dict[str, Any]) -> pd.DataFrame:
    rows = []
    tasks = settings.get("tasks", {})
    if not isinstance(tasks, dict):
        return pd.DataFrame([{
            "path": "tasks",
            "type": value_type(tasks),
            "value": display_value(tasks),
        }])

    for task_name, task_config in tasks.items():
        row = {
            "task": task_name,
            "type": value_type(task_config),
            "summary": summarize_value(task_config),
        }
        if isinstance(task_config, dict):
            row["keys"] = ", ".join(task_config.keys())
        else:
            row["value"] = display_value(task_config)
        rows.append(row)

    return pd.DataFrame(rows)


def build_overview_rows(name: str, value: Any) -> pd.DataFrame:
    if isinstance(value, dict):
        return pd.DataFrame([
            {
                "key": key,
                "type": value_type(child_value),
                "summary": summarize_value(child_value),
                "value": "" if isinstance(child_value, (dict, list)) else display_value(child_value),
            }
            for key, child_value in value.items()
        ])

    if isinstance(value, list):
        return pd.DataFrame([
            {
                "index": index,
                "type": value_type(child_value),
                "summary": summarize_value(child_value),
                "value": display_value(child_value),
            }
            for index, child_value in enumerate(value, start=1)
        ])

    return pd.DataFrame([{"key": name, "type": value_type(value), "value": display_value(value)}])


def table_from_collection(path: str, value: Any) -> pd.DataFrame | None:
    if isinstance(value, dict):
        rows = []
        for key, child_value in value.items():
            row = {"name": key}
            if isinstance(child_value, dict):
                for child_key, grandchild_value in child_value.items():
                    row[child_key] = display_value(grandchild_value)
            else:
                row["type"] = value_type(child_value)
                row["value"] = display_value(child_value)
            rows.append(row)
        return pd.DataFrame(rows) if rows else None

    if isinstance(value, list):
        rows = []
        for index, child_value in enumerate(value, start=1):
            row = {"index": index}
            if isinstance(child_value, dict):
                for child_key, grandchild_value in child_value.items():
                    row[child_key] = display_value(grandchild_value)
            else:
                row["type"] = value_type(child_value)
                row["value"] = display_value(child_value)
            rows.append(row)
        return pd.DataFrame(rows) if rows else None

    return None


def collect_nested_tables(value: Any, path: str = "") -> list[tuple[str, pd.DataFrame]]:
    tables = []
    if isinstance(value, dict):
        for key, child_value in value.items():
            child_path = f"{path}.{key}" if path else key
            table = table_from_collection(child_path, child_value)
            if table is not None:
                tables.append((child_path, table))
            if isinstance(child_value, (dict, list)):
                tables.extend(collect_nested_tables(child_value, child_path))
    elif isinstance(value, list):
        for index, child_value in enumerate(value, start=1):
            child_path = f"{path}[{index}]"
            if isinstance(child_value, (dict, list)):
                tables.extend(collect_nested_tables(child_value, child_path))

    return tables


def show_dataframe(title: str, dataframe: pd.DataFrame) -> None:
    st.subheader(title)
    if dataframe.empty:
        st.info("No records available.")
    else:
        st.dataframe(dataframe, hide_index=True)


def set_status(level: str, message: str) -> None:
    st.session_state.settings_status = {"level": level, "message": message}


def save_settings() -> None:
    parsed_settings, error = parse_json(st.session_state.settings_json_text)
    if error:
        set_status("error", error)
        return

    SETTINGS_PATH.write_text(pretty_json(parsed_settings) + "\n", encoding="utf-8")
    st.session_state.settings_json_text = read_settings_text()
    set_status("success", "settings.json saved successfully.")


def format_settings() -> None:
    parsed_settings, error = parse_json(st.session_state.settings_json_text)
    if error:
        set_status("error", error)
        return

    st.session_state.settings_json_text = pretty_json(parsed_settings)
    set_status("success", "JSON formatted.")


def reload_settings() -> None:
    st.session_state.settings_json_text = read_settings_text()
    set_status("info", "settings.json reloaded from file.")


if st.session_state.get("user_type") != "admin":
    st.error("Access denied. Admin privileges required.")
    st.stop()


st.header(":material/settings: Schema Management")
st.caption(f"Editing `{SETTINGS_PATH.relative_to(Path.cwd())}`")

if "settings_json_text" not in st.session_state:
    st.session_state.settings_json_text = read_settings_text()

status = st.session_state.pop("settings_status", None)
if status:
    getattr(st, status["level"])(status["message"])

current_settings, current_error = parse_json(st.session_state.settings_json_text)

tab_tables, tab_json = st.tabs(["Schema tables", "JSON editor"])

with tab_tables:
    if current_error:
        st.error(current_error)
        st.info("Fix the JSON in the editor tab to refresh the table preview.")
    elif current_settings is not None:
        show_dataframe("Task objects", build_tasks_summary(current_settings))

        tasks = current_settings.get("tasks", {})
        if not isinstance(tasks, dict) or not tasks:
            st.info("No task objects found under `tasks`.")
        else:
            selected_task = st.selectbox(
                "Select task object",
                options=list(tasks.keys()),
                key="schema_task_select",
            )
            selected_config = tasks[selected_task]

            show_dataframe(f"{selected_task} overview", build_overview_rows(selected_task, selected_config))

            nested_tables = collect_nested_tables(selected_config)
            if not nested_tables:
                st.info("No nested objects or arrays available for this task.")
            else:
                for table_path, table in nested_tables:
                    show_dataframe(f"{selected_task}.{table_path}", table)

with tab_json:
    with st.form("settings_json_form"):
        st.text_area(
            "settings.json",
            key="settings_json_text",
            height=520,
        )

        with st.container(horizontal=True):
            st.form_submit_button(
                "Save settings",
                type="primary",
                icon=":material/save:",
                on_click=save_settings,
            )
            st.form_submit_button(
                "Format JSON",
                icon=":material/data_object:",
                on_click=format_settings,
            )
            
            st.form_submit_button(
                "Reload from file",
                icon=":material/refresh:",
                on_click=reload_settings,
            )
    #download button to download the settings.json file
    st.download_button(
                "Download settings.json",key="download_settings_btn",
                data=st.session_state.settings_json_text,
                file_name="settings.json",
                mime="application/json",
            )
