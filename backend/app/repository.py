"""Safe, lightweight repository structure inspection.

This module lists source-file paths only. It does not open or execute files.
"""

import os
import re
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
    "vendor",
    "target",
    ".idea",
    ".vscode",
    "chroma_db",
}

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".php", ".rb",
    ".swift", ".kt", ".kts", ".scala",
    ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml",
    ".md", ".rst", ".txt", ".sql",
    ".sh", ".bat", ".ps1", ".xml",
    ".vue", ".svelte", ".ipynb",
}

SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}
SENSITIVE_NAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "secrets",
    ".npmrc", ".pypirc", ".netrc", ".htpasswd",
}
SENSITIVE_DIRS = {".ssh", ".aws", ".gnupg", ".kube", ".azure", ".docker", "secrets", ".secrets"}
SENSITIVE_NAME_PATTERNS = (
    re.compile(r"^client[_-]?secrets?(?:[_.-].*)?\.(?:json|ya?ml)$"),
    re.compile(r"^service[_-]?account.*\.json$"),
    re.compile(r"^(?:terraform|secrets?)\.tfvars(?:\.json)?$"),
)
MAX_FILES = 5000
MAX_DEPTH = 20


def _is_junction(path: Path) -> bool:
    """Return True for Windows junctions when supported by this Python version."""
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if is_junction else False


def inspect_repository(repository_path: str) -> dict:
    """Return supported file paths under an explicitly selected directory.

    File contents are never read. Symlinks and Windows junctions are skipped,
    as are common dependency, cache, build, and secret-containing paths.
    """
    if not repository_path or not repository_path.strip():
        raise ValueError("Repository path cannot be empty.")

    requested_path = Path(repository_path).expanduser()

    if not requested_path.is_absolute():
        raise ValueError("Please provide an absolute repository path.")

    if requested_path.is_symlink() or _is_junction(requested_path):
        raise ValueError("A symbolic link or junction cannot be the repository root.")

    if not requested_path.exists():
        raise ValueError("Repository path does not exist.")

    if not requested_path.is_dir():
        raise ValueError("Repository path must be a directory.")

    root = requested_path.resolve(strict=True)
    files = []
    skipped_directories = []
    truncated = False

    def record_walk_error(error: OSError) -> None:
        # Do not return absolute paths or operating-system error details.
        try:
            relative = Path(error.filename).relative_to(root).as_posix()
        except (TypeError, ValueError):
            relative = "."
        skipped_directories.append(relative)

    for current_dir, directories, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=record_walk_error,
    ):
        current = Path(current_dir)
        depth = len(current.relative_to(root).parts)

        if depth >= MAX_DEPTH:
            directories[:] = []
            continue

        directories[:] = sorted(
            name
            for name in directories
            if name not in IGNORED_DIRS
            and name.lower() not in SENSITIVE_DIRS
            and not (current / name).is_symlink()
            and not _is_junction(current / name)
        )

        for filename in sorted(filenames):
            file_path = current / filename

            if file_path.is_symlink() or _is_junction(file_path):
                continue

            lower_name = filename.lower()
            suffix = file_path.suffix.lower()

            if lower_name.startswith(".env"):
                continue
            # Match "secrets", "secrets.py", "credentials.json" and similar names.
            if lower_name in SENSITIVE_NAMES or Path(lower_name).stem in SENSITIVE_NAMES:
                continue
            if suffix in SENSITIVE_SUFFIXES:
                continue
            if any(pattern.match(lower_name) for pattern in SENSITIVE_NAME_PATTERNS):
                continue
            if suffix not in SUPPORTED_EXTENSIONS:
                continue

            if len(files) >= MAX_FILES:
                truncated = True
                break

            files.append(
                {
                    "path": file_path.relative_to(root).as_posix(),
                    "extension": suffix,
                }
            )

        if truncated:
            break

    files.sort(key=lambda item: item["path"].lower())

    return {
        "repository_name": root.name,
        "file_count": len(files),
        "truncated": truncated,
        "skipped_directories": sorted(set(skipped_directories)),
        "files": files,
    }
