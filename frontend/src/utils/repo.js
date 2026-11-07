// Small helpers for repository information shown in the UI.

const LANGUAGE_NAMES = {
  '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript (JSX)', '.mjs': 'JavaScript',
  '.ts': 'TypeScript', '.tsx': 'TypeScript (TSX)', '.java': 'Java', '.go': 'Go', '.rs': 'Rust',
  '.c': 'C', '.h': 'C/C++ header', '.cpp': 'C++', '.cc': 'C++', '.hpp': 'C++ header',
  '.cs': 'C#', '.php': 'PHP', '.rb': 'Ruby', '.kt': 'Kotlin', '.swift': 'Swift',
  '.html': 'HTML', '.css': 'CSS', '.json': 'JSON', '.md': 'Markdown', '.sql': 'SQL',
  '.sh': 'Shell', '.yaml': 'YAML', '.yml': 'YAML', '.toml': 'TOML',
};

export function languageName(extension) {
  return LANGUAGE_NAMES[String(extension).toLowerCase()] ?? String(extension || 'other');
}

/** Counts files by extension: [{extension, language, count}], largest first. */
export function summarizeFiles(files = []) {
  const counts = new Map();
  for (const file of files) counts.set(file.extension, (counts.get(file.extension) ?? 0) + 1);
  return [...counts.entries()]
    .map(([extension, count]) => ({ extension, language: languageName(extension), count }))
    .sort((a, b) => b.count - a.count || a.extension.localeCompare(b.extension));
}

/** Returns an error message for an obviously wrong path, or null. */
export function checkPathInput(value) {
  const path = (value ?? '').trim();
  if (!path) return 'Enter the full path of a project folder.';
  if (path.length > 4096) return 'That path is too long.';
  const absolute = /^[A-Za-z]:[\\/]/.test(path) || path.startsWith('/') || path.startsWith('\\\\');
  if (!absolute) return 'Use a full path, for example C:\\Users\\You\\Desktop\\my-project.';
  return null;
}

export function repositoryLabel(path) {
  const parts = String(path ?? '').split(/[\\/]+/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : '';
}

/** Reducer for one asynchronous operation: idle -> loading -> success | error. */
export const initialOperation = { status: 'idle', data: null, error: null };

export function operationReducer(state, action) {
  switch (action.type) {
    case 'start':
      return { status: 'loading', data: null, error: null };
    case 'success':
      return { status: 'success', data: action.data, error: null };
    case 'error':
      return { status: 'error', data: null, error: action.error };
    case 'reset':
      return initialOperation;
    default:
      return state;
  }
}
