# PA-002 - Bounded Document Ingestion

PA-002 adds local PDF and DOCX extraction to the approved-root Local Files
connector. PDF extraction accepts bounded unencrypted text streams and rejects
malformed envelopes, encryption, unsupported filters, decompression failures,
empty extraction and oversized output. DOCX extraction reads only the main
document XML and bounds entry count, expanded size and compression ratio.

Records retain source binary hash, domain, classification, source URI, typed
record type and PDF-page or DOCX-paragraph transformation provenance. A
read-only `local-files.search` capability exposes only exact-scope previously
ingested content through `LocalFilesEvidenceAdapter` and the existing
permission-first context assembler.

Automated tests use temporary synthetic documents only. No owner root, live
document or external parser service was accessed.
