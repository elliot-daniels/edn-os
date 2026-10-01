from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from tests.connectors.local_files.test_local_files import (
    NOW,
    authorized_request,
    context,
    discover_direct,
    evaluator,
    make_config,
    registry,
)

from edn.connectors.errors import SourceUnavailableError
from edn.connectors.local_files import (
    DocumentExtractionError,
    LocalFilesConnector,
    extract_document,
)
from edn.core import Purpose
from edn.intelligence import (
    ContextAssembler,
    IntelligenceRequest,
    LocalFilesEvidenceAdapter,
)


def _write_pdf(path: Path, text: str, *, encrypted: bool = False) -> None:
    encryption = b" /Encrypt 3 0 R" if encrypted else b""
    stream = f"BT ({text}) Tj ET".encode()
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj << /Length "
        + str(len(stream)).encode()
        + encryption
        + b" >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF\n"
    )


def _write_docx(path: Path, paragraphs: tuple[str, ...]) -> None:
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)


def test_synthetic_pdf_and_docx_extract_bounded_structural_provenance(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "approval.pdf"
    docx = tmp_path / "project.docx"
    _write_pdf(pdf, "Client approval due Friday")
    _write_docx(docx, ("Project Juniper", "Decision required"))

    pdf_result = extract_document(pdf)
    docx_result = extract_document(docx)

    assert pdf_result.record_type == "document.pdf"
    assert pdf_result.sections[0].locator == "page:1"
    assert "approval due Friday" in pdf_result.text
    assert docx_result.record_type == "document.docx"
    assert tuple(item.locator for item in docx_result.sections) == (
        "paragraph:1",
        "paragraph:2",
    )


def test_malformed_and_encrypted_documents_fail_closed(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.pdf"
    encrypted = tmp_path / "encrypted.pdf"
    broken_docx = tmp_path / "broken.docx"
    malformed.write_bytes(b"not a pdf")
    _write_pdf(encrypted, "secret", encrypted=True)
    broken_docx.write_bytes(b"not a zip")

    for path in (malformed, encrypted, broken_docx):
        with pytest.raises(DocumentExtractionError):
            extract_document(path)


def test_connector_ingests_pdf_and_docx_with_typed_provenance(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_pdf(root / "approval.pdf", "Client approval due Friday")
    _write_docx(root / "project.docx", ("Project Juniper", "Decision required"))
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidates = discover_direct(connector)
    scope = tuple(item.resource_id for item in candidates)

    result = connector.ingest(
        authorized_request(connector, "local-files.ingest", "ingest", scope)
    )

    assert {item.record_type for item in result.records} == {
        "document.pdf",
        "document.docx",
    }
    evidence = connector.evidence(scope)
    assert {item.locator for item in evidence} == {"pages", "document-structure"}
    assert {item.transformation_id for item in evidence} == {
        "local-files.pdf",
        "local-files.docx",
    }


def test_connector_wraps_unsafe_extraction_as_source_unavailable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_pdf(root / "encrypted.pdf", "secret", encrypted=True)
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidate = discover_direct(connector)[0]

    with pytest.raises(SourceUnavailableError, match="extracted safely"):
        connector.ingest(
            authorized_request(
                connector,
                "local-files.ingest",
                "ingest",
                (candidate.resource_id,),
            )
        )


def test_ingested_documents_are_retrievable_through_context_assembly(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_pdf(root / "approval.pdf", "Client approval due Friday")
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidate = discover_direct(connector)[0]
    connector.ingest(
        authorized_request(
            connector,
            "local-files.ingest",
            "ingest",
            (candidate.resource_id,),
        )
    )
    principal, domain, classification = context(connector.config)
    request = IntelligenceRequest(
        "client approval",
        principal,
        Purpose("local-files-test", "Synthetic Local Files test"),
        domain,
        classification,
        (candidate.resource_id,),
    )
    adapter = LocalFilesEvidenceAdapter(connector, (candidate.resource_id,))
    assembler = ContextAssembler(
        registry(connector),
        evaluator("local-files.search", "search", domain.domain_id),
        (adapter,),
    )

    assembled = assembler.assemble(request, now=NOW)

    assert len(assembled.evidence) == 1
    assert assembled.evidence[0].source_label == "Local document"
    assert "approval due Friday" in assembled.evidence[0].excerpt
    assert assembled.evidence[0].provenance[0].record.security_domain == domain
