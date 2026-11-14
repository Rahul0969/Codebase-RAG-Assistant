// Client-side filtering of semantic search results (no extra backend call).
export function fileExt(path) {
  const name = String(path || '').split(/[\\/]/).pop() || '';
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot).toLowerCase() : '';
}
export function topDirectory(path) {
  const parts = String(path || '').split(/[\\/]/);
  return parts.length > 1 ? parts[0] : '(root)';
}
export function facets(matches) {
  const uniq = (fn) => [...new Set(matches.map(fn).filter(Boolean))].sort();
  return {
    languages: uniq((m) => m.language),
    directories: uniq((m) => topDirectory(m.file_path)),
    extensions: uniq((m) => fileExt(m.file_path)),
  };
}
export function filterMatches(matches, { language = '', directory = '', extension = '' } = {}) {
  return matches.filter((m) =>
    (!language || m.language === language) &&
    (!directory || topDirectory(m.file_path) === directory) &&
    (!extension || fileExt(m.file_path) === extension));
}
