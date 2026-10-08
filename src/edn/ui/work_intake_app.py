"""Local Work Intake demo. No Microsoft client or live write path."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st

from edn.operations.intake import (
    SERVICES,
    URGENCY_LEVELS,
    IntakeCommitUncertainError,
    IntakeRequest,
    IntakeStore,
)
from edn.operations.intake_attachments import IntakeAttachmentStore
from edn.operations.intake_projection import prepare_envelope
from edn.operations.intake_security import require_supported_platform
from edn.operations.intake_sync import SyntheticSyncStore

LABELS = {
    "contactName": "Contact name",
    "company": "Company",
    "email": "Email",
    "phone": "Phone",
    "siteLocation": "Site / location",
    "serviceRequired": "Service required",
    "preferredDate": "Preferred date (YYYY-MM-DD, optional)",
    "urgency": "Urgency",
    "jobDescription": "Job description",
    "reference": "Customer reference",
}
STATUS = {
    "not_synced": "Not sent to SharePoint",
    "dry_run": "Dry-run record prepared · not sent to SharePoint",
}


def request_fields(values: dict[str, str], key: str) -> dict[str, str]:
    result = {}
    for name, label in LABELS.items():
        value = values.get(name, "")
        if name in {"serviceRequired", "urgency"}:
            options = SERVICES if name == "serviceRequired" else URGENCY_LEVELS
            result[name] = st.selectbox(
                label,
                options,
                index=options.index(value) if value in options else 0,
                key=f"{key}-{name}",
            )
        elif name == "jobDescription":
            result[name] = st.text_area(label, value, key=f"{key}-{name}")
        else:
            result[name] = st.text_input(label, value, key=f"{key}-{name}")
    return result


def attach_file(
    store: IntakeStore,
    files: IntakeAttachmentStore,
    request: IntakeRequest,
    filename: str,
    payload: bytes,
) -> None:
    metadata = files.attach(request.request_id, filename, payload).to_dict()
    if metadata in request.attachments:
        return
    store.update(
        request.request_id,
        request.revision,
        request.fields,
        attachments=(*request.attachments, metadata),
    )


def verify_supporting_files(root: Path, request: IntakeRequest) -> None:
    if not request.attachments:
        return
    files = IntakeAttachmentStore(root / "attachments")
    for metadata in request.attachments:
        identifier = metadata["attachment_id"]
        if not isinstance(identifier, str):
            raise ValueError("Invalid supporting-file identity")
        if files.get(request.request_id, identifier).to_dict() != metadata:
            raise ValueError("Supporting-file metadata changed")
        files.read(request.request_id, identifier)


def render_manual_creation(store: IntakeStore, reader: IntakeStore) -> None:
    """A malformed intent blocks creation without hiding the readable queue."""
    with st.expander("Create a work request", expanded=True):
        try:
            intent = reader.current_submission()
            if intent is None or st.button("Start a new work request"):
                intent = store.begin_submission()
        except (ValueError, sqlite3.Error, OSError):
            st.error("Submission identity is unavailable. Creation is blocked.")
            return
        st.caption(f"Durable submission identity: {intent.submission_id}")
        if intent.request_id:
            st.info(
                "This submission is already saved. Review it in the queue, or start "
                "a new work request. Retrying preserves the existing request."
            )
        with st.form(f"create-request-{intent.submission_id}", clear_on_submit=False):
            fields = request_fields(
                intent.fields or {}, f"create-{intent.submission_id}"
            )
            create = st.form_submit_button("Save request locally")
        if create:
            st.session_state.pop("prepared-record", None)
            try:
                request = store.create(fields, submission_id=intent.submission_id)
                st.session_state["selected-request"] = request.request_id
                st.session_state["queue-offset"] = 0
                st.success("Request saved locally. Review it before approval.")
            except (ValueError, sqlite3.Error, OSError):
                st.error(
                    "Saving was not confirmed. Keep your entered information and "
                    "check required fields and local storage."
                )


def render() -> None:
    st.set_page_config(page_title="EDN OS Work Intake", page_icon="📥", layout="wide")
    st.title("Work Intake")
    st.caption("Local demo · synthetic data only · SharePoint dry run")
    try:
        require_supported_platform()
    except ValueError:
        st.error(
            "Protected Work Intake requires Linux or WSL. "
            "No intake storage has been opened."
        )
        return
    setting = os.environ.get("EDN_INTAKE_ROOT", "")
    root = Path(setting)
    if not setting or not root.is_absolute() or not root.is_dir():
        st.info("Start the demo with a configured local intake folder.")
        return
    path = root / "requests.db"
    if not path.is_file():
        st.info("Initialise the demo store before opening Work Intake.")
        return
    store = IntakeStore(path, evidence_root=root / "attachments")
    reader = IntakeStore(path, read_only=True, evidence_root=root / "attachments")
    with st.expander("Synthetic automated intake"):
        st.caption("Import a synthetic website contract JSON. No live source is read.")
        with st.form("synthetic-intake"):
            external_id = st.text_input("Synthetic source request ID")
            contract_upload = st.file_uploader(
                "Synthetic request contract", type=["json"]
            )
            import_request = st.form_submit_button("Import synthetic request")
        if import_request:
            st.session_state.pop("prepared-record", None)
            try:
                if contract_upload is None:
                    raise ValueError("No synthetic contract selected")
                contract_upload.seek(0)
                raw = contract_upload.read(32769)
                if len(raw) > 32768:
                    raise ValueError("Synthetic contract exceeds its bound")
                contract = json.loads(raw)
                if not isinstance(contract, dict):
                    raise ValueError("Synthetic contract must be an object")
                request = store.import_contract(
                    contract,
                    external_id,
                    source_identity={
                        "source_system": "sharepoint",
                        "source_account": "synthetic-local-account",
                        "site_id": "synthetic-local-site",
                        "list_id": "synthetic-job-requests",
                        "native_item_id": external_id,
                    },
                )
                st.session_state["selected-request"] = request.request_id
                st.session_state["queue-offset"] = 0
                st.success(
                    "Synthetic request is in the local queue. Review before approval."
                )
            except (ValueError, sqlite3.Error, OSError, RecursionError):
                st.error(
                    "Synthetic import is unconfirmed. Reload before retrying, "
                    "then check the contract, source ID and local demo store."
                )
    render_manual_creation(store, reader)
    st.subheader("Intake queue")
    offset = st.session_state.get("queue-offset", 0)
    try:
        page = reader.list_requests_with_diagnostics(limit=50, offset=offset)
        requests = page.requests
    except (ValueError, sqlite3.Error, OSError):
        st.error(
            "The local intake queue is unavailable. Synchronisation is unconfirmed."
        )
        return
    previous, following = st.columns(2)
    if previous.button("Previous requests", disabled=offset == 0):
        st.session_state["queue-offset"] = max(0, offset - 50)
        st.rerun()
    if following.button("Next requests", disabled=len(requests) + page.malformed < 50):
        st.session_state["queue-offset"] = offset + 50
        st.rerun()
    st.caption(f"{len(requests)} readable requests on this page · 50 per page")
    if page.malformed:
        st.warning(
            f"{page.malformed} malformed request(s) isolated on this page. "
            "Other requests remain available."
        )
    if not requests:
        st.info("No requests on this page.")
        return
    by_id = {request.request_id: request for request in requests}
    selected = st.session_state.get("selected-request")
    if selected not in by_id:
        selected = requests[0].request_id
    request_id = st.selectbox(
        "Select a request",
        tuple(by_id),
        index=tuple(by_id).index(selected),
        format_func=lambda value: (
            f"{by_id[value].fields['contactName']} · "
            f"{by_id[value].fields['siteLocation']}"
            f" · {by_id[value].state} · {value[:8]}"
        ),
    )
    request = by_id[request_id]
    st.session_state["selected-request"] = request_id
    st.subheader("Review and correct")
    st.text(f"Local request: {request_id} · revision {request.revision}")
    st.write(f"Review: {request.state.capitalize()}")
    st.caption(STATUS.get(request.sync_status, "Synchronisation status unknown"))
    st.caption(f"Source: {request.source_type}")
    try:
        provenance = reader.source_provenance(request_id)
        linked_alias = provenance.get("linked_alias") is True
    except (ValueError, sqlite3.Error, OSError):
        st.error("Source identity is unconfirmed. Review actions are blocked.")
        return
    with st.expander("Source identity and work linkage"):
        st.json(provenance)
    if linked_alias:
        st.warning(
            "This is a linked source record. Edit and approve its canonical work "
            f"request: {provenance['canonical_work_id']}"
        )
    if request.source_pending:
        st.warning("Source content changed. Resolve it explicitly before approval.")
        try:
            st.json(reader.source_snapshot(request_id))
        except (ValueError, sqlite3.Error, OSError):
            st.error("Changed source details are unavailable. Resolution is blocked.")
            return
        with st.form(f"source-resolution-{request_id}-{request.revision}"):
            resolution = st.selectbox(
                "Source resolution", ("keep_local", "apply_source")
            )
            source_reason = st.text_input("Reason for source resolution")
            resolve_source = st.form_submit_button("Resolve changed source")
        if resolve_source:
            st.session_state.pop("prepared-record", None)
            try:
                store.resolve_source_change(
                    request_id,
                    request.revision,
                    decision=resolution,
                    reason=source_reason,
                )
                st.rerun()
            except (ValueError, sqlite3.Error, OSError):
                st.error(
                    "Source resolution is unconfirmed. Check the reason and revision."
                )
    try:
        duplicates = reader.duplicate_candidates(request_id)
    except (ValueError, sqlite3.Error, OSError):
        st.error("Duplicate status is unconfirmed. Approval and export are blocked.")
        return
    if duplicates:
        st.warning("Possible duplicate work requires an explicit decision.")
        with st.form(f"duplicate-resolution-{request_id}-{request.revision}"):
            other_id = st.selectbox(
                "Possible duplicate request",
                tuple(item.request_id for item in duplicates),
            )
            duplicate_choice = st.selectbox(
                "Duplicate resolution", ("distinct", "same_work")
            )
            duplicate_reason = st.text_input("Reason for duplicate resolution")
            resolve_duplicate = st.form_submit_button("Record duplicate decision")
        if resolve_duplicate:
            st.session_state.pop("prepared-record", None)
            try:
                store.resolve_duplicate(
                    request_id,
                    other_id,
                    request.revision,
                    decision=duplicate_choice,
                    reason=duplicate_reason,
                )
                st.rerun()
            except (ValueError, sqlite3.Error, OSError):
                st.error(
                    "Duplicate resolution is unconfirmed. "
                    "Check the decision and revision."
                )
    with st.form(f"review-{request_id}-{request.revision}"):
        corrected = request_fields(
            request.fields, f"review-{request_id}-{request.revision}"
        )
        save = st.form_submit_button(
            "Save corrections",
            disabled=request.state not in {"draft", "approved"} or linked_alias,
        )
    if save:
        st.session_state.pop("prepared-record", None)
        try:
            store.update(request_id, request.revision, corrected)
            st.rerun()
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error("Corrections are unconfirmed. Reload before retrying.")
            if isinstance(error, IntakeCommitUncertainError):
                st.stop()
    st.subheader("Supporting files")
    files_valid = True
    try:
        verify_supporting_files(root, request)
    except (ValueError, sqlite3.Error, OSError):
        files_valid = False
        st.error(
            "Supporting-file integrity is unconfirmed. "
            "Approval and dry-run preparation are blocked."
        )
    st.caption(
        "PDF, PNG, JPEG, DOCX, EML or TXT · 20 MB each / 100 MB per request "
        "· local only · no OCR extraction"
    )
    for metadata in request.attachments:
        st.text(
            f"{metadata['original_name']} · {metadata['size_bytes']} bytes "
            "· recorded locally"
        )
    with st.form(f"attachment-{request_id}-{request.revision}"):
        upload = st.file_uploader(
            "Supporting document or photo",
            type=["pdf", "jpg", "jpeg", "png", "docx", "eml", "txt"],
        )
        add = st.form_submit_button(
            "Save supporting file",
            disabled=request.state not in {"draft", "approved"} or linked_alias,
        )
    if add:
        st.session_state.pop("prepared-record", None)
        if upload is None:
            st.error("Select a supporting file first.")
        else:
            try:
                attach_file(
                    store,
                    IntakeAttachmentStore(root / "attachments"),
                    request,
                    upload.name,
                    upload.getvalue(),
                )
                st.rerun()
            except (ValueError, sqlite3.Error, OSError):
                st.error(
                    "File association is unconfirmed. Reload before retrying, "
                    "then review local storage and file type."
                )
    st.caption("Corrections and added files require a fresh approval.")
    st.caption(
        "Single local operator · self-approval is recorded for the exact version."
    )
    with st.expander("Request lifecycle"):
        st.caption("Rejected requests can reopen. Cancelled requests are terminal.")
        with st.form(f"lifecycle-{request_id}-{request.revision}"):
            target = st.selectbox("Action", ("rejected", "cancelled", "draft"))
            reason = st.text_input("Reason for this decision")
            decide = st.form_submit_button(
                "Record lifecycle decision", disabled=request.state == "cancelled"
            )
        if decide:
            st.session_state.pop("prepared-record", None)
            try:
                store.transition(request_id, request.revision, target, reason=reason)
                st.rerun()
            except (ValueError, sqlite3.Error, OSError):
                st.error(
                    "Decision was not confirmed. Check the action, reason and revision."
                )
    if request.approval_actor:
        st.caption(
            f"Recorded self-approval: {request.approval_actor} · "
            f"{request.approval_timestamp} · revision {request.approved_revision}"
        )
    history_valid = True
    with st.expander("Review and approval history"):
        try:
            history = reader.audit_history(request_id)
            if not history:
                st.caption("No approval has been recorded.")
            for decision in history:
                st.caption(
                    f"{str(decision['decision']).replace('_', ' ')} · "
                    f"revision {decision['revision']} · "
                    f"{decision['actor']} · {decision['decided_at']}"
                )
                st.code(str(decision["content_hash"]), language=None)
                if decision.get("reason"):
                    st.text(f"Reason: {decision['reason']}")
        except (ValueError, sqlite3.Error, OSError):
            history_valid = False
            st.error(
                "Approval history is unavailable; approval evidence is unconfirmed."
            )
    if st.button(
        "Approve reviewed request (self-approval)",
        disabled=request.state != "draft"
        or not files_valid
        or not history_valid
        or request.source_pending
        or bool(duplicates)
        or linked_alias,
    ):
        st.session_state.pop("prepared-record", None)
        try:
            verify_supporting_files(root, request)
            store.approve(request_id, request.revision)
            st.rerun()
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error("Approval is unconfirmed. Reload and review the current revision.")
            if isinstance(error, IntakeCommitUncertainError):
                st.stop()
    if st.button(
        "Prepare SharePoint record (dry run)",
        disabled=request.state != "approved"
        or not files_valid
        or not history_valid
        or request.source_pending
        or bool(duplicates)
        or linked_alias,
    ):
        st.session_state.pop("prepared-record", None)
        try:
            verify_supporting_files(root, request)
            payload = prepare_envelope(
                store.export(request_id, request.revision), request.attachments
            )
            st.session_state["prepared-record"] = payload
            st.rerun()
        except (ValueError, sqlite3.Error, OSError):
            st.error("Dry-run preparation failed. Nothing was sent to SharePoint.")
    payload = st.session_state.get("prepared-record")
    if (
        isinstance(payload, dict)
        and payload.get("request_id") == request_id
        and payload.get("revision") == request.revision
        and request.state == "approved"
        and files_valid
        and history_valid
        and not request.source_pending
        and not duplicates
        and not linked_alias
    ):
        st.success("Reviewed dry-run record. Nothing has been sent.")
        st.json(payload["fields"])
        st.download_button(
            "Download reviewed dry-run record and evidence manifest",
            json.dumps(payload, indent=2),
            file_name=f"intake-{request_id}-dry-run.json",
            mime="application/json",
        )
        if payload.get("operation") == "reference_existing":
            st.info(
                "This source item already exists in the synthetic source. The "
                "dry run references its identity and does not propose another create."
            )
            st.json(payload["target"])
        else:
            st.download_button(
                "Download SharePoint create payload",
                json.dumps({"fields": payload["fields"]}, indent=2),
                file_name=f"intake-{request_id}.json",
                mime="application/json",
            )
        st.subheader("Synthetic synchronisation")
        st.caption(
            "Private local fake transport. Every status below is synthetic; "
            "nothing is sent to Microsoft."
        )
        try:
            sync = SyntheticSyncStore(root / "synthetic-sync")
        except (ValueError, OSError):
            sync = None
            st.error("Synthetic synchronisation status is unconfirmed.")
        if sync is not None:
            lookup_failed = False
            unresolved: tuple[dict[str, Any], ...] = ()
            try:
                receipt = sync.get(payload)
                unresolved = sync.unconfirmed(payload)
            except (ValueError, OSError):
                receipt = None
                lookup_failed = True
                st.error("Synthetic status is unconfirmed. Reconcile before retrying.")
            if receipt is None and not lookup_failed:
                st.info(
                    "Synthetic transport: not attempted · live SharePoint: not synced"
                )
            elif receipt is not None:
                st.write(
                    f"Synthetic transport: {receipt['status']} · "
                    "live SharePoint: not synced"
                )
                st.caption(f"Attempt {receipt['attempt']} · {receipt['timestamp']}")
            outcome = st.selectbox(
                "Simulated transport outcome", ("success", "failed", "unknown")
            )
            older = tuple(
                item
                for item in unresolved
                if item["identity"]["revision"] != request.revision
            )
            if older:
                st.warning(
                    "An earlier approved version is unconfirmed. "
                    "Reconcile it before another delivery."
                )
                by_key = {item["identity"]["idempotency_key"]: item for item in older}
                selected_key = st.selectbox(
                    "Unconfirmed prior version",
                    tuple(by_key),
                    format_func=lambda key: (
                        f"Revision {by_key[key]['identity']['revision']} · "
                        f"hash {by_key[key]['identity']['content_hash'][:12]}"
                    ),
                )
                if st.button("Reconcile prior version"):
                    try:
                        sync.reconcile_record(payload, by_key[selected_key]["identity"])
                        st.rerun()
                    except (ValueError, OSError):
                        st.error("Prior-version reconciliation is unconfirmed.")
            unconfirmed = (
                lookup_failed
                or bool(unresolved)
                or (
                    receipt is not None
                    and receipt["status"]
                    in {
                        "pending",
                        "unknown",
                    }
                )
            )
            if st.button("Run synthetic sync", disabled=unconfirmed):
                try:
                    sync.deliver(payload, outcome)
                    st.rerun()
                except (ValueError, OSError):
                    st.error("Synthetic attempt is unconfirmed. Reload and reconcile.")
            if st.button(
                "Reconcile synthetic attempt",
                disabled=receipt is None and not lookup_failed,
            ):
                try:
                    sync.reconcile(payload)
                    st.rerun()
                except (ValueError, OSError):
                    st.error("Synthetic reconciliation is unconfirmed.")


if __name__ == "__main__":
    render()
