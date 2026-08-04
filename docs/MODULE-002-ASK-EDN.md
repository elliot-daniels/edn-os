# Module 002.3 — Ask EDN

Ask EDN adds grounded, read-only question answering over the local email-memory
database. Keyword Search remains available as a separate interface mode.

## How it works

```text
Question
  → deterministic safe search terms
  → ranked SQLite FTS5 email retrieval
  → bounded email excerpts
  → local extractive answer
  → validated numbered citations
```

Retrieval differs from Search: Search passes an operator-entered FTS query to
the existing search service, while Ask EDN converts a natural-language question
into a bounded OR query containing only locally tokenized terms. Punctuation and
FTS operators from the question are never passed through directly.

Evidence keeps the backend relevance order. Each item includes the subject,
sender, sent date, folder, message ID, source record key, bounded excerpt and
full plain-text body for local inspection. The default is five sources and the
UI permits at most ten.

## Answers and citations

The current `extractive` provider runs entirely locally. It selects up to three
retrieved sources and presents concise excerpts with citations such as `[1]`.
Every citation is checked against the retrieved evidence before display.
Answers with fabricated, duplicate or missing citations are rejected.

When no useful terms or matching emails exist, Ask EDN reports insufficient
evidence instead of answering from general knowledge.

## Provider configuration

The provider boundary is defined by `AnswerProvider`. Current approved values:

| `EDN_LLM_PROVIDER` | Behaviour |
|---|---|
| unset, `extractive`, `local` | Local deterministic extractive answer |
| `disabled`, `off`, `none` | Answer generation disabled |

External providers are intentionally unsupported. EDN OS security policy
prohibits sending source email content to cloud AI. A future approved provider
can implement the same protocol and consume only `build_bounded_context()`
output, which is capped at 8,000 characters. Credentials and model names must
remain outside Git if that policy changes.

To disable answer generation entirely:

```bash
export EDN_LLM_PROVIDER=disabled
```

## Running locally

Wait until no production import is writing to the database, then run:

```bash
source /home/elliot/.venvs/edn-os/bin/activate
cd /home/elliot/projects/edn-os

export EDN_MEMORY_DB="/mnt/f/EDN OS/Database/edn-memory.db"
export EDN_LLM_PROVIDER=extractive

streamlit run src/edn/ui/app.py \
  --server.address 127.0.0.1 \
  --browser.gatherUsageStats false
```

Open <http://localhost:8501>.

For development, use a synthetic temporary database; never copy production
email data into the repository.

## Privacy and security

- Database access is SQLite read-only.
- No external API or network call is made by retrieval or answering.
- Only bounded excerpts are prepared for the provider boundary.
- Email content is rendered as literal plain text, never HTML.
- Questions, bodies, excerpts and prompts are not logged.
- The server must remain bound to `127.0.0.1`.

## Current limitations

- Retrieval is lexical FTS5, not semantic search.
- The extractive provider summarizes evidence snippets rather than synthesizing
  a fluent narrative.
- Search terms use deterministic stop-word filtering and may miss synonyms.
- There is no conversation memory or threading.
- The current production database may be incomplete if its import did not
  finish successfully.
