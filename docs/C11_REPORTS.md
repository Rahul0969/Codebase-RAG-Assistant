# C11 — Repository Intelligence Reports

The Reports page creates a local report for the currently selected repository. It is part of the existing Codebase RAG Assistant; it does not create a separate service or send repository contents to a hosted AI API.

## Formats

- Markdown (`md`) — editable report suitable for GitHub or documentation.
- HTML (`html`) — self-contained, dark-themed report page.
- JSON (`json`) — structured report data for further processing.

## Report contents

Reports include repository metadata, inspected-file and generated-chunk counts, file-type/language counts, recognized dependency manifests, directory structure, entry-point filename candidates, important files, conservative security-pattern observations, recommendations, file references and limitations.

Statistics and paths come from the local repository inspector and Tree-sitter chunker. A missing parser or partial scan is recorded as a limitation. Filename-based entry points are candidates, not proof of runtime entry points. Security matches are review prompts, not confirmed vulnerabilities or a complete security audit.

## Optional local AI summary

The report page enables local Ollama summary generation by default. It uses the configured `OLLAMA_MODEL` and sends a small, redacted sample of parsed code to the local Ollama service. If Ollama is unavailable or fails, the report is still generated with a deterministic summary. Disable the checkbox to skip the LLM entirely.

No paid API or hosted LLM is used.

## API

### Generate

`POST /api/reports/generate`

```json
{
  "repository_path": "C:\\Users\\You\\Projects\\sample-project",
  "format": "md",
  "use_ai_summary": false
}
```

`format` must be `md`, `html`, or `json`. `use_ai_summary` defaults to `true`.

### List

`GET /api/reports`

Returns report metadata only; it does not expose the generated report directory.

### Retrieve

`GET /api/reports/{report_id}`

Returns the report content and safe filename/MIME metadata.

### Download

`GET /api/reports/{report_id}/download`

Downloads the stored report. IDs must be 32-character lowercase hexadecimal identifiers; the server never accepts a filesystem path from this endpoint.

## Storage and limits

Reports are stored under `backend/data/reports/`, which is excluded from Git. The repository inspector's ignored-directory, sensitive-file and symlink rules are reused. Files read for dependency/security observations are limited to 1 MB each and 12 MB total. Code chunking uses the existing Tree-sitter limits. Generated report history is capped to the latest 100 entries in the API response.

## Known limitations

- This is a repository structure and static-pattern report, not a full compiler, dependency resolver, vulnerability scanner or runtime call-graph analyzer.
- Dependency extraction is detailed for `package.json` and `requirements.txt`; other recognized manifests are identified without echoing arbitrary manifest contents.
- The report includes at most 300 file references in the Markdown evidence list.
- Large repositories may be truncated by the existing inspector/chunker safety limits.
- Ollama summary quality depends on the locally installed model; the deterministic fallback is not an AI-generated narrative.
