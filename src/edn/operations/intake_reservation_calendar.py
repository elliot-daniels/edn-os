"""Read-only synthetic calendar projection of verified durable local holds."""

from dataclasses import replace
from datetime import datetime

from edn.connectors.microsoft_calendar.models import CalendarEvent
from edn.core import Classification, SecurityDomain
from edn.operations.intake import IntakeError, IntakeStore, _digest
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.operations.intake_scheduling import PROVISIONAL, CalendarSnapshot


def include_local_reservations(
    snapshot: CalendarSnapshot,
    reservations: SyntheticReservationStore,
    requests: IntakeStore,
) -> CalendarSnapshot:
    """Validate every active binding under job-then-ledger locks; never release it.

    A stale or unverifiable hold makes availability unknown, not free. This is
    snapshot evidence only, not an atomic booking or job/reservation transaction.
    """
    if not snapshot.scope_ref.startswith("synthetic-"):
        raise IntakeError("Only synthetic calendar projection is permitted")
    busy = []
    with requests._connect() as jobs, reservations._backend._connect() as ledger:
        for item in reservations._rows(ledger).values():
            if item["state"] == "cancelled":
                continue
            job_id = item["job_id"]
            job = requests._get(jobs, job_id)
            last = item["history"][-1]
            if (
                requests._canonical(jobs, job_id) != job_id
                or job.state not in {"draft", "approved"}
                or job.source_pending
                or job.revision != last["job_revision"]
                or _digest(job.fields, job.attachments) != last["job_hash"]
            ):
                raise IntakeError("Local reservation requires canonical job review")
            plan = last["plan"]
            busy.append(
                CalendarEvent(
                    job_id,
                    "synthetic-local-reservations",
                    PROVISIONAL,
                    datetime.fromisoformat(plan["occupied_start"]),
                    datetime.fromisoformat(plan["occupied_end"]),
                    "Australia/Adelaide",
                    "synthetic@example.test",
                    (),
                    None,
                    False,
                    None,
                    None,
                    snapshot.checked_at,
                    (),
                    SecurityDomain("EDN", "EDN synthetic"),
                    Classification("edn", "internal", "Synthetic", 1),
                )
            )
    return replace(snapshot, events=(*snapshot.events, *busy))
