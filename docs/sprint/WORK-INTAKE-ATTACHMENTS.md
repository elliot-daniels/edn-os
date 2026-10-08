# Work Intake protected supporting attachments

Bounded issue: local attachment originals for the owner-requested Work Intake MVP.
Base `26eb5466e15dfccc6280d9aa8296b05d57928928`, with the shared protected core
helper dependency `d933acec5a2d3a01a47c36838af0f2b83334f8f1` and shared format
codec `40e87afd9b52926d9beade0eb0cbfb294705788b` normally merged into
this feature branch. This branch owns only its attachment module, tests and this
evidence document; the shared security helper belongs to the core PR.

## Current owner-approved boundary

Protected storage requires Linux or WSL. Native Windows and other platforms fail
before filesystem inspection, create, chmod or writes. Pure uploaded-byte format
validation can run on unsupported platforms without creating storage. Existing
runtime directories must be owned by the runtime UID and mode 0700; ancestry is
validated by the shared helper. Every new directory is 0700, every original,
metadata/receipt and lock file is owned regular mode 0600 with one link. Symlinks,
hardlinks, unsafe ownership/modes and untrusted ancestry fail closed. No existing
ACL/permissions are broadened and no platform security tests are skipped.

Allowed: PDF, PNG, JPEG, DOCX, EML and TXT. Exact decimal bounds are **20,000,000
bytes per file** and **100,000,000 bytes per request**, up to **100 files**. These
are MB limits, not MiB. Stream and filesystem reads request a fixed cap plus one
overflow byte. Filenames become normalized length-limited display basenames only;
canonical request/attachment UUIDs and fixed names determine storage paths.

The single shared intake_formats codec is used by writer and backend evidence
approval/export; neither layer keeps a weaker duplicated format gate.
PDF/PNG/JPEG validation checks matching suffixes and bounded format envelopes;
it is not full rendering or a malware-clean guarantee. DOCX ZIP validation bounds
members (2,000), expanded bytes (20,000,000), compression ratio (100), supported
compression methods and CRC reads; unsafe paths, duplicate aliases, encryption,
symlink/nonregular members, known VBA/macro declarations and XML DTD/entities are
rejected. XML must be strict UTF-8, with depth 128 and 100,000-node bounds. No archive is extracted to
filesystem and no macro executes. TXT/EML require strict UTF-8 text without binary
control bytes; EML additionally needs valid message headers with a 65,536-byte
header cap. No OCR, automatic document extraction, network or AI dispatch occurs.

## API and atomic capacity accounting

`IntakeAttachmentStore(root)` requires an existing selected private directory
outside Git. `attach(request_id, filename, bytes)` and bounded `attach_stream`
return immutable metadata. `get(request_id, attachment_id)` and
`read(request_id, attachment_id)` support restart and bounded integrity checks.
Metadata keys are exactly `attachment_id`, `request_id`, `original_name`,
`media_type`, `size_bytes`, `sha256`; no filesystem path is serialized.

A per-request owner-only flock serializes uploads across processes. An atomic
0600 receipt reserves the full file size **before** any original bytes are
written. Original/metadata bytes first enter exclusive private pending files and
are fully fsynced before renameat2 NO_REPLACE publishes their final names. Open
parent directory descriptors are fsynced; atomic receipt replacement marks
completion only after both files are durable. Interrupted original or metadata
staging cannot expose a partial final file through the API. Existing originals
and attachment records are never replaced.
No hard-link publication is used. The receipt has a 65,536-byte bound.

Incomplete/unbound originals still consume their full reservation. Unknown
physical folders/files, oversized originals, mismatched metadata/receipt sizes
or quota tampering fail closed rather than being silently adopted. Failed writes
or hard interruption may leave reserved/incomplete entries or pending receipt
files requiring owner-led recovery; they are not returned as completed uploads.
There is no automatic garbage collection, deletion or stale finalization.

Attachment persistence precedes the separate request-revision transaction.
The core must bind metadata to the matching request, invalidate approval when
attachments change and preserve local provenance. The UI must verify `read` on
associated originals before approval/export; approved metadata alone does not
prove current bytes. Ancestry is opened component-by-component with O_DIRECTORY/O_NOFOLLOW. Root,
request and attachment operations use owned open directory descriptors and
dir_fd-relative opens/mkdir/rename/unlink, including receipt replacement and
no-clobber publication. Replacing a validated parent pathname with an outside
symlink cannot redirect writes: they remain on the already-authorized inode or
fail closed. Reads anchor receipt, metadata and bytes in one descriptor walk.
These controls do not establish volume encryption.

## Export and verification

The inspected website contract has no attachment list fields/upload flow.
Attachment metadata remains local and separate from SharePoint export fields;
dry runs must not claim binary upload, synchronization or external writes.
No website schema, production root, source permission or credential changes.

Synthetic tests cover supported/hostile formats, exact bounds, native Windows
refusal before any I/O, restart/hash verification, modes/ownership/link rejection,
failed conservative reservations, unknown physical originals, tampered quotas,
one-hundred-file bound and concurrent processes competing for the last 20 MB.
Actual root/request/attachment swaps after descriptor validation reproduce the
former outside-root race and assert the outside sentinel is unchanged. Disk
failures and subprocess hard exits during partial original/metadata staging
assert final partial paths are absent and evidence is unreadable via the API.
Linux executes every positive protected-storage test. Windows storage cases assert
the explicit unsupported no-creation contract and return; these are not skips.
Local native checks verify pure formats/refusal only, not positive Linux runtime
acceptance. Required full hosted Linux/Windows CI and independent QA are recorded
against the exact PR head. Revert the feature code to remove this API; retained
private files require an owner-approved recovery/discard decision, not automatic
migration or permission changes.
