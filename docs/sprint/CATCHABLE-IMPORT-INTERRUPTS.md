# Catchable import interruptions

When Python receives KeyboardInterrupt or SystemExit during a tracked mailbox
import, it now records the same incomplete outcome as other import errors before
re-raising the original termination. No later page/mailbox is attempted because
termination still propagates. The reason is the fixed import_error code, without
source/exception content. No progress means failed; progress means partial.

Hard process termination can still leave in_progress, shown as unconfirmed
completion after restart. This change neither guesses active importer ownership
nor repairs Event/checkpoint commit gaps. Those limitations remain explicit OCT-06
requirements pending their original detailed QA criteria. No scheduler, automatic
source retry, schema change or real import is introduced.

Rollback: revert the handler change; retained outcomes use the existing version1
schema. Synthetic restart/replay tests preserve original Events and interrupted
attempts, and distinguish catchable termination from unfinalized attempts.
