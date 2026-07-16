# PST Extractor Proof of Concept

Disposable evaluation scripts for **MOD-001 — Memory**. These scripts are **not**
imported by the production `edn` package.

## Safety

- Open PST files **read-only**.
- Do **not** write beside the source PST.
- Do **not** write under `E:\EDN OS` unless the operator explicitly chooses that path.
- First probes collect **metadata only** — no message bodies or attachments.
- No network access. No automatic installation of system packages or PST libraries.

## Prerequisites

Run environment inspection first:

```powershell
python -m poc.pst.inspect_environment --output-dir C:\Temp\edn-poc-reports
```

Optional PST access check (requires operator approval):

```powershell
python -m poc.pst.inspect_environment `
  --pst "D:\path\to\archive.pst" `
  --output-dir C:\Temp\edn-poc-reports `
  --fingerprint
```

## Probes

### libpff / pypff

```powershell
python -m poc.pst.probe_libpff `
  --pst "D:\path\to\archive.pst" `
  --output-dir C:\Temp\edn-poc-reports `
  --sample-size 5
```

Install `pypff` manually if required. The probe reports `unavailable` when the
module cannot be imported.

### readpst

```powershell
python -m poc.pst.probe_readpst `
  --pst "D:\path\to\archive.pst" `
  --output-dir C:\Temp\edn-poc-reports
```

Conversion sampling is **off by default**. To allow a temporary conversion when
listing fails:

```powershell
python -m poc.pst.probe_readpst `
  --pst "D:\path\to\archive.pst" `
  --output-dir C:\Temp\edn-poc-reports `
  --allow-conversion-sample
```

## Compare results

```powershell
python -m poc.pst.compare_results `
  --reports-dir C:\Temp\edn-poc-reports `
  --output C:\Temp\edn-poc-reports\comparison.json
```

Record scores in `docs/PST-EXTRACTOR-POC.md` after reviewing JSON output.

## Output files

| File | Source |
|------|--------|
| `environment.json` | `inspect_environment.py` |
| `probe_libpff.json` | `probe_libpff.py` |
| `probe_readpst.json` | `probe_readpst.py` |

Do not commit PST files or generated reports.
