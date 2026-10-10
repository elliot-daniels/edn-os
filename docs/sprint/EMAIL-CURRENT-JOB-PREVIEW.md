# Current-job-aware synthetic scheduling preview

Original retained email details can become stale after a canonical correction,
source update or cancellation. The synthetic UI now reads the protected exact
source-to-job binding before planning. Cancelled/rejected work, unresolved source
changes or changed site/scope/preferredDate suppress the old email's proposal.
Unknown/corrupt binding/store and linked aliases fail closed for preview and
require current canonical review. Reading never materialises or changes a job.
The deterministic original submission receipt must agree with the source binding.
A missing or rewired binding cannot impersonate an unmaterialised/current job.

Unmaterialised partial drafts retain the existing conservative preview. A current
matching job retains existing Adelaide 10–15 weekday rules, explicit dates/night
requirements, uncertainty and calendar completeness/conflict checks. The new guard
does not infer a revised duration, silently reschedule or release reservations.
No reservation or customer appointment is created by this UI.

The regression covers protected binding/no-write reads, cancellation/rejection,
changed scheduling fields, pending sources, and the actual full app after synthetic
update/cancel APIs. Original source/history remains. Fresh AppTest is not a physical
Android interaction or host restart. No assessment/schema/frozen QA/CI/security
changes; independent exact-head Grok/Dot review and full hosted gates required.

Linux/WSL: private0700 Linux parent outside Git, `umask 077`, existing dev venv;
`python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`,
then `http://127.0.0.1:8502`. Subsequent restarts omit --initialise. Automatic mobile
update/cancel execution, reservation coupling and other documented email workflow
requirements remain open. Existing accepted b4a519b Android host and main remain
unchanged; no live Microsoft access, deployment or external AI disclosure.
