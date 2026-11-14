"""Local Ollama model registry, preferences and resource-aware routing.

All model discovery and inference stay on the loopback Ollama API. Preferences are
stored locally in backend/data and are never sent to a remote service.
"""
from __future__ import annotations
import json, os, re, tempfile
from pathlib import Path
from typing import Any

PREFERENCE_FILE = Path(__file__).resolve().parents[1] / "data" / "model_preferences.json"
VALID_MODES = {"AUTO", "MANUAL"}


def _preference_path() -> Path:
    return Path(os.environ.get("RAG_MODEL_PREFERENCES_FILE", str(PREFERENCE_FILE))).resolve()


def get_preferences() -> dict[str, str]:
    path = _preference_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    mode = str(value.get("mode", "AUTO")).upper() if isinstance(value, dict) else "AUTO"
    model = str(value.get("model", "")).strip() if isinstance(value, dict) else ""
    return {"mode": mode if mode in VALID_MODES else "AUTO", "model": model[:200]}


def save_preferences(mode: str, model: str = "") -> dict[str, str]:
    mode = str(mode).upper().strip()
    model = str(model).strip()
    if mode not in VALID_MODES:
        raise ValueError("Mode must be AUTO or MANUAL.")
    if mode == "MANUAL" and (not model or len(model) > 200):
        raise ValueError("Choose an installed Ollama model for MANUAL mode.")
    path = _preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"mode": mode, "model": model if mode == "MANUAL" else ""}, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix=".model-preferences-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try: os.unlink(temp_name)
        except OSError: pass
    return get_preferences()


def _parameter_billions(item: dict[str, Any]) -> float | None:
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    raw = str(details.get("parameter_size") or "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*B", raw, re.I)
    if match: return float(match.group(1))
    name = str(item.get("name", ""))
    match = re.search(r"(?:^|[-_:])([0-9]+(?:\.[0-9]+)?)b(?:[-_:]|$)", name, re.I)
    return float(match.group(1)) if match else None


def available_memory_gb() -> float | None:
    """Best-effort available physical memory without adding a dependency."""
    try:
        if os.name == "nt":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            state = MEMORYSTATUSEX(); state.dwLength = ctypes.sizeof(state)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                return state.ullAvailPhys / (1024 ** 3)
        else:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 ** 2)
    except Exception:
        return None
    return None


def classify_query(messages: list[dict[str, str]]) -> dict[str, str]:
    user_messages = [str(m.get("content", "")) for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    text = (user_messages[-1] if user_messages else " ".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))).lower()
    # RAG prompts append the natural-language question after the retrieved source context.
    if "question:" in text:
        text = text.rsplit("question:", 1)[-1]
    complex_terms = ("architecture", "design", "refactor", "security", "dependency", "impact", "trace", "debug", "explain the entire", "compare", "root cause")
    code_terms = ("code", "function", "class", "bug", "error", "implement", "write", "fix", "test")
    if any(term in text for term in complex_terms):
        return {"task_type": "deep_analysis", "complexity": "high"}
    if any(term in text for term in code_terms):
        return {"task_type": "code_assistance", "complexity": "medium"}
    return {"task_type": "general_question", "complexity": "low"}


def _parameter_billion_by_name(name: str) -> float:
    match = re.search(r"(?:^|[-_:])([0-9]+(?:\.[0-9]+)?)b(?:[-_:]|$)", name, re.I)
    return float(match.group(1)) if match else 999.0


def choose_model(models: list[dict[str, Any]], messages: list[dict[str, str]], configured_model: str) -> tuple[str, dict[str, str]]:
    prefs = get_preferences()
    if prefs["mode"] == "MANUAL":
        installed = {str(item.get("name", "")) for item in models}
        selected = prefs["model"]
        if selected not in installed:
            raise ValueError(f"Selected manual model '{selected}' is no longer installed. Switch to AUTO or select an installed model.")
        return selected, {"mode": "MANUAL", "reason": "Using the model selected in Settings."}
    classification = classify_query(messages)
    available = available_memory_gb()
    # Conservative parameter budgets: leave room for Windows, embeddings and Chroma.
    budget = 2.0 if available is None else max(0.8, min(8.0, available * 0.55))
    candidates = []
    for item in models:
        name = str(item.get("name", ""))
        params = _parameter_billions(item)
        if not name: continue
        # Unknown parameter size is allowed only as a last-resort candidate.
        if params is not None and params > budget: continue
        candidates.append((params if params is not None else 0.25, name))
    if not candidates:
        installed = [str(item.get("name", "")) for item in models if item.get("name")]
        if installed:
            selected = min(installed, key=lambda name: (_parameter_billion_by_name(name), name))
        else:
            selected = configured_model
    else:
        candidates.sort()
        # Low/medium tasks favor small models; high complexity can use the largest safe model.
        if classification["complexity"] == "high": selected = candidates[-1][1]
        elif classification["complexity"] == "medium": selected = candidates[min(len(candidates)-1, max(0, len(candidates)//2))][1]
        else: selected = candidates[0][1]
    reason = f"AUTO selected a {classification['complexity']}-tier model for {classification['task_type']} within the estimated local memory budget."
    return selected, {"mode": "AUTO", "reason": reason, **classification, "available_memory_gb": round(available, 2) if available is not None else None}
