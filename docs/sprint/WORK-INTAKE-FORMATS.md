# Shared intake evidence formats

This pure codec is shared by local attachment acceptance and backend evidence
verification. It performs no filesystem operations, extraction, rendering,
network calls or AI dispatch. API:
`validate_attachment_payload(filename, bytes) -> (normalized_name, media_type)`;
`normalize_attachment_name(filename)` produces display metadata only.
`IntakeAttachmentError` exposes fixed source-free errors.

Supported: PDF, PNG, JPEG, DOCX, EML and TXT. Exact decimal caps are
20,000,000 bytes/file and 100,000,000 bytes/request, with100 files/request and
65,536-byte receipts. Storage owns locked aggregate enforcement; this codec
checks the individual payload before any protected write.

PDF/images use bounded matching format envelopes, not a malware-clean claim.
DOCX validates bounded ZIP members, expansion/compression, CRC reads, paths,
symlink/nonregular entries, encryption, known VBA/macro declarations and strict
UTF-8 XML without DTD/entities, with bounded depth/node counts. TXT/EML require
strict UTF-8 without binary controls; EML headers are bounded/checked and parser
failures are fixed errors. No original bytes are transformed or macros executed.

Backend approval/export must run this same validator on descriptor-verified
stored bytes and compare normalized name/media with the approved immutable
metadata; a second weaker format gate is not an equivalent security boundary.
The protected storage/receipt/hash checks belong to the separate shared security
helper and writer. This dependency can be merged into core without importing the
attachment writer. Synthetic pure-codec tests run on Windows and Linux; they do
not establish positive protected storage acceptance.

## Direct QA repairs F40-13/F40-14

DOCX must begin with `PK\x03\x04` at byte offset zero. Valid ZIP polyglots
appended to PDF/image payloads are rejected, including a ZIP tail that leaves
PDF EOF within the previous envelope bound. EML has at most1,000 header fields,
998 octets per header line excluding CRLF, and65,536 header bytes. The chosen
minimum is a nonempty From or Date header; Subject-only messages are rejected.
These policies apply identically at upload and backend approval/export. Pure
regressions reproduce the direct Grok findings and test exact boundary acceptance.
