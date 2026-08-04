"""Streamlit entry point for local EDN email search and grounded answers."""

from __future__ import annotations

import streamlit as st

from edn.knowledge.answering import (
    AnswerConfigurationError,
    AnswerGenerationError,
    answer_question,
    resolve_answer_provider,
)
from edn.knowledge.models import EmailEvidence
from edn.memory.models import EmailRecord
from edn.retrieval import (
    DEFAULT_EVIDENCE_LIMIT,
    MAX_EVIDENCE_LIMIT,
    RetrievalEngine,
    RetrievalError,
)
from edn.ui.service import (
    DEFAULT_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
    DatabaseConfigurationError,
    DatabaseTemporarilyBusyError,
    DatabaseUnavailableError,
    SearchQueryError,
    format_result,
    format_sent_date,
    open_read_only_store,
    resolve_database_path,
    search_emails,
)


def _render_email_result(record: EmailRecord) -> None:
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
            st.code(result.provenance_key, language=None, wrap_lines=True)
        st.text(result.body_preview)
        with st.expander("Show full plain-text body"):
            st.text(result.body_text)


def _render_evidence(item: EmailEvidence) -> None:
    with st.expander(f"[{item.evidence_id}] Supporting email"):
        st.markdown("**Subject**")
        st.text(item.subject or "(No subject)")
        st.markdown("**Sender**")
        st.text(item.sender or "(Unknown sender)")
        st.markdown("**Sent**")
        st.text(format_sent_date(item.sent_at))
        st.markdown("**Folder**")
        st.text(item.folder_path or "(Unknown folder)")
        st.markdown("**Message ID / source key**")
        st.code(
            item.message_id or item.source_record_key,
            language=None,
            wrap_lines=True,
        )
        st.markdown("**Relevant excerpt**")
        st.text(item.body_excerpt)
        st.markdown("**Full plain-text body**")
        st.text(item.body_text or "(No plain-text body)")


st.set_page_config(page_title="EDN OS", page_icon="🔎", layout="wide")
st.title("EDN OS")
st.caption(
    "Search local email memory or ask grounded questions. "
    "Indexed email content stays on this device."
)

try:
    database_path = resolve_database_path()
    store = open_read_only_store(database_path)
    indexed_email_count = store.count()
    retrieval_engine = RetrievalEngine.from_store(store)
    answer_provider = resolve_answer_provider()
except (
    AnswerConfigurationError,
    DatabaseConfigurationError,
    DatabaseUnavailableError,
) as error:
    st.error(str(error))
    st.stop()

st.success(f"Database ready · {indexed_email_count:,} indexed emails")
search_tab, ask_tab = st.tabs(("Search", "Ask EDN"))

with search_tab:
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
        search_submitted = st.form_submit_button("Search", type="primary")

    if search_submitted:
        if not query.strip():
            st.info("Enter one or more keywords to search email memory.")
        else:
            try:
                with st.spinner("Searching local email memory…"):
                    records = search_emails(store, query, limit=int(result_limit))
            except DatabaseTemporarilyBusyError as error:
                st.warning(str(error))
            except SearchQueryError as error:
                st.warning(str(error))
            else:
                if not records:
                    st.info("No matching emails found.")
                else:
                    st.subheader(
                        f"{len(records)} result{'s' if len(records) != 1 else ''}"
                    )
                    for record in records:
                        _render_email_result(record)

with ask_tab:
    st.caption(
        "Ask EDN uses deterministic local retrieval and extractive summaries. "
        "It does not use cloud AI."
    )
    with st.form("ask-edn"):
        question = st.text_area(
            "Ask a question about your email archive",
            placeholder="What happened during the Pimba outage?",
            height=100,
        )
        evidence_limit = st.number_input(
            "Maximum supporting emails",
            min_value=1,
            max_value=MAX_EVIDENCE_LIMIT,
            value=DEFAULT_EVIDENCE_LIMIT,
            step=1,
        )
        ask_submitted = st.form_submit_button("Ask EDN", type="primary")

    if ask_submitted:
        if not question.strip():
            st.info("Enter a question for Ask EDN.")
        else:
            try:
                with st.spinner("Retrieving evidence and grounding the answer…"):
                    answered = answer_question(
                        question,
                        retrieval_engine,
                        answer_provider,
                        retrieval_limit=int(evidence_limit),
                    )
            except (AnswerGenerationError, RetrievalError) as error:
                st.error(str(error))
            else:
                st.subheader("Grounded answer")
                st.text(answered.answer.text)
                for warning in answered.answer.warnings:
                    st.warning(warning)
                if answered.answer.insufficient_evidence:
                    st.info(
                        "The retrieved evidence was insufficient for a grounded answer."
                    )
                else:
                    cited_ids = set(answered.answer.cited_evidence_ids)
                    st.subheader("Sources")
                    for evidence_item in answered.evidence:
                        if evidence_item.evidence_id in cited_ids:
                            _render_evidence(evidence_item)
