from edn.core import (
    Classification,
    EvidenceRef,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    SourceRef,
    UniversalRecordRef,
)
from edn.intelligence import (
    ContextEvidence,
    IntelligenceRequest,
    IntelligenceResponse,
)
from edn.ui.service import evidence_security_label, visible_intelligence_evidence


def _context() -> tuple[IntelligenceRequest, SecurityDomain, Classification]:
    domain = SecurityDomain("EDN", "EDN", tenant_id="tenant")
    classification = Classification("edn", "confidential", "EDN Confidential")
    principal = PrincipalContext("owner", "tenant", frozenset({domain}), True)
    return (
        IntelligenceRequest(
            "Weekly priorities",
            principal,
            Purpose("weekly", "Weekly review"),
            domain,
            classification,
        ),
        domain,
        classification,
    )


def _evidence(
    identifier: str, domain: SecurityDomain, classification: Classification
) -> ContextEvidence:
    record = UniversalRecordRef(
        SourceRef(f"source-{identifier}", "test", "instance", "Test"),
        identifier,
        domain,
        classification,
        "test-record",
    )
    return ContextEvidence(
        f"context:{identifier}",
        "test.retrieve",
        "Test",
        "Test title",
        "Test excerpt",
        1.0,
        (EvidenceRef(f"evidence-{identifier}", record),),
    )


def test_ui_filters_unauthorized_evidence_before_rendering() -> None:
    request, domain, classification = _context()
    personal = SecurityDomain("PERSONAL", "Personal", tenant_id="tenant")
    response = IntelligenceResponse(
        (),
        (
            _evidence("allowed", domain, classification),
            _evidence("blocked", personal, classification),
        ),
        (),
        (),
        "session-test",
    )

    visible = visible_intelligence_evidence(response, request)

    assert tuple(item.context_id for item in visible) == ("context:allowed",)
    assert evidence_security_label(visible[0]) == "EDN · EDN Confidential"


def test_response_exposes_capability_gaps_and_source_families() -> None:
    _, domain, classification = _context()
    response = IntelligenceResponse(
        (),
        (_evidence("calendar", domain, classification),),
        (),
        ("accounting.read:capability_not_registered",),
        "session-test",
    )

    assert response.unavailable_capabilities == (
        "accounting.read:capability_not_registered",
    )
    assert response.source_families == ("Test",)
