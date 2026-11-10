# C12 — Code Change Impact Analysis

## Purpose

The Change Impact page identifies likely files affected by a proposed change. It builds a bounded, local, file-level import graph without executing repository code.

## How to use

1. Select and inspect a repository on the Repository page.
2. Open **Change Impact** in the sidebar.
3. Enter one to twenty repository-relative paths, one per line (for example `src/services/api.js`).
4. Select **Analyze impact**.
5. Review direct dependents, transitive dependents, likely related tests, dependency edges and analysis limitations.

## API

`POST /repository/impact`

```json
{
  "repository_path": "C:\\Users\\you\\project",
  "changed_files": ["src/services/api.js", "src/components/ReportsPanel.jsx"]
}
```

The endpoint validates the repository root with the same C10 path guard as other repository APIs. Changed file paths must be relative, remain inside the selected repository and match files discovered by safe repository inspection.

Response fields (all earlier fields are kept; new ones are marked *new*):

- `direct_dependents`: **confirmed** files that import a changed file.
- `transitive_dependents`: **confirmed** files reached through a chain of confirmed imports.
- `all_affected_files`: direct plus transitive (confirmed only).
- `possible_dependents` *new*: files reachable only through **inferred** edges (see below). Never mixed into the confirmed lists.
- `related_tests`: **confirmed** test files that depend on a changed file through imports. Changed from earlier behaviour, which also included filename guesses.
- `likely_related_tests` *new*: test files matched by naming convention only, or reachable only through inferred edges.
- `dependency_edges`: affected-subgraph edges, each with `confidence` (`confirmed` or `inferred`) *new*; `dependency_edge_count` *new* gives the full count before the 500-edge cap.
- `unresolved_local_references`: local-looking imports that matched no file, one entry per file and specifier, with a `reason` *new* (`not_found`, `ambiguous_match`, `beyond_repository_root`, `unsupported_file_type`); `unresolved_reference_count` *new*.
- `unmapped_aliases` *new*: alias imports such as `@/x` that could not be mapped (not guessed).
- `cycles` *new*: real import cycles (strongly connected groups of confirmed edges) that include a changed file, with their member files. `possible_dependency_cycle` and `cycle_involving_changed_files` are kept.
- `skipped_files`, `skipped_file_count`, `skipped_reason_counts` *new*: files that could not be analysed (`syntax_error`, `too_large`, `binary`, `not_utf8`, `unreadable`, `symlink`, `byte_budget_exhausted`, `time_budget_exhausted`).
- `limitations`, `truncated`, `files_scanned`, `files_discovered`, `analysis_version` (2).

## Confirmed vs. inferred

| Confidence | Meaning | Examples |
|---|---|---|
| confirmed | The import resolves to exactly one scanned file by the language's rules | Python relative/absolute imports rooted at the repository; JS/TS relative paths (extensions, `index` files, `.js`→`.ts` ESM style); Java imports matched through the **declared** `package` line |
| inferred | A guess that is plausible but unproven | Python imports rooted in a subfolder (`from app.x` for `backend/app/x.py`) when exactly one file matches; JS `@/` or `~/` aliases mapped to `src/`; baseUrl-style imports; Java wildcard imports (`import a.b.*`) |

Ambiguous matches (several files fit) create no edge and are reported as unresolved. Standard-library module names are never matched to local files by guessing.

## Supported static import patterns

- Python `import` and `from ... import ...` (relative and absolute, packages, namespace folders, `from pkg import submodule`). Importing a symbol from a package depends on its `__init__.py` only when the name is not a submodule.
- JavaScript/TypeScript/Vue/Svelte `import ... from`, `export ... from`, side-effect `import 'x'`, literal `import('x')` and `require('x')`. Comments and string literals are ignored.
- Java single-class, nested-class and static imports resolved through each file's `package` declaration (works with `src/main/java` layouts); wildcard imports are inferred.

## Limitations

This is a file-level static import graph, not a runtime call graph. Dynamic imports with computed names, reflection, dependency injection, generated code, tsconfig/vite/webpack alias settings, same-package Java references (no import statement) and non-import relationships are not detected. `.mjs`/`.cjs` files are not scanned by repository inspection. Related-test discovery does not prove coverage. No source code is executed or imported (Python files are only parsed), and the API returns paths and import specifiers, never source text.

## Limits (configurable in `backend/.env`)

| Variable | Default | Range |
|---|---|---|
| `RAG_IMPACT_MAX_FILES` | 2500 | 100–10000 |
| `RAG_IMPACT_MAX_FILE_BYTES` | 512000 | 10000–2000000 |
| `RAG_IMPACT_MAX_TOTAL_BYTES` | 8000000 | 500000–64000000 |
| `RAG_IMPACT_MAX_SECONDS` | 20 | 1–300 |

When the file cap is reached, changed files are read first, then files nearest to them in the folder tree. Only one file is held in memory at a time. Reaching any limit sets `truncated` and adds a plain-language limitation.

## Changed-path handling

Paths may use `/` or `\\`, a leading `./`, and dot-folders (`.storybook/main.js`). Absolute paths, drive letters (`C:\\...`), `..`, NUL characters and over-long values are rejected. A case-only difference (Windows) is accepted when exactly one file matches.
