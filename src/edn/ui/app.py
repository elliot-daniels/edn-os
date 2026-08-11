"""Streamlit entry point for local EDN email search and grounded answers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from edn.core import (
    AuthenticationStatus,
    CapabilityManifest,
    CapabilityOnboardingPlanner,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    CapabilityValueProfile,
    Classification,
    OnboardingRecommendation,
    PermissionEvaluator,
    PermissionOutcome,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
)
from edn.intelligence import (
    ActionPlanner,
    ActionStatus,
    CapabilityGapAdapter,
    ContextAssembler,
    EmailRetrievalAdapter,
    IntelligenceRequest,
    IntelligenceService,
    KnowledgeGraphAdapter,
    SourceAdapter,
    SQLiteActionProposalStore,
    SQLiteSessionStore,
)
from edn.knowledge.answering import (
    AnswerConfigurationError,
    AnswerGenerationError,
    answer_question,
    resolve_answer_provider,
)
from edn.knowledge.models import EmailEvidence
from edn.knowledge_graph.entities import EntityType
from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.knowledge_graph.retrieval import KnowledgeCandidateRetriever
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
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
    evidence_security_label,
    format_result,
    format_sent_date,
    open_read_only_store,
    resolve_database_path,
    resolve_intelligence_database_path,
    search_emails,
    visible_intelligence_evidence,
)


def _intelligence_runtime(
    store: SQLiteEmailStore,
    graph_store: KnowledgeGraphStore,
    graph_available: bool,
    operational_database_path: Path,
) -> tuple[
    IntelligenceService,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    Classification,
    tuple[tuple[str, str, str], ...],
    tuple[OnboardingRecommendation, ...],
]:
    domain = SecurityDomain("EDN", "EDN Systems", tenant_id="edn-local")
    classification = Classification("edn", "confidential", "EDN Confidential", rank=2)
    principal = PrincipalContext("local-owner", "edn-local", frozenset({domain}), True)
    purpose = Purpose("business-intelligence", "EDN business intelligence")
    adapters: list[SourceAdapter] = [
        EmailRetrievalAdapter(RetrievalEngine.from_store(store))
    ]
    if graph_available:
        adapters.append(KnowledgeGraphAdapter(graph_store))
    adapters.append(
        CapabilityGapAdapter(
            "calendar.search", "search", ("default-calendar", "window:this-week")
        )
    )
    registry = CapabilityRegistry()
    for adapter in adapters:
        is_calendar = adapter.capability_id == "calendar.search"
        manifest = CapabilityManifest(
            adapter.capability_id,
            "microsoft-graph" if is_calendar else "edn-local",
            "microsoft-calendar" if is_calendar else "legacy-read-adapter",
            "0.1.0",
            frozenset({adapter.operation}),
            frozenset({"Calendars.Read"}) if is_calendar else frozenset(),
            frozenset({"EDN"}),
            "read",
        )
        registry.register(
            manifest,
            CapabilityRuntimeState(
                CapabilityStatus.AUTHENTICATION_REQUIRED
                if is_calendar
                else CapabilityStatus.READY,
                AuthenticationStatus.MISSING
                if is_calendar
                else AuthenticationStatus.NOT_REQUIRED,
                health="unknown" if is_calendar else "healthy",
                explanation=(
                    "Calendar read is implemented but awaits live approval "
                    "and authentication."
                    if is_calendar
                    else "Local read-only source is available."
                ),
            ),
        )
    policy = PermissionEvaluator(
        PolicySet(
            "local-alpha",
            "1",
            tuple(
                PolicyRule(
                    f"allow-{adapter.capability_id.replace('.', '-')}",
                    PermissionOutcome.ALLOWED,
                    "Local read-only Alpha authority.",
                    principal_ids=frozenset({principal.principal_id}),
                    purpose_ids=frozenset({purpose.purpose_id}),
                    domain_ids=frozenset({domain.domain_id}),
                    capability_ids=frozenset({adapter.capability_id}),
                    operations=frozenset({adapter.operation}),
                )
                for adapter in adapters
            ),
        )
    )
    sessions = SQLiteSessionStore(operational_database_path)
    actions = SQLiteActionProposalStore(operational_database_path)
    sessions.initialise()
    actions.initialise()
    health = tuple(
        (adapter.capability_id, decision.status.value, decision.explanation)
        for adapter in adapters
        for decision in (
            registry.resolve(adapter.capability_id, adapter.operation, domain),
        )
    )
    onboarding = CapabilityOnboardingPlanner().plan(
        registry,
        tuple(
            CapabilityValueProfile(
                adapter.capability_id,
                adapter.operation,
                decision_value=5 if adapter.capability_id == "calendar.search" else 4,
                recurrence=5,
                freshness=5 if adapter.capability_id == "calendar.search" else 3,
                administrative_leverage=4,
                information_density=4,
                record_count=store.count()
                if adapter.capability_id == "email.search"
                else None,
                exact_scope=("default-calendar", "window-this-week")
                if adapter.capability_id == "calendar.search"
                else ("local-authorised-store",),
            )
            for adapter in adapters
        ),
        domain,
    )
    return (
        IntelligenceService(
            ContextAssembler(registry, policy, tuple(adapters)),
            sessions=sessions,
            action_planner=ActionPlanner(actions),
        ),
        principal,
        purpose,
        domain,
        classification,
        health,
        onboarding,
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
    intelligence_database_path = resolve_intelligence_database_path(database_path)
    store = open_read_only_store(database_path)
    indexed_email_count = store.count()
    graph_store = KnowledgeGraphStore(database_path, read_only=True)
    graph_available = graph_store.schema_available()
    supplemental = (
        (KnowledgeCandidateRetriever(graph_store, store),) if graph_available else ()
    )
    retrieval_engine = RetrievalEngine.from_store(
        store, supplemental_retrievers=supplemental
    )
    answer_provider = resolve_answer_provider()
except (
    AnswerConfigurationError,
    DatabaseConfigurationError,
    DatabaseUnavailableError,
) as error:
    st.error(str(error))
    st.stop()

if "intelligence_runtime" not in st.session_state:
    st.session_state.intelligence_runtime = _intelligence_runtime(
        store, graph_store, graph_available, intelligence_database_path
    )
(
    intelligence_service,
    intelligence_principal,
    intelligence_purpose,
    intelligence_domain,
    intelligence_classification,
    intelligence_capability_health,
    intelligence_onboarding,
) = st.session_state.intelligence_runtime

st.success(f"Database ready · {indexed_email_count:,} indexed emails")
intelligence_tab, search_tab, ask_tab, knowledge_tab = st.tabs(
    ("Intelligence", "Search", "Ask EDN", "Knowledge")
)

with intelligence_tab:
    st.caption(
        "Governed local intelligence with evidence, uncertainty, and capability gaps."
    )
    with st.expander("Capability health"):
        for capability_id, status, explanation in intelligence_capability_health:
            st.write(f"**{capability_id}** - {status}")
            st.caption(explanation)
    with st.expander("Progressive capability onboarding"):
        st.caption(
            "Ranked by decision value, recurrence, freshness, information density "
            "and administrative leverage. Counts and bytes are capacity facts only."
        )
        for item in intelligence_onboarding:
            st.write(
                f"**{item.capability_id}** - {item.readiness.value} "
                f"(value score {item.value_score})"
            )
            st.caption(item.readiness_explanation)
            if item.missing_steps:
                st.write("Missing steps: " + ", ".join(item.missing_steps))
            if item.capacity_record_count is not None:
                st.caption(
                    f"Capacity input: {item.capacity_record_count:,} indexed records"
                )
            if item.request is not None:
                st.code(
                    "Request: "
                    f"{item.request.operation} {item.request.capability_id}; "
                    f"scope={','.join(item.request.exact_scope) or 'none'}; "
                    "permissions="
                    f"{','.join(item.request.required_permissions) or 'none'}",
                    language=None,
                )
                st.caption(
                    "Exact request; owner may reject it. No authority is granted."
                )
    if "intelligence_messages" not in st.session_state:
        st.session_state.intelligence_messages = []
    for message in st.session_state.intelligence_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    daily_brief_requested = st.button(
        "Build today's brief",
        type="primary",
        key="daily-intelligence-brief",
    )
    intelligence_question = st.chat_input(
        "Ask what matters this week for EDN Systems",
        key="intelligence-question",
    )
    if daily_brief_requested or intelligence_question:
        submitted_question = (
            "What do I need to know today?"
            if daily_brief_requested
            else intelligence_question
        )
        request = IntelligenceRequest(
            submitted_question,
            intelligence_principal,
            intelligence_purpose,
            intelligence_domain,
            intelligence_classification,
        )
        prior_session = st.session_state.get("intelligence_session_id")
        try:
            if daily_brief_requested:
                response = intelligence_service.daily_brief(
                    request,
                    now=datetime.now(UTC),
                    session_id=prior_session,
                )
            else:
                response = intelligence_service.answer(
                    request,
                    now=datetime.now(UTC),
                    session_id=prior_session,
                )
        except (PermissionError, RuntimeError, ValueError):
            st.error("Intelligence could not safely assemble the authorised context.")
        else:
            st.session_state.intelligence_session_id = response.session_id
            st.session_state.intelligence_messages.extend(
                (
                    {"role": "user", "content": submitted_question},
                    {
                        "role": "assistant",
                        "content": "\n\n".join(
                            f"{item.kind.value.upper()}: {item.text}"
                            for item in response.statements
                        ),
                    },
                )
            )
            st.subheader("Priorities")
            for number, priority in enumerate(response.priorities, start=1):
                with st.container(border=True):
                    st.markdown(f"#### {number}. {priority.title}")
                    st.write(priority.why_it_matters)
                    st.caption(
                        f"Timeframe: {priority.timeframe or 'Unknown'} · "
                        f"Confidence: {priority.confidence}"
                    )
                    st.write(f"Recommended next step: {priority.recommended_next_step}")
                    for missing in priority.missing_information:
                        st.info(f"Missing information: {missing}")
            for proposal in response.proposed_actions:
                st.session_state.setdefault("proposal_evidence", {})[
                    proposal.proposal_id
                ] = proposal.source_evidence_ids
            st.subheader("Evidence")
            for item in visible_intelligence_evidence(response, request):
                with st.expander(f"{item.source_label}: {item.title}"):
                    st.text(item.excerpt)
                    st.caption(evidence_security_label(item))
                    st.caption(item.provenance[0].locator or "Source record")
            if response.unavailable_capabilities:
                st.subheader("Capability gaps")
                for gap in response.unavailable_capabilities:
                    st.warning(gap)

    review_request = IntelligenceRequest(
        "Review internal proposals",
        intelligence_principal,
        intelligence_purpose,
        intelligence_domain,
        intelligence_classification,
    )
    review_items = intelligence_service.proposals_for_review(review_request)
    if review_items:
        st.subheader("Proposed actions / drafts")
    for proposal in review_items:
        with st.container(border=True):
            st.markdown(f"#### {proposal.proposed_operation}")
            st.write(proposal.rationale)
            if proposal.draft_text:
                st.markdown("**Internal draft**")
                st.text(proposal.draft_text)
            st.caption(
                f"Status: {proposal.status.value} - Not sent or executed - "
                "Separate execution authority required"
            )
            st.caption(
                f"Target capability: {proposal.target_capability} - "
                f"Risk: {proposal.risk_level} - "
                f"Hash: {proposal.proposal_hash[:12]}"
            )
            if proposal.status in {
                ActionStatus.PROPOSED,
                ActionStatus.DRAFT,
                ActionStatus.AWAITING_REVIEW,
            }:
                approve, reject, supersede = st.columns(3)
                evidence_ids = st.session_state.get("proposal_evidence", {}).get(
                    proposal.proposal_id, ()
                )
                with approve:
                    approved = st.button(
                        "Approve for future execution",
                        key=f"approve-{proposal.proposal_id}",
                        disabled=(
                            proposal.status is not ActionStatus.AWAITING_REVIEW
                            or not evidence_ids
                        ),
                    )
                with reject:
                    rejected = st.button("Reject", key=f"reject-{proposal.proposal_id}")
                with supersede:
                    superseded = st.button(
                        "Supersede", key=f"supersede-{proposal.proposal_id}"
                    )
                selected = (
                    ActionStatus.APPROVED_FOR_EXECUTION
                    if approved
                    else ActionStatus.REJECTED
                    if rejected
                    else ActionStatus.SUPERSEDED
                    if superseded
                    else None
                )
                if selected is not None:
                    try:
                        now = datetime.now(UTC)
                        intelligence_service.review_proposal(
                            proposal.proposal_id,
                            status=selected,
                            proposal_hash=proposal.proposal_hash,
                            human_review_ref=f"local-owner-ui:{now.isoformat()}",
                            now=now,
                            current_evidence_ids=tuple(evidence_ids),
                        )
                    except (KeyError, PermissionError, ValueError) as error:
                        st.error(str(error))
                    else:
                        st.rerun()

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

with knowledge_tab:
    st.caption("Structured entities extracted locally with deterministic rules.")
    if not graph_available:
        st.info("Run the local knowledge extraction pipeline to build this view.")
    else:
        category_labels = {
            "Projects": EntityType.PROJECT,
            "People": EntityType.PERSON,
            "Technologies": EntityType.TECHNOLOGY,
            "Equipment": EntityType.EQUIPMENT,
            "Sites": EntityType.SITE,
            "Clients": EntityType.CLIENT,
            "Incidents": EntityType.INCIDENT,
            "Skills": EntityType.SKILL,
        }
        selected_category = st.selectbox(
            "Category", tuple(category_labels), key="knowledge-category"
        )
        entities = graph_store.list_entities(
            category_labels[selected_category], limit=100
        )
        if not entities:
            st.info("No entities have been extracted in this category.")
        else:
            entity_labels = {
                f"{entity.canonical_name} ({entity.source_count} sources)": entity
                for entity in entities
            }
            selected_label = st.selectbox(
                "Entity", tuple(entity_labels), key="knowledge-entity"
            )
            details = graph_store.entity_details(
                entity_labels[selected_label].entity_id
            )
            if details is not None:
                st.subheader(details.entity.canonical_name)
                st.write(details.entity.summary)
                st.markdown("**Related entities**")
                if not details.related_entities:
                    st.caption("No deterministic relationships found.")
                for related in details.related_entities:
                    arrow = "→" if related.direction == "outgoing" else "←"
                    st.text(
                        f"{arrow} {related.predicate}: "
                        f"{related.entity.canonical_name} "
                        f"({related.source_count} sources)"
                    )
                st.markdown("**Supporting emails**")
                for source_key in details.source_record_keys[:20]:
                    supporting_record = store.get(source_key)
                    if supporting_record is not None:
                        _render_email_result(supporting_record)
