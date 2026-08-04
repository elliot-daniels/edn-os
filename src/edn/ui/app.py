"""Streamlit entry point for local EDN email-memory search."""

from __future__ import annotations

import streamlit as st

from edn.ui.service import (
    DEFAULT_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
    DatabaseConfigurationError,
    DatabaseUnavailableError,
    SearchQueryError,
    format_result,
    open_read_only_store,
    resolve_database_path,
    search_emails,
)

st.set_page_config(
    page_title="EDN OS",
    page_icon="🔎",
    layout="wide",
)

st.title("EDN OS")
st.caption(
    "Local email-memory search. Your indexed email content stays on this device."
)

try:
    database_path = resolve_database_path()
    store = open_read_only_store(database_path)
    indexed_email_count = store.count()
except (DatabaseConfigurationError, DatabaseUnavailableError) as error:
    st.error(str(error))
    st.stop()

st.success(f"Database ready · {indexed_email_count:,} indexed emails")

with st.form("email-search"):
    query = st.text_input(
        "Search email memory",
        placeholder="Try Pimba, Juniper, CRQ, or a quoted phrase",
        help="Searches subjects, senders, and plain-text email bodies.",
    )
    result_limit = st.number_input(
        "Maximum results",
        min_value=1,
        max_value=MAX_RESULT_LIMIT,
        value=DEFAULT_RESULT_LIMIT,
        step=1,
    )
    submitted = st.form_submit_button("Search", type="primary")

if submitted:
    if not query.strip():
        st.info("Enter one or more keywords to search email memory.")
    else:
        try:
            with st.spinner("Searching local email memory…"):
                records = search_emails(store, query, limit=int(result_limit))
        except SearchQueryError as error:
            st.warning(str(error))
        except DatabaseUnavailableError as error:
            st.error(str(error))
        else:
            if not records:
                st.info("No matching emails found.")
            else:
                st.subheader(f"{len(records)} result{'s' if len(records) != 1 else ''}")
                for record in records:
                    result = format_result(record)
                    with st.container(border=True):
                        st.markdown("#### Email")
                        st.text(result.subject)
                        metadata_column, provenance_column = st.columns(2)
                        with metadata_column:
                            st.markdown("**From**")
                            st.text(result.sender)
                            st.markdown("**Sent**")
                            st.text(result.sent_date)
                            st.markdown("**Folder**")
                            st.text(result.folder_path)
                        with provenance_column:
                            st.write("**Message ID / source key:**")
                            st.code(
                                result.provenance_key,
                                language=None,
                                wrap_lines=True,
                            )
                        st.text(result.body_preview)
                        with st.expander("Show full plain-text body"):
                            st.text(result.body_text)
