# Work Intake local supporting attachment foundation

Issue: intake attachments, a bounded foundation for the owner-requested local Work
Intake demo. Base `26eb5466e15dfccc6280d9aa8296b05d57928928`. Only the new
attachment module, synthetic tests and this evidence document are in scope.

`IntakeAttachmentStore(root)` requires an existing absolute operator-selected
runtime directory outside Git. `attach(request_id, filename, payload)` accepts
canonical request UUIDs and original bytes; `get(request_id, attachment_id)` and
`read(request_id, attachment_id)` support restart retrieval and integrity checks.
`attach_stream` requests at most 10 MiB plus one overflow byte from ordinary
file/BytesIO upload streams. Every filesystem read has a fixed byte bound.

PDF, JPEG and PNG files have a per-file 10 MiB cap and matching suffix/envelope
checks. This is bounded file-type validation, not complete document parsing or
malware scanning. Files remain untrusted originals: this module does not execute,
render, extract, upload, decrypt or send them to any external service. DOCX was
considered against the existing local parser and is excluded from this first
foundation. No OCR or automatic PDF extraction is claimed or required.

Filename input becomes a normalized, length-limited display basename only.
Storage names are canonical request/attachment UUIDs with fixed original and
metadata names. Original bytes are exclusively created and fsynced; completed
metadata is published atomically without replacing an existing target (Windows
rename refuses existing targets, POSIX hard-link publication is exclusive).
Symlinks/Windows reparse points, including existing ancestors, fail closed. Reads
validate record identity, exact metadata shape, sizes, content hashes and format
envelopes. Fixed UI errors exclude underlying paths or exception/source contents.

Metadata fields are exactly `attachment_id`, `request_id`, `original_name`,
`media_type`, `size_bytes`, `sha256`. No filesystem path is serialized. The intake
workflow must bind these metadata records to its matching request/revision and
invalidate approval when that set changes. The core caps ten associated files.
Before review approval or dry-run export, the UI must call `read` for associated
attachments to check stored bytes independently of the approved metadata hash.

Attachment files are persisted before the separate workflow transaction. If
metadata publication or workflow association fails, unbound/incomplete originals
may remain; they are not an approved request or a successful sync. No background
cleanup or retention deletion is implemented. Owner-controlled recovery can
inspect/discard synthetic demo data without changing the immutable records.

The website's inspected request contract has no attachment fields/upload flow.
Local attachment metadata remains separate from SharePoint fields and the dry
run must never claim it was uploaded or synchronized. No source permissions,
credentials, website contract, production root/ACL or cloud behavior changes.
As elsewhere, protected operator-owned parent directories are a prerequisite;
path/link checks do not defeat a hostile process racing parent-directory changes
or establish encryption/ACL protection by themselves.

Synthetic acceptance covers supported files, bounded bytes/streams, normalized
names, traversal/identity rejection, unknown/mismatched types, restart/hash checks,
no overwrite, corrupted metadata/bytes, ancestor/file reparse points, missing/Git
roots and interrupted metadata publication. Full check results are recorded in
the PR. Revert the feature commit to remove this foundation; no existing Event
schema or runtime migration is involved. Hosted Linux runtime CI remains required.
