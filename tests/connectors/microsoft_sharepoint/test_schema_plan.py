from urllib.parse import parse_qs, urlsplit

import pytest

from edn.connectors.microsoft_sharepoint.schema_plan import (
    HISTORICAL_SITE_GUID,
    HOST,
    SITE_URL,
    list_schema_requests,
    permission_readiness,
    site_identity_request,
)

SITE_ID = f"{HOST},{HISTORICAL_SITE_GUID},00000000-0000-0000-0000-000000000001"


def test_inert_plan_is_exact_bounded_metadata_only():
    requests = (
        site_identity_request(),
        *list_schema_requests(resolved_site_id=SITE_ID, resolved_web_url=SITE_URL),
    )
    assert len(requests) == 7
    for request in requests:
        url = urlsplit(request.url)
        assert request.method == "GET" and not request.follow_continuation
        assert url.netloc == "graph.microsoft.com"
        assert "/items" not in url.path and "/permissions" not in url.path
        assert "$expand" not in parse_qs(url.query)
        assert request.maximum_records <= 100
    assert sum("/columns?" in request.url for request in requests) == 3


@pytest.mark.parametrize(
    "identity,url",
    [
        ("bare-guid", SITE_URL),
        (SITE_ID, "https://other.example/site"),
        (
            SITE_ID.replace(
                HISTORICAL_SITE_GUID, "00000000-0000-0000-0000-000000000002"
            ),
            SITE_URL,
        ),
        (SITE_ID.replace(HOST, "other.sharepoint.com"), SITE_URL),
        (SITE_ID + "/items", SITE_URL),
    ],
)
def test_plan_fails_on_unverified_site_or_path_injection(identity, url):
    with pytest.raises(ValueError):
        list_schema_requests(resolved_site_id=identity, resolved_web_url=url)


def test_existing_pilot_scopes_are_insufficient_and_selected_scope_is_not_a_grant():
    assert (
        permission_readiness(frozenset({"User.Read", "Mail.Read", "Calendars.Read"}))
        == "blocked_missing_sharepoint_read_permission"
    )
    assert permission_readiness(frozenset({"Sites.Selected"})).startswith("unverified_")
