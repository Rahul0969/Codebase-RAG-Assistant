"""Local repository report generation using inspected source evidence.

Reports are stored in an application-managed directory, never inside the target
repository. The LLM is optional: factual statistics and findings are deterministic.
"""
from __future__ import annotations

import html
import json
import re
import uuid
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunker import chunk_repository
from .llm_service import LLMError, generate_chat, get_settings
from .repository import inspect_repository
from .security import redact_secrets

REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
ALLOWED_FORMATS = {"md", "html", "json"}
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_READ_BYTES = 12_000_000
MAX_FILES_TO_READ = 5000
MANIFEST_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "Cargo.toml", "go.mod", "Gemfile", "composer.json",
    "Pipfile", "environment.yml", "environment.yaml",
}
ENTRY_NAMES = {
    "main.py", "app.py", "__main__.py", "manage.py", "main.java", "main.go",
    "main.rs", "index.js", "index.jsx", "index.ts", "index.tsx", "server.js",
    "server.ts", "app.jsx", "app.tsx", "program.cs", "index.html",
}
LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cs": "C#",
    ".go": "Go", ".rs": "Rust", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift",
    ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala", ".html": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".json": "JSON", ".yaml": "YAML",
    ".yml": "YAML", ".toml": "TOML", ".md": "Markdown", ".rst": "reStructuredText",
    ".txt": "Text", ".sql": "SQL", ".sh": "Shell", ".bat": "Batch",
    ".ps1": "PowerShell", ".xml": "XML", ".vue": "Vue", ".svelte": "Svelte",
    ".ipynb": "Jupyter Notebook",
}


def _safe_read(root: Path, relative: str, remaining: int) -> tuple[str | None, int]:
    candidate = root / Path(relative)
    try:
        is_junction = getattr(candidate, "is_junction", None)
        if candidate.is_symlink() or bool(is_junction and is_junction()):
            return None, remaining
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file():
            return None, remaining
        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES or size > remaining:
            return None, remaining
        raw = resolved.read_bytes()
        text = raw.decode("utf-8-sig")
        return text, remaining - len(raw)
    except (OSError, UnicodeError, ValueError):
        return None, remaining


def _dependency_summary(root: Path, files: list[dict], budget: int) -> tuple[list[dict], int]:
    results: list[dict] = []
    remaining = budget
    for item in files:
        name = Path(item["path"]).name
        if name not in MANIFEST_NAMES:
            continue
        content, remaining = _safe_read(root, item["path"], remaining)
        if content is None:
            continue
        dependencies: list[str] = []
        if name == "package.json":
            try:
                parsed = json.loads(content)
                for group in ("dependencies", "devDependencies", "peerDependencies"):
                    values = parsed.get(group, {}) if isinstance(parsed, dict) else {}
                    if isinstance(values, dict):
                        dependencies.extend(redact_secrets(f"{key} ({value})") for key, value in values.items())
            except (ValueError, AttributeError):
                dependencies.append("Could not parse package.json")
        elif name == "requirements.txt":
            dependencies = [redact_secrets(line.strip()) for line in content.splitlines()
                            if line.strip() and not line.lstrip().startswith(("#", "-"))]
        else:
            # Do not echo arbitrary manifest lines: some build files may contain credentials.
            dependencies = ["Manifest detected; detailed dependency extraction is not implemented for this format."]
        results.append({"manifest": item["path"], "dependencies": dependencies[:150]})
    return results, remaining


def _security_observations(root: Path, files: list[dict], budget: int) -> tuple[list[dict], int]:
    findings: list[dict] = []
    remaining = budget
    # These are deliberately conservative indicators, not a security scanner.
    patterns = [
        (re.compile(r"\beval\s*\("), "Dynamic evaluation", "Review whether dynamically evaluated input can be controlled by users."),
        (re.compile(r"\b(?:subprocess\.(?:run|Popen|call)|os\.system)\s*\("), "Process execution", "Review argument handling and avoid passing untrusted input to shell commands."),
        (re.compile(r"\b(?:verify=False|CERT_NONE)\b"), "TLS verification disabled", "Verify that certificate checks are not disabled in production code."),
        (re.compile(r"\b(?:debug\s*=\s*True|DEBUG\s*=\s*True)\b", re.I), "Debug mode enabled", "Confirm debug mode is not enabled in production configuration."),
    ]
    for item in files:
        content, remaining = _safe_read(root, item["path"], remaining)
        if content is None:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            for pattern, title, recommendation in patterns:
                if pattern.search(line):
                    findings.append({
                        "title": title,
                        "file_path": item["path"],
                        "line": line_number,
                        "evidence": redact_secrets(line.strip())[:240],
                        "recommendation": recommendation,
                        "confidence": "pattern_match_requires_manual_review",
                    })
                    if len(findings) >= 100:
                        return findings, remaining
    return findings, remaining


def _architecture(files: list[dict]) -> dict:
    directories = Counter()
    for item in files:
        parent = Path(item["path"]).parent.as_posix()
        if parent != ".":
            directories[parent] += 1
    entry_points = [item["path"] for item in files if Path(item["path"]).name.lower() in ENTRY_NAMES]
    top_level = sorted({Path(item["path"]).parts[0] for item in files if len(Path(item["path"]).parts) > 1})
    return {
        "top_level_directories": top_level,
        "directory_file_counts": dict(sorted(directories.items())[:100]),
        "entry_point_candidates": entry_points[:50],
        "note": "Entry points are filename-based candidates; verify them manually.",
    }


def _build_markdown(report: dict) -> str:
    stats = report["statistics"]
    lines = [f"# Repository Intelligence Report: {report['repository_name']}", "",
             f"- Generated: {report['generated_at']}", f"- Repository: `{report['repository_path']}`",
             f"- Report ID: `{report['report_id']}`", f"- Summary source: {report['summary_source']}", "", "## 1. Executive Summary", "",
             report["executive_summary"], ""]
    if report.get("summary_evidence"):
        lines.append("Summary evidence (AI-generated summary is model-written; verify these references manually):")
        lines.extend(f"- `{item['path']}:{item['start_line']}-{item['end_line']}`" for item in report["summary_evidence"])
    lines += ["", "## 2. Repository Statistics", "",
             f"- Files inspected: {stats['files_inspected']}",
             f"- Source chunks parsed: {stats['chunks_generated']}",
             f"- Files represented in chunks: {stats['files_with_chunks']}",
             f"- Inspection truncated: {stats['inspection_truncated']}",
             f"- Chunking truncated: {stats['chunking_truncated']}", "", "### Languages / file types", ""]
    for key, value in report["languages"].items():
        lines.append(f"- {key}: {value}")
    lines += ["", "### Files by extension", ""]
    lines.extend(f"- `{key}`: {value}" for key, value in report["extensions"].items())
    lines += ["", "## 3. Technology Stack and Dependencies", ""]
    if report["dependencies"]:
        for manifest in report["dependencies"]:
            lines.append(f"### `{manifest['manifest']}`")
            lines.extend(f"- {dep}" for dep in manifest["dependencies"])
            if not manifest["dependencies"]:
                lines.append("- No dependencies extracted.")
    else:
        lines.append("No recognized dependency manifest was found or readable.")
    lines += ["", "## 4. Project Architecture", "",
              f"Top-level directories: {', '.join(report['architecture']['top_level_directories']) or 'No nested directories detected.'}", "",
              "### Directory file counts", ""]
    lines.extend(f"- `{key}`: {value}" for key, value in report["architecture"]["directory_file_counts"].items())
    lines += ["", "### Entry-point candidates", ""]
    lines.extend(f"- `{path}`" for path in report["architecture"]["entry_point_candidates"])
    lines += ["", f"> {report['architecture']['note']}", "", "## 5. Important Files", ""]
    lines.extend(f"- `{item['path']}` — {item['reason']}" for item in report["important_files"])
    lines += ["", "## 6. Code Analysis", "",
              "This section summarizes deterministic structural observations. It does not claim a complete code-quality audit.", "",
              f"- Supported files discovered: {stats['files_inspected']}",
              f"- Files successfully represented by chunks: {stats['files_with_chunks']}",
              f"- Files skipped during chunking: {len(report['chunking']['skipped_files'])}", "",
              "## 7. Security Observations", "",
              "Pattern matches are review prompts, not confirmed vulnerabilities. Manual review is required.", ""]
    if report["security_observations"]:
        for finding in report["security_observations"]:
            lines.append(f"- **{finding['title']}** — `{finding['file_path']}:{finding['line']}` — {finding['recommendation']}")
    else:
        lines.append("No configured security patterns matched in the inspected text. This is not proof of security.")
    lines += ["", "## 8. Recommendations", "",
              "- Review entry-point candidates and confirm the actual application startup flow.",
              "- Add or maintain automated tests for core modules and API boundaries.",
              "- Review security pattern matches manually and use a dedicated security review before production use.",
              "- Keep dependency manifests and setup documentation synchronized.",
              "- Re-index after source changes before relying on semantic search or RAG answers.", "",
              "## 9. Evidence and References", ""]
    lines.extend(f"- `{item['path']}` ({item['extension']})" for item in report["files"][:300])
    lines += ["", "## 10. Limitations", ""]
    lines.extend(f"- {item}" for item in report["limitations"])
    lines += ["", "---", "Generated locally by Codebase RAG Assistant.", ""]
    return "\n".join(lines)


def _build_html(markdown: str, report: dict) -> str:
    # Minimal safe Markdown-to-HTML renderer. Every source-derived line is escaped.
    rendered: list[str] = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            continue
        if line == "---":
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append("<hr>")
        elif line.startswith("### ") or line.startswith("## ") or line.startswith("# "):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            level = 3 if line.startswith("### ") else 2 if line.startswith("## ") else 1
            rendered.append(f"<h{level}>{html.escape(line[level + 1:])}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("> "):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        else:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        rendered.append("</ul>")
    body = "\n".join(rendered)
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Repository Report</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 20px;background:#081225;color:#e7eefc}"
            "h1,h2,h3{color:#75a7ff}li{margin:4px 0}code{background:#142344;padding:2px 5px;border-radius:4px}blockquote{border-left:3px solid #5795f5;padding-left:14px;color:#b9c9e8}"
            "</style></head><body><h1>" + html.escape(report["repository_name"]) + " — Repository Report</h1>" + body + "</body></html>")


def generate_report(repository_path: str, report_format: str = "md", use_ai_summary: bool = True,
                    report_dir: Path | None = None) -> dict:
    fmt = report_format.lower().lstrip(".")
    if fmt not in ALLOWED_FORMATS:
        raise ValueError("Report format must be md, html, or json.")
    inspection = inspect_repository(repository_path)
    root = Path(repository_path).expanduser().resolve(strict=True)
    chunking: dict[str, Any]
    try:
        chunking = chunk_repository(str(root))
    except Exception as error:  # Report generation must still work without the parser package.
        chunking = {"chunk_count": 0, "chunks": [], "skipped_files": [], "truncated": False,
                    "error": f"Chunking unavailable: {type(error).__name__}"}
    chunks = chunking.get("chunks", []) if isinstance(chunking, dict) else []
    language_counts = Counter(LANGUAGE_BY_EXTENSION.get(item["extension"], item["extension"]) for item in inspection["files"])
    extension_counts = Counter(item["extension"] for item in inspection["files"])
    files_with_chunks = len({item.get("file_path") for item in chunks if item.get("file_path")})
    dependencies, remaining = _dependency_summary(root, inspection["files"], MAX_TOTAL_READ_BYTES)
    observations, remaining = _security_observations(root, inspection["files"], remaining)
    important_files = []
    for item in inspection["files"]:
        name = Path(item["path"]).name.lower()
        if name in ENTRY_NAMES:
            important_files.append({"path": item["path"], "reason": "Entry-point filename candidate; confirm by reviewing its contents."})
        elif name in MANIFEST_NAMES:
            important_files.append({"path": item["path"], "reason": "Dependency or build configuration manifest."})
    limitations = [
        "Repository inspection lists only supported extensions and excludes configured sensitive files and ignored directories.",
        "File reads are limited to 1 MB per file and 12 MB total for dependency and security observations.",
        "Tree-sitter chunking supports only languages configured in the existing chunker; chunking may be unavailable if its parser package is missing.",
        "Security observations use conservative pattern matching and are not a complete vulnerability scan.",
        "Architecture relationships are inferred from paths and filename candidates, not proven runtime call graphs.",
    ]
    if inspection.get("truncated"):
        limitations.append("Repository inspection reached its configured file limit; statistics cover only the inspected subset.")
    if chunking.get("truncated"):
        limitations.append("Code chunking reached its configured chunk limit; chunk statistics cover only the generated subset.")
    if chunking.get("error"):
        limitations.append(chunking["error"])
    if remaining <= 0:
        limitations.append("The bounded file-reading budget was exhausted; some manifests or security patterns may not have been examined.")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report_id = uuid.uuid4().hex
    report: dict[str, Any] = {
        "report_id": report_id,
        "repository_name": inspection["repository_name"],
        "repository_path": str(root),
        "generated_at": now,
        "executive_summary": (f"{inspection['repository_name']} contains {inspection['file_count']} supported files. "
                              f"The scanner generated {len(chunks)} code chunks across {files_with_chunks} files. "
                              "The report records observable repository structure and bounded static checks."),
        "summary_source": "deterministic",
        "summary_evidence": [],
        "statistics": {"files_inspected": inspection["file_count"], "chunks_generated": len(chunks),
                       "files_with_chunks": files_with_chunks,
                       "inspection_truncated": bool(inspection.get("truncated")),
                       "chunking_truncated": bool(chunking.get("truncated"))},
        "languages": dict(sorted(language_counts.items())),
        "extensions": dict(sorted(extension_counts.items())),
        "files": inspection["files"],
        "architecture": _architecture(inspection["files"]),
        "important_files": important_files[:150],
        "dependencies": dependencies,
        "security_observations": observations,
        "chunking": {"skipped_files": chunking.get("skipped_files", []), "error": chunking.get("error")},
        "limitations": limitations,
    }

    if use_ai_summary and chunks:
        evidence = "\n\n".join(
            f"[{c.get('file_path')}:{c.get('start_line')}-{c.get('end_line')}]\n{redact_secrets(str(c.get('content', '')))[:1000]}"
            for c in chunks[:8]
        )[:7000]
        try:
            settings = get_settings()
            settings = replace(settings, timeout=min(settings.timeout, 45.0),
                               num_predict=min(settings.num_predict, 220))
            generated = generate_chat([
                {"role": "system", "content": "Write a concise, cautious repository overview using only supplied evidence. Do not invent dependencies, runtime behavior, or architecture. Cite every concrete code claim using the supplied [path:start-end] references. State uncertainty and do not claim a complete audit."},
                {"role": "user", "content": f"Repository: {inspection['repository_name']}\nFiles: {inspection['file_count']}\nEvidence:\n{evidence}\n\nWrite a 3-5 sentence executive summary."},
            ], settings=settings)
            report["executive_summary"] = generated["text"][:3000]
            report["summary_source"] = f"local Ollama ({generated.get('model', settings.model)})"
            report["summary_evidence"] = [
                {"path": str(chunk.get("file_path")), "start_line": int(chunk.get("start_line", 1)),
                 "end_line": int(chunk.get("end_line", 1))}
                for chunk in chunks[:8] if chunk.get("file_path")
            ]
        except (LLMError, ValueError, OSError):
            report["limitations"].append("Ollama summary generation was unavailable; a deterministic summary was used.")

    markdown = _build_markdown(report)
    if fmt == "md":
        content = markdown
        extension = "md"
        mime = "text/markdown; charset=utf-8"
    elif fmt == "html":
        content = _build_html(markdown, report)
        extension = "html"
        mime = "text/html; charset=utf-8"
    else:
        content = json.dumps(report, ensure_ascii=False, indent=2)
        extension = "json"
        mime = "application/json"
    directory = report_dir or REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{report_id}.{extension}"
    target = directory / filename
    target.write_text(content, encoding="utf-8")
    # Metadata JSON supports listing and later downloads in any generated format.
    metadata_path = directory / f"{report_id}.meta.json"
    metadata_path.write_text(json.dumps({"report_id": report_id, "repository_name": inspection["repository_name"],
                                         "generated_at": now, "format": fmt, "filename": filename,
                                         "mime_type": mime}, indent=2), encoding="utf-8")
    return {"report_id": report_id, "repository_name": inspection["repository_name"],
            "generated_at": now, "format": fmt, "filename": filename,
            "mime_type": mime, "content": content, "summary_source": report["summary_source"]}


def list_reports(report_dir: Path | None = None) -> list[dict]:
    directory = report_dir or REPORT_DIR
    if not directory.exists():
        return []
    items = []
    for path in directory.glob("*.meta.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(item, dict) and re.fullmatch(r"[a-f0-9]{32}", str(item.get("report_id", ""))):
                items.append({key: item.get(key) for key in ("report_id", "repository_name", "generated_at", "format", "filename")})
        except (OSError, ValueError):
            continue
    return sorted(items, key=lambda item: item.get("generated_at", ""), reverse=True)[:100]


def read_report(report_id: str, report_dir: Path | None = None) -> tuple[str, str, str]:
    if not re.fullmatch(r"[a-f0-9]{32}", report_id or ""):
        raise FileNotFoundError("Report not found.")
    directory = (report_dir or REPORT_DIR).resolve()
    metadata_path = directory / f"{report_id}.meta.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filename = metadata.get("filename")
        if not isinstance(filename, str) or filename != Path(filename).name or not filename.startswith(report_id + "."):
            raise FileNotFoundError
        target = (directory / filename).resolve(strict=True)
        target.relative_to(directory)
        if not target.is_file():
            raise FileNotFoundError
        return target.read_text(encoding="utf-8"), str(metadata.get("mime_type", "application/octet-stream")), filename
    except (OSError, ValueError, TypeError, AttributeError):
        raise FileNotFoundError("Report not found.") from None
