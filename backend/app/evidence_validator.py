"""Practical evidence checks for generated answers.

What this module does (all deterministic, no LLM involved):
  * finds citations written as [path/to/file.py:15-32] in the answer;
  * checks every citation against the chunks that were actually shown to the model;
  * reports which retrieved sources were cited and which answer sentences have no citation;
  * flags identifiers written in `backticks` that never appear in the retrieved code.

What it does NOT do: prove that a sentence is true. A valid citation means "this file
and these lines were really retrieved", not "the sentence correctly describes them".
"""
from __future__ import annotations

import re
from typing import Any

CITATION_BRACKET = re.compile(r"\[([^\[\]\r\n]{3,300})\]")
CITATION_ITEM = re.compile(
    r"^\s*(?P<path>[^\s:][^:\[\]]*?):\s*L?(?P<start>\d{1,7})(?:\s*[-\u2013\u2014]\s*L?(?P<end>\d{1,7}))?\s*$"
)
FILE_LIKE = re.compile(r"(?:/|\\|\.[A-Za-z0-9_+]{1,8}$)")
INLINE_CODE = re.compile(r"`([^`\r\n]{1,120})`")
IDENTIFIER = re.compile(r"^[A-Za-z_][\w.]*(?:\(\))?$")
PATHLIKE = re.compile(r"^[\w./\\-]+\.[A-Za-z0-9_+]{1,8}$")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
COMMON_LITERALS = {"True", "False", "None", "null", "true", "false", "self", "cls"}

INSUFFICIENT_PHRASES = (
    "not enough information", "insufficient", "cannot determine", "can't determine",
    "cannot be determined", "does not contain", "do not contain", "doesn't contain",
    "no evidence", "not found in the", "not shown in the", "unable to find",
    "cannot find", "can't find",
)

MIN_CLAIM_CHARS = 30
MAX_EXAMPLES = 5


def _normalize_path(path: str) -> str:
    cleaned = path.strip().strip("`'\"").replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def extract_citations(answer: str) -> list[dict]:
    """Return unique citations in order of appearance (not yet validated)."""
    found: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for bracket in CITATION_BRACKET.finditer(answer or ""):
        for part in re.split(r"[;,](?=\s*[^\d\s])", bracket.group(1)):
            item = CITATION_ITEM.match(part)
            if not item:
                continue
            path = _normalize_path(item.group("path"))
            if not path or not FILE_LIKE.search(path):
                continue
            start = int(item.group("start"))
            end = int(item.group("end") or start)
            key = (path, start, end)
            if key in seen:
                continue
            seen.add(key)
            text = f"{path}:{start}" if start == end else f"{path}:{start}-{end}"
            found.append({"text": text, "file_path": path, "start_line": start, "end_line": end})
    return found


def _shown_intervals(chunks: list[dict]) -> dict[str, list[tuple[int, int, int]]]:
    """Merge the line ranges shown to the model, per file: [(start, end, source_id)]."""
    per_file: dict[str, list[tuple[int, int, int]]] = {}
    for chunk in chunks:
        start = chunk.get("context_start_line", chunk.get("start_line"))
        end = chunk.get("context_end_line", chunk.get("end_line"))
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            continue
        per_file.setdefault(_normalize_path(chunk["file_path"]), []).append(
            (start, end, int(chunk.get("source_id", 0))))
    return per_file


def _merge(intervals: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end, _ in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def check_citation(citation: dict, shown: dict[str, list[tuple[int, int, int]]]) -> dict:
    """Validate one citation against the shown line ranges."""
    result = {**citation, "valid": False, "reason": "", "source_id": None}
    path, start, end = citation["file_path"], citation["start_line"], citation["end_line"]
    if path not in shown:
        result["reason"] = "file_not_retrieved"
        return result
    if start < 1 or end < start:
        result["reason"] = "invalid_line_range"
        return result
    if any(a <= start and end <= b for a, b in _merge(shown[path])):
        result["valid"] = True
        result["reason"] = "ok"
        for a, b, source_id in shown[path]:
            if a <= start <= b:
                result["source_id"] = source_id
                break
        return result
    result["reason"] = "lines_outside_retrieved_range"
    return result


def _declares_insufficient(answer: str) -> bool:
    lowered = (answer or "").lower()
    return any(phrase in lowered for phrase in INSUFFICIENT_PHRASES)


def _claim_sentences(answer: str) -> list[str]:
    """Sentences that read like statements about the code (heuristic)."""
    claims = []
    in_code_block = False
    for line in (answer or "").splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        for sentence in SENTENCE_SPLIT.split(line):
            text = sentence.strip(" \t-*#>")
            if len(text) < MIN_CLAIM_CHARS or text.endswith("?"):
                continue
            if _declares_insufficient(text):
                continue
            claims.append(sentence.strip())
    return claims


def _unsupported_identifiers(answer: str, chunks: list[dict]) -> list[str]:
    haystack = "\n".join(str(c.get("content", "")) for c in chunks)
    paths = {_normalize_path(c["file_path"]) for c in chunks}
    basenames = {p.rsplit("/", 1)[-1] for p in paths}
    missing: list[str] = []
    for span in INLINE_CODE.finditer(answer or ""):
        token = span.group(1).strip()
        if token in COMMON_LITERALS:
            continue
        if PATHLIKE.match(token):
            normalized = _normalize_path(token)
            if normalized not in paths and normalized.rsplit("/", 1)[-1] not in basenames \
                    and not any(p.endswith("/" + normalized) for p in paths):
                if token not in missing:
                    missing.append(token)
            continue
        if not IDENTIFIER.match(token):
            continue
        name = token[:-2] if token.endswith("()") else token
        looks_specific = "_" in name or "." in name or token.endswith("()") \
            or re.search(r"[a-z][A-Z]", name) or len(name) >= 7
        if not looks_specific:
            continue
        if name in haystack or name.rsplit(".", 1)[-1] in haystack:
            continue
        if token not in missing:
            missing.append(token)
    return missing[:20]


def validate_answer(answer: str, chunks: list[dict]) -> dict[str, Any]:
    """Check an answer's citations and coverage against the evidence it was given.

    Returns a dict with: citations, unsupported_citations, validation_passed,
    evidence_status, evidence_coverage, unsupported_identifiers, evidence_summary.

    evidence_status is one of:
      verified              every citation is valid and every claim sentence has one
      partially_verified    citations valid, but some claims lack citations or
                            `identifiers` do not appear in the retrieved code
      invalid_citations     at least one citation points outside the retrieved evidence
      no_citations          the answer cites nothing
      insufficient_evidence nothing was retrieved, or the answer says it cannot tell
    """
    answer = answer or ""
    shown = _shown_intervals(chunks)
    checked = [check_citation(c, shown) for c in extract_citations(answer)]
    invalid = [c for c in checked if not c["valid"]]
    valid = [c for c in checked if c["valid"]]
    cited_ids = sorted({c["source_id"] for c in valid if c["source_id"]})

    claims = _claim_sentences(answer)
    uncited = [s for s in claims if not extract_citations(s)]
    identifiers = _unsupported_identifiers(answer, chunks) if chunks else []

    coverage = {
        "retrieved_sources": len(chunks),
        "sources_cited": len(cited_ids),
        "cited_source_ids": cited_ids,
        "claim_sentences": len(claims),
        "cited_claim_sentences": len(claims) - len(uncited),
        "uncited_claim_examples": [s[:200] for s in uncited[:MAX_EXAMPLES]],
    }

    if not chunks:
        status = "insufficient_evidence"
        summary = "No relevant code was retrieved, so the question cannot be answered from the repository."
    elif invalid:
        status = "invalid_citations"
        summary = (f"{len(invalid)} of {len(checked)} citation(s) do not match the retrieved code and "
                   "must not be trusted.")
    elif not checked:
        if _declares_insufficient(answer):
            status = "insufficient_evidence"
            summary = "The answer states that the retrieved code is not enough to answer the question."
        else:
            status = "no_citations"
            summary = "The answer contains no source citations, so it cannot be traced to specific code."
    elif uncited or identifiers:
        status = "partially_verified"
        notes = []
        if uncited:
            notes.append(f"{len(uncited)} statement(s) have no citation")
        if identifiers:
            notes.append(f"{len(identifiers)} named identifier(s) do not appear in the retrieved code")
        summary = (f"All {len(valid)} citation(s) point to retrieved code, but " + " and ".join(notes) + ". "
                   "This is a heuristic check, not proof of correctness.")
    else:
        status = "verified"
        summary = (f"All {len(valid)} citation(s) point to retrieved code and every statement is cited. "
                   "This confirms traceability, not that each statement is correct.")

    return {
        "citations": checked,
        "unsupported_citations": invalid,
        "validation_passed": bool(checked) and not invalid and bool(chunks),
        "evidence_status": status,
        "evidence_coverage": coverage,
        "unsupported_identifiers": identifiers,
        "evidence_summary": summary,
    }
