# Email-to-job intake and scheduling — synthetic development scope

Owner's 10 October 2026 instruction authorises bounded implementation of the
email-to-job workflow. This extends the Work Intake development exception only.
It does not activate live mailbox/calendar access, external AI disclosure,
customer communications, commercial commitments, Microsoft permission changes,
deployment replacement or main promotion.

Use existing Operations Events, Intelligence evidence/model boundaries, Calendar
contracts and protected Work Intake storage. Original email evidence is immutable;
AI estimates remain labelled derived state. Missing information does not justify
invented values or changing existing approval/export security gates. Drafts remain
durable and resume after owner answers. Completed jobs retain exact revision/hash
approval semantics. Source replay, forwards and recipient copies need source-bound
receipts; ambiguous associations must not mutate another customer's job.

First bounded component: pure provisional scheduling, no transport. Adelaide
local window is 10:00–15:00, weekdays, with all travel/preparation occupancy inside
that window. Conservative default buffers are 30 minutes before and after, stated
as planning defaults rather than verified travel facts. Jobs are never split.
Explicit date/time remains a constraint, conflicts do not silently move it.
Unknown duration/site may yield a proposal but cannot qualify for reservation.
Calendar coverage must be complete and checked within five minutes. Filtered EDN
events alone do not prove full availability: excluded commitments, unavailable
sources or incomplete pagination require unknown coverage. Holidays/customer
unavailability must be represented by blocking calendar commitments.

Reservation identity is stable per job, including rescheduling. Every future
internal booking must be labelled Provisional — Awaiting Confirmation. A planner
result is not a booking: the workflow must atomically recheck current commitments
before publishing a synthetic reservation. Live reservation would require fresh
scoped authority and review; no live writer exists in this component.

Acceptance includes earliest unsplit fit, buffers/conflicts, explicit-date
preservation, weekend/all-day handling, stale/incomplete reads, UTC/Adelaide DST,
uncertain proposals and replay identity. Further bounded components will supply
classification/extraction, durable partial drafts, answer-resume/update/cancel,
synthetic reservation transactions and mobile presentation. Independent Grok QA
and Dot exact-head technical acceptance precede accepted development integration.
The existing private Android demo remains on its accepted application tree.
