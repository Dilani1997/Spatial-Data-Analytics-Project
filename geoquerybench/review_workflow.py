"""Review-state helpers and verdict presentation. Owner: Dilani."""

from html import escape

import streamlit as st

from .data_loader import clean


def option_index(options, current_value):
    return options.index(current_value) if current_value in options else 0

def verdict_style(verdict):
    mapping = {
        "Pass": ("correct", "🟢"),
        "Fail": ("incorrect", "🔴"),
        "Correct": ("correct", "🟢"),
        "Partially correct": ("partial", "🟡"),
        "Incorrect": ("incorrect", "🔴"),
        "Correct refusal": ("refusal", "🔵"),
        "Needs adjudication": ("adjudication", "🟣"),
    }
    return mapping.get(verdict, ("pending", "⚪"))

def widget_key(field, qid, reviewer):
    safe_reviewer = "".join(character if character.isalnum() else "_" for character in reviewer)
    return f"{field}_{qid}_{safe_reviewer}"

def apply_demo_values(qid, reviewer):
    values = {
        "result": "Demonstration verification: the client-supplied query ran successfully and its returned rows were checked against the question, schema and expected output.",
        "rewrite_applicable": False,
        "rewritten_query": "",
        "rewrite_equivalence": "Not assessed",
        "rewrite_comments": "",
        "translation_quality": "Not assessed",
        "executability": "Pass",
        "schema": "Pass",
        "logic": "Pass",
        "domain": "Pass",
        "output": "Pass",
        "verdict": "Pass",
        "comments": "The supplied query executed without error, used the expected fields and returned the requested result. Attach the real query-output evidence before using this as a completed review.",
        "flag": False,
    }
    for field, value in values.items():
        st.session_state[widget_key(field, qid, reviewer)] = value

def apply_quick_preset(qid, reviewer, preset):
    if preset == "pass":
        values = {
            "executability": "Pass", "schema": "Pass", "logic": "Pass",
            "domain": "Pass", "output": "Pass", "verdict": "Pass",
            "comments": "The client-supplied query ran successfully and its output answers the original question with the required fields and format.",
            "flag": False,
        }
    elif preset == "fail":
        values = {
            "executability": "Pass", "schema": "Pass", "logic": "Fail",
            "domain": "Fail", "output": "Fail", "verdict": "Fail",
            "comments": "The client-supplied query output does not fully answer the original question. The failing condition and supporting result evidence are recorded below.",
            "flag": False,
        }
    else:
        values = {
            "executability": "Not assessed", "schema": "Not assessed",
            "logic": "Not assessed", "domain": "Not assessed",
            "output": "Not assessed", "verdict": "Not assessed",
            "comments": "", "flag": False,
        }
    for field, value in values.items():
        st.session_state[widget_key(field, qid, reviewer)] = value

def display_verdict(verdict, flagged=False):
    css_class, icon = verdict_style(verdict)
    st.markdown(
        f'<span class="badge {css_class}">{icon} {escape(clean(verdict, "Not assessed"))}</span>',
        unsafe_allow_html=True,
    )
    if flagged:
        st.markdown(
            '<span class="badge flag">🚩 Requires client clarification</span>',
            unsafe_allow_html=True,
        )
