"""Static, local-first code change impact analysis (C12, refined).

Builds a file-level import graph for Python, JavaScript/TypeScript and Java.
It parses text only: repository code is never imported, executed or compiled,
and source contents are never returned (only paths and import specifiers).

Every edge carries a confidence level:

* ``confirmed`` - an import statement that resolves to exactly one scanned file
  by the language's own rules (relative path, package path, declared Java package).
* ``inferred``  - a plausible match that needs a guess (source-root or alias
  inference, wildcard imports). Inferred edges never appear in the confirmed
  dependent lists; they are reported separately as ``possible_*`` results.
"""
from __future__ import annotations

import ast
import bisect
import os
import posixpath
import re
import sys
import time
import warnings
from collections import defaultdict, deque
from pathlib import Path

from .repository import inspect_repository

CONFIRMED = "confirmed"
INFERRED = "inferred"

# Defaults; each can be lowered/raised with an RAG_IMPACT_* variable (see _limits()).
MAX_ANALYSIS_FILES = 2500
MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 8_000_000
MAX_SECONDS = 20.0

MAX_CHANGED_FILES = 20
MAX_UNRESOLVED = 200
MAX_EDGES_RETURNED = 500
MAX_SKIPPED_LISTED = 100
MAX_CYCLES_RETURNED = 10
MAX_CYCLE_FILES = 50
MAX_WILDCARD_FILES = 50
MAX_SPECIFIER_CHARS = 200

_JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
_JS_RESOLVE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".json")
_JS_ESM_SWAP = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
_UNSCANNED_TARGET_EXTS = {".mjs", ".cjs", ".mts", ".cts"}
_ALIAS_PREFIXES = ("@/", "~/", "#", "$lib/")
_ANALYZED_SUFFIXES = _JS_SUFFIXES | {".py", ".java"}
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))

# Comments and string literals, matched together so "//" inside a string is not a comment.
_JS_TOKEN = re.compile(
    r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`", re.S)
_JS_FROM = re.compile(r"(?<![.\w$])from\s*(['\"])(?P<s>[^'\"\n]+)\1")
_JS_SIDE_EFFECT = re.compile(r"(?<![.\w$])import\s*(['\"])(?P<s>[^'\"\n]+)\1")
_JS_DYNAMIC = re.compile(r"(?<![.\w$])import\s*\(\s*(['\"])(?P<s>[^'\"\n]+)\1\s*[,)]")
_JS_REQUIRE = re.compile(r"(?<![.\w$])require\s*\(\s*(['\"])(?P<s>[^'\"\n]+)\1\s*\)")
_JAVA_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_JAVA_IMPORT = re.compile(r"^\s*import\s+(?P<static>static\s+)?(?P<name>[\w.]+?)(?P<wild>\.\*)?\s*;", re.M)
_JAVA_PACKAGE = re.compile(r"^\s*package\s+(?P<name>[\w.]+)\s*;", re.M)
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "testing"}
_DRIVE = re.compile(r"^[A-Za-z]:")


def _env_number(name: str, default, low, high, cast):
    try:
        value = cast(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _limits() -> tuple[int, int, int, float]:
    return (
        _env_number("RAG_IMPACT_MAX_FILES", MAX_ANALYSIS_FILES, 100, 10_000, int),
        _env_number("RAG_IMPACT_MAX_FILE_BYTES", MAX_FILE_BYTES, 10_000, 2_000_000, int),
        _env_number("RAG_IMPACT_MAX_TOTAL_BYTES", MAX_TOTAL_BYTES, 500_000, 64_000_000, int),
        _env_number("RAG_IMPACT_MAX_SECONDS", MAX_SECONDS, 1.0, 300.0, float),
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def _normalize_changed(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Each changed file path must be a non-empty relative path.")
    text = raw.strip().replace("\\", "/")
    if len(text) > 1024 or "\x00" in text:
        raise ValueError("A changed file path is not valid.")
    if text.startswith("/") or _DRIVE.match(text):
        raise ValueError("Changed file paths must be relative to the selected repository.")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError("Changed file paths must stay inside the selected repository.")
    return "/".join(parts)


def _match_changed(normalized: str, path_set: set[str], lower_map: dict[str, list[str]]) -> str:
    if normalized in path_set:
        return normalized
    # Windows file systems ignore case; accept a case-only difference when it is unambiguous.
    matches = lower_map.get(normalized.lower(), [])
    if len(matches) == 1:
        return matches[0]
    shown = normalized if len(normalized) <= 200 else normalized[:200] + "..."
    raise ValueError(
        f"Changed file was not found among scanned source files: {shown} "
        "(unsupported file types, ignored folders and sensitive files are excluded).")


# ---------------------------------------------------------------------------
# Safe source reading
# ---------------------------------------------------------------------------
def _read_source(root: Path, relative: str, remaining: int, max_file: int):
    """Return (text | None, remaining_budget, skip_reason | None). Never follows symlinks."""
    candidate = root.joinpath(*relative.split("/"))
    try:
        if candidate.is_symlink():
            return None, remaining, "symlink"
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file():
            return None, remaining, "not_a_file"
        size = resolved.stat().st_size
        if size > max_file:
            return None, remaining, "too_large"
        if size > remaining:
            return None, remaining, "byte_budget_exhausted"
        with resolved.open("rb") as handle:
            raw = handle.read(max_file + 1)
        if len(raw) > max_file:
            return None, remaining, "too_large"
        if b"\x00" in raw[:4096]:
            return None, remaining, "binary"
        return raw.decode("utf-8-sig"), remaining - len(raw), None
    except UnicodeDecodeError:
        return None, remaining, "not_utf8"
    except (OSError, ValueError):
        return None, remaining, "unreadable"


# ---------------------------------------------------------------------------
# Parsing (text only)
# ---------------------------------------------------------------------------
def _parse_python(source: str):
    """Return [(level, module, names, is_from)] or None when the file does not parse."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # invalid escape sequences etc. are not our business
            tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((0, alias.name, (), False) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = tuple(alias.name for alias in node.names if alias.name != "*")
            found.append((node.level or 0, node.module or "", names, True))
    return found


def _parse_js(source: str) -> list[str]:
    """Return import specifiers found in code (not in comments or inside string literals)."""
    strings: list[tuple[int, int]] = []
    pieces: list[str] = []
    cursor = 0
    for match in _JS_TOKEN.finditer(source):
        start, end = match.span()
        text = match.group(0)
        if text.startswith("/"):  # comment: blank it out but keep line structure
            pieces.append(source[cursor:start])
            pieces.append(re.sub(r"[^\n]", " ", text))
            cursor = end
        else:
            strings.append((start, end))
    pieces.append(source[cursor:])
    code = "".join(pieces)
    starts = [item[0] for item in strings]

    def in_string(position: int) -> bool:
        index = bisect.bisect_right(starts, position) - 1
        return index >= 0 and strings[index][0] <= position < strings[index][1]

    found: list[str] = []
    for pattern in (_JS_FROM, _JS_SIDE_EFFECT, _JS_DYNAMIC, _JS_REQUIRE):
        for match in pattern.finditer(code):
            if not in_string(match.start()):
                found.append(match.group("s"))
    return found


def _parse_java(source: str):
    code = _JAVA_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)
    package = _JAVA_PACKAGE.search(code)
    imports = [(m.group("name"), bool(m.group("static")), bool(m.group("wild")))
               for m in _JAVA_IMPORT.finditer(code)]
    return (package.group("name") if package else ""), imports


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _join(directory: str, name: str) -> str:
    return f"{directory}/{name}" if directory else name


class _Graph:
    def __init__(self) -> None:
        self.edges: dict[str, dict[str, str]] = defaultdict(dict)
        self.unresolved: list[dict] = []
        self.unresolved_total = 0
        self._seen: set[tuple[str, str]] = set()
        self.aliases: set[str] = set()

    def add(self, source: str, target: str, confidence: str) -> None:
        if source == target:
            return
        current = self.edges[source].get(target)
        if current == CONFIRMED:
            return
        self.edges[source][target] = confidence

    def miss(self, source: str, reference: str, reason: str) -> None:
        key = (source, reference)
        if key in self._seen:
            return
        self._seen.add(key)
        self.unresolved_total += 1
        if len(self.unresolved) < MAX_UNRESOLVED:
            self.unresolved.append({"file_path": source, "reference": reference[:MAX_SPECIFIER_CHARS],
                                    "reason": reason})


class _Index:
    """Lookup tables over all discovered files."""

    def __init__(self, paths: list[str]) -> None:
        self.files = set(paths)
        self.dirs = {parent for path in paths for parent in _ancestors(path)}
        self.top_dirs = {path.split("/", 1)[0] for path in paths if "/" in path}
        self.package_names = ({p.split("/", 1)[0] for p in paths if "/" in p and p.endswith(".py")}
                              | {posixpath.basename(posixpath.dirname(p)) for p in paths
                                 if p.endswith("/__init__.py")}
                              | {posixpath.splitext(p)[0] for p in paths if "/" not in p and p.endswith(".py")})
        self._suffixes: dict[str, set[str]] | None = None

    def py_suffixes(self) -> dict[str, set[str]]:
        if self._suffixes is None:
            table: dict[str, set[str]] = defaultdict(set)
            for path in self.files:
                if not path.endswith(".py"):
                    continue
                parts = path.split("/")
                for i in range(len(parts)):
                    table["/".join(parts[i:])].add(path)
            self._suffixes = table
        return self._suffixes


def _ancestors(path: str):
    directory = posixpath.dirname(path)
    while directory:
        yield directory
        directory = posixpath.dirname(directory)


def _py_module(index: _Index, parts: list[str]):
    """Return (file, directory) for a dotted module path rooted at the repository."""
    base = "/".join(parts)
    if not base:
        return None, ""
    for candidate in (base + ".py", base + "/__init__.py"):
        if candidate in index.files:
            return candidate, None
    return (None, base) if base in index.dirs else (None, None)


def _resolve_python(graph: _Graph, index: _Index, relative: str, item) -> None:
    level, module, names, is_from = item
    mod_parts = [p for p in module.split(".") if p] if module else []
    confidence = CONFIRMED
    spec = "." * level + module
    here = posixpath.dirname(relative)
    here_parts = here.split("/") if here else []
    if level:
        if level - 1 > len(here_parts):
            graph.miss(relative, spec, "beyond_repository_root")
            return
        parts = here_parts[: len(here_parts) - (level - 1)] + mod_parts
        found, directory = _py_module(index, parts)
    else:
        parts = mod_parts
        found, directory = _py_module(index, parts)
        if found is None and directory is None:
            if parts and parts[0] in _STDLIB:
                return
            matches: set[str] = set()
            table = index.py_suffixes()
            base = "/".join(parts)
            for candidate in (base + ".py", base + "/__init__.py"):
                matches |= table.get(candidate, set())
            if len(matches) > 1:
                graph.miss(relative, spec, "ambiguous_match")
                return
            if matches:
                found, confidence = next(iter(matches)), INFERRED
            elif parts and parts[0] in index.package_names:
                graph.miss(relative, spec, "not_found")
                return
            else:
                return  # external package: not a local reference
    if found is None and directory is None:
        graph.miss(relative, spec, "not_found")
        return

    package_dir = None
    if found is not None:
        is_package = found.endswith("/__init__.py") or found == "__init__.py"
        package_dir = posixpath.dirname(found) if is_package else None
    else:
        package_dir = directory

    symbols_from_package = False
    submodule_hits = 0
    if is_from and package_dir is not None:
        for name in names:
            sub = _join(package_dir, name)
            if sub + ".py" in index.files:
                graph.add(relative, sub + ".py", confidence); submodule_hits += 1
            elif sub + "/__init__.py" in index.files:
                graph.add(relative, sub + "/__init__.py", confidence); submodule_hits += 1
            elif sub not in index.dirs:
                symbols_from_package = True
    elif is_from:
        symbols_from_package = False  # names are symbols of a plain module

    if found is not None:
        # `from . import x` only depends on the package's __init__ when x is defined there.
        own_package = level > 0 and not module
        if not own_package or symbols_from_package:
            graph.add(relative, found, confidence)
        if not level and len(parts) > 1:
            start = posixpath.dirname(found)
            if found.endswith("/__init__.py"):
                start = posixpath.dirname(start)
            for _ in range(len(parts) - 1):
                init = _join(start, "__init__.py")
                inside = bool(start) and relative.startswith(start + "/")
                if init in index.files and not inside:
                    graph.add(relative, init, confidence)
                start = posixpath.dirname(start)


def _js_probe(index: _Index, base: str):
    """Resolve a normalised path (no leading ./) to a scanned file, trying extensions and index files."""
    if base in index.files:
        return base
    ext = posixpath.splitext(base)[1].lower()
    stem = base[: -len(ext)] if ext else base
    if ext in _JS_ESM_SWAP:
        for swap in _JS_ESM_SWAP[ext]:
            if stem + swap in index.files:
                return stem + swap
    for candidate_ext in _JS_RESOLVE_EXTS:
        if base + candidate_ext in index.files:
            return base + candidate_ext
    for candidate_ext in _JS_RESOLVE_EXTS:
        candidate = f"{base}/index{candidate_ext}"
        if candidate in index.files:
            return candidate
    return None


def _resolve_js(graph: _Graph, index: _Index, relative: str, specifier: str) -> None:
    spec = specifier.strip().replace("\\", "/")
    if not spec or spec.startswith(("http://", "https://", "data:", "node:", "/")):
        return
    if spec.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(relative), spec))
        if base in ("..", ".") or base.startswith("../"):
            graph.miss(relative, spec, "beyond_repository_root")
            return
        target = _js_probe(index, base)
        if target:
            graph.add(relative, target, CONFIRMED)
        elif posixpath.splitext(base)[1].lower() in _UNSCANNED_TARGET_EXTS:
            graph.miss(relative, spec, "unsupported_file_type")
        else:
            graph.miss(relative, spec, "not_found")
        return
    for prefix in _ALIAS_PREFIXES:
        if spec.startswith(prefix):
            rest = spec[len(prefix):] if prefix != "#" else spec
            for root_dir in (("src/", "") if prefix in ("@/", "~/") else ()):
                target = _js_probe(index, root_dir + rest)
                if target:
                    graph.add(relative, target, INFERRED)
                    return
            if len(graph.aliases) < 50:
                graph.aliases.add(spec[:MAX_SPECIFIER_CHARS])
            return
    first = spec.split("/", 1)[0]
    if first in index.top_dirs:  # baseUrl-style import such as "src/utils/api"
        target = _js_probe(index, posixpath.normpath(spec))
        if target:
            graph.add(relative, target, INFERRED)
        else:
            graph.miss(relative, spec, "not_found")
    # anything else is an external package: not reported


def _resolve_java(graph: _Graph, relative: str, imports, classes: dict[str, str],
                  packages: dict[str, list[str]], roots: set[str]) -> None:
    for name, static, wildcard in imports:
        if wildcard and not static:
            members = sorted(packages.get(name, []))
            if members:
                for member in members[:MAX_WILDCARD_FILES]:
                    graph.add(relative, member, INFERRED)  # a wildcard does not prove usage
            elif name.split(".", 1)[0] in roots:
                graph.miss(relative, name + ".*", "not_found")
            continue
        parts = name.split(".")
        # `import a.b.C`, `import a.b.C.Inner`, `import static a.b.C.member`, `import static a.b.C.*`
        for cut in range(len(parts), max(len(parts) - 3, 0), -1):
            target = classes.get(".".join(parts[:cut]))
            if target:
                graph.add(relative, target, CONFIRMED)
                break
        else:
            if parts[0] in roots:
                graph.miss(relative, name + (".*" if wildcard else ""), "not_found")


# ---------------------------------------------------------------------------
# Graph algorithms
# ---------------------------------------------------------------------------
def _reach(reverse: dict[str, set[str]], starts) -> set[str]:
    seen: set[str] = set()
    queue = deque(starts)
    while queue:
        node = queue.popleft()
        for parent in reverse.get(node, ()):
            if parent not in seen:
                seen.add(parent)
                queue.append(parent)
    return seen


def _strongly_connected(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Iterative Tarjan: components with more than one file (real import cycles)."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0
    for start in sorted(adjacency):
        if start in index_of:
            continue
        work = [(start, iter(adjacency.get(start, ())))]
        index_of[start] = low[start] = counter; counter += 1
        stack.append(start); on_stack.add(start)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index_of:
                    index_of[child] = low[child] = counter; counter += 1
                    stack.append(child); on_stack.add(child)
                    work.append((child, iter(adjacency.get(child, ()))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index_of[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component = []
                while True:
                    member = stack.pop(); on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    result.append(sorted(component))
    return result


# ---------------------------------------------------------------------------
# Test-file detection
# ---------------------------------------------------------------------------
def _is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    stem = posixpath.splitext(name)[0]
    if any(part in _TEST_DIRS for part in parts[:-1]):
        return True
    if stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec", "_spec")):
        return True
    original = posixpath.splitext(path.split("/")[-1])[0]
    return path.endswith(".java") and bool(re.match(r"^(Test\w+|\w+(Test|Tests|IT|Spec))$", original))


def _naming_match(changed: str, test_path: str) -> bool:
    stem = posixpath.splitext(posixpath.basename(changed))[0].lower()
    if stem in {"index", "__init__", "main", "app"}:
        return False  # far too generic to match by name alone
    test_stem = posixpath.splitext(posixpath.basename(test_path))[0].lower()
    candidates = {f"test_{stem}", f"{stem}_test", f"{stem}.test", f"{stem}.spec", f"{stem}_spec",
                  f"{stem}test", f"{stem}tests", f"test{stem}", f"{stem}spec", f"{stem}it"}
    return test_stem in candidates


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def analyze_change_impact(repository_path: str, changed_files: list[str]) -> dict:
    """Return confirmed/possible dependents, tests and cycles for 1-20 changed files.

    `changed_files` are repository-relative paths (either slash style). Confirmed results
    come only from import statements that resolve unambiguously; guesses are reported
    separately under ``possible_*`` / ``likely_*`` and edges carry a ``confidence`` field.
    """
    if not isinstance(changed_files, list) or not changed_files or len(changed_files) > MAX_CHANGED_FILES:
        raise ValueError(f"Provide between 1 and {MAX_CHANGED_FILES} changed repository-relative file paths.")
    max_files, max_file_bytes, max_total, max_seconds = _limits()
    started = time.monotonic()

    root = Path(repository_path).expanduser().resolve(strict=True)
    inspection = inspect_repository(str(root))
    all_paths = [item["path"] for item in inspection["files"]]
    path_set = set(all_paths)
    lower_map: dict[str, list[str]] = defaultdict(list)
    for path in all_paths:
        lower_map[path.lower()].append(path)

    changed: list[str] = []
    for raw in changed_files:
        match = _match_changed(_normalize_changed(raw), path_set, lower_map)
        if match not in changed:
            changed.append(match)

    # Scan order: changed files first, then files closest to them (likely importers).
    changed_dirs = [posixpath.dirname(path).split("/") for path in changed]

    def closeness(path: str) -> int:
        parts = posixpath.dirname(path).split("/")
        best = 0
        for other in changed_dirs:
            shared = 0
            for left, right in zip(parts, other):
                if left != right:
                    break
                shared += 1
            best = max(best, shared)
        return best

    others = sorted((p for p in all_paths if p not in changed), key=lambda p: (-closeness(p), p))
    capped = len(all_paths) > max_files
    scan_order = (changed + others)[:max_files]

    # Pass 1: read and parse (one file in memory at a time).
    parsed: dict[str, tuple] = {}
    skip_counts: dict[str, int] = defaultdict(int)
    skipped: list[dict] = []
    remaining = max_total
    timed_out = False

    def skip(path: str, reason: str) -> None:
        skip_counts[reason] += 1
        if len(skipped) < MAX_SKIPPED_LISTED:
            skipped.append({"path": path, "reason": reason})

    for position, relative in enumerate(scan_order):
        suffix = posixpath.splitext(relative)[1].lower()
        if suffix not in _ANALYZED_SUFFIXES:
            continue
        if time.monotonic() - started > max_seconds:
            timed_out = True
            skip_counts["time_budget_exhausted"] += sum(
                1 for p in scan_order[position:] if posixpath.splitext(p)[1].lower() in _ANALYZED_SUFFIXES)
            break
        source, remaining, reason = _read_source(root, relative, remaining, max_file_bytes)
        if source is None:
            skip(relative, reason or "unreadable")
            continue
        if suffix == ".py":
            items = _parse_python(source)
            if items is None:
                skip(relative, "syntax_error")
                continue
            parsed[relative] = ("py", items)
        elif suffix == ".java":
            parsed[relative] = ("java", _parse_java(source))
        else:
            parsed[relative] = ("js", _parse_js(source))
        del source

    # Pass 2: resolve.
    index = _Index(all_paths)
    graph = _Graph()
    classes: dict[str, str] = {}
    packages: dict[str, list[str]] = defaultdict(list)
    for relative, (kind, data) in parsed.items():
        if kind == "java" and data[0]:
            classes[f"{data[0]}.{posixpath.splitext(posixpath.basename(relative))[0]}"] = relative
            packages[data[0]].append(relative)
    java_roots = {name.split(".", 1)[0] for name in packages}

    for relative in sorted(parsed):
        kind, data = parsed[relative]
        if kind == "py":
            for item in data:
                _resolve_python(graph, index, relative, item)
        elif kind == "js":
            for specifier in dict.fromkeys(data):
                _resolve_js(graph, index, relative, specifier)
        else:
            _resolve_java(graph, relative, data[1], classes, packages, java_roots)

    reverse_all: dict[str, set[str]] = defaultdict(set)
    reverse_confirmed: dict[str, set[str]] = defaultdict(set)
    for importer, targets in graph.edges.items():
        for target, confidence in targets.items():
            reverse_all[target].add(importer)
            if confidence == CONFIRMED:
                reverse_confirmed[target].add(importer)

    changed_set = set(changed)
    direct = set().union(*(reverse_confirmed.get(path, set()) for path in changed)) - changed_set
    confirmed_all = _reach(reverse_confirmed, changed) - changed_set
    transitive = confirmed_all - direct
    possible = (_reach(reverse_all, changed) - changed_set) - confirmed_all

    confirmed_tests = sorted(p for p in confirmed_all if _is_test_path(p))
    likely_tests = sorted(
        p for p in all_paths
        if p not in confirmed_all and p not in changed_set and _is_test_path(p)
        and any(_naming_match(c, p) for c in changed))
    possible_tests = sorted(p for p in possible if _is_test_path(p) and p not in likely_tests)

    confirmed_adjacency = {
        importer: sorted(t for t, c in targets.items() if c == CONFIRMED)
        for importer, targets in graph.edges.items()}
    cycles = []
    for component in _strongly_connected(confirmed_adjacency):
        touched = sorted(set(component) & changed_set)
        if touched:
            cycles.append({"files": component[:MAX_CYCLE_FILES], "size": len(component),
                           "changed_files_involved": touched})
    cycles.sort(key=lambda item: (-len(item["changed_files_involved"]), item["size"], item["files"]))
    cycles = cycles[:MAX_CYCLES_RETURNED]
    cycle_changed = sorted({path for cycle in cycles for path in cycle["changed_files_involved"]})

    relevant = confirmed_all | possible
    edge_rows = [
        {"importer": importer, "dependency": target, "confidence": confidence}
        for importer in sorted(graph.edges) for target, confidence in sorted(graph.edges[importer].items())
        if importer in relevant or target in changed_set]
    edge_total = len(edge_rows)

    limitations = [
        "This is static file-level import analysis, not a runtime call graph.",
        "Dynamic imports with computed names, reflection, dependency injection, generated code, "
        "tsconfig/vite/webpack aliases and framework conventions may be missed.",
        "Confirmed lists contain only imports that resolve unambiguously; guesses are reported under possible_*/likely_* fields.",
        "Java classes in the same package use each other without imports; those relationships are not detected.",
        "Only supported source files found by repository inspection are considered "
        "(.mjs/.cjs and other unsupported types are not scanned).",
    ]
    unanalyzed = sorted({p for p in changed if posixpath.splitext(p)[1].lower() not in _ANALYZED_SUFFIXES})
    if unanalyzed:
        limitations.append("Imports are only analysed in Python, JavaScript/TypeScript and Java files; "
                           "non-code changed files can only be found as direct import targets: "
                           + ", ".join(unanalyzed[:5]) + ("..." if len(unanalyzed) > 5 else ""))
    if inspection.get("truncated"):
        limitations.append("Repository inspection stopped at its file limit, so some files were never discovered.")
    if capped:
        limitations.append(f"Analysis file cap reached: at most {max_files} of {len(all_paths)} files were read "
                           "(files nearest the changed files were read first).")
    if timed_out:
        limitations.append(f"The {max_seconds:g}-second time budget ran out; remaining files were not analysed.")
    if skip_counts.get("byte_budget_exhausted"):
        limitations.append("The source-reading byte budget was exhausted; some files were not analysed.")
    if skip_counts.get("syntax_error"):
        limitations.append(f"{skip_counts['syntax_error']} Python file(s) could not be parsed, so their imports are unknown.")
    if skipped:
        limitations.append("Some files were skipped (too large, binary, not UTF-8, unreadable); see skipped_files.")
    if graph.aliases:
        limitations.append("Alias imports that could not be mapped were not analysed (see unmapped_aliases).")

    truncated = bool(inspection.get("truncated") or capped or timed_out
                     or skip_counts.get("byte_budget_exhausted") or edge_total > MAX_EDGES_RETURNED)
    return {
        "repository_name": inspection["repository_name"],
        "changed_files": changed,
        "files_discovered": inspection["file_count"],
        "files_scanned": len(parsed),
        "direct_dependents": sorted(direct),
        "transitive_dependents": sorted(transitive),
        "all_affected_files": sorted(confirmed_all),
        "possible_dependents": sorted(possible),
        "related_tests": confirmed_tests,
        "likely_related_tests": sorted(set(likely_tests) | set(possible_tests)),
        "dependency_edges": edge_rows[:MAX_EDGES_RETURNED],
        "dependency_edge_count": edge_total,
        "unresolved_local_references": graph.unresolved,
        "unresolved_reference_count": graph.unresolved_total,
        "unmapped_aliases": sorted(graph.aliases),
        "cycles": cycles,
        "possible_dependency_cycle": bool(cycles),
        "cycle_involving_changed_files": cycle_changed,
        "skipped_files": skipped,
        "skipped_file_count": sum(skip_counts.values()),
        "skipped_reason_counts": dict(sorted(skip_counts.items())),
        "truncated": truncated,
        "limitations": limitations,
        "analysis_kind": "static_import_graph",
        "analysis_version": 2,
    }
