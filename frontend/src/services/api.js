// Centralized client for the local FastAPI backend. All network access goes through here.

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8000';

export const TIMEOUTS = {
  health: 6_000,
  inspect: 60_000,
  status: 30_000,
  index: 30 * 60_000, // indexing a large repository on a small PC can take a long time
  search: 90_000,
  ask: 5 * 60_000, // a local model may need minutes on low-memory hardware
  report: 3 * 60_000, // optional local LLM summary; deterministic report is the fallback
};

/** One error type for everything that can go wrong, so the UI can show friendly messages. */
export class ApiError extends Error {
  /**
   * @param {{kind: 'network'|'timeout'|'http'|'invalid_response'|'config', message: string,
   *          status?: number|null, code?: string|null}} details
   */
  constructor({ kind, message, status = null, code = null }) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

export function resolveBaseUrl(raw) {
  const value = (raw ?? '').toString().trim() || DEFAULT_BASE_URL;
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new ApiError({ kind: 'config', message: 'The backend URL is not a valid address.' });
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new ApiError({ kind: 'config', message: 'The backend URL must start with http:// or https://.' });
  }
  return url.origin + url.pathname.replace(/\/+$/, '');
}

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);

export function isLoopbackHost(hostname) {
  return LOOPBACK_HOSTS.has(String(hostname).toLowerCase()) || String(hostname).endsWith('.localhost');
}

/**
 * Chrome-family browsers ask the user for "local network" permission when a public website
 * calls a loopback address, and the request should declare its target address space.
 * Other browsers ignore the extra option.
 */
export function shouldDeclareLoopback(baseUrl, pageHostname) {
  try {
    return isLoopbackHost(new URL(baseUrl).hostname) && !!pageHostname && !isLoopbackHost(pageHostname);
  } catch {
    return false;
  }
}

function explainDetail(detail, status) {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length > 0) {
    const parts = detail
      .map((item) => {
        const where = Array.isArray(item?.loc) ? item.loc.filter((p) => p !== 'body').join('.') : '';
        const what = typeof item?.msg === 'string' ? item.msg : 'is invalid';
        return where ? `${where}: ${what}` : what;
      })
      .slice(0, 3);
    return `Please check your input (${parts.join('; ')}).`;
  }
  return `The backend returned an error (HTTP ${status}).`;
}

const is = {
  object: (v) => v !== null && typeof v === 'object' && !Array.isArray(v),
  array: Array.isArray,
  string: (v) => typeof v === 'string',
  number: (v) => typeof v === 'number' && Number.isFinite(v),
  boolean: (v) => typeof v === 'boolean',
};

// Minimal shape checks so a mismatched backend version shows a clear message instead of a crash.
const SHAPES = {
  health: { status: is.string, ollama: is.object, embedding: is.object, chromadb: is.object },
  inspect: { repository_name: is.string, file_count: is.number, files: is.array },
  status: { indexed: is.boolean, chunk_count: is.number },
  index: { chunk_count: is.number, indexed_count: is.number, embedding_model: is.string },
  search: { matches: is.array, result_count: is.number },
  ask: {
    answer: is.string, evidence_status: is.string, validation_passed: is.boolean,
    citations: is.array, retrieved_chunks: is.array, model: is.string,
  },
  report: { report_id: is.string, repository_name: is.string, format: is.string, content: is.string, filename: is.string },
  reports: { reports: is.array },
  reportContent: { report_id: is.string, filename: is.string, content: is.string },
  impact: { repository_name: is.string, changed_files: is.array, direct_dependents: is.array, transitive_dependents: is.array, related_tests: is.array, limitations: is.array },
};

function checkShape(name, data) {
  const shape = SHAPES[name];
  const ok = is.object(data) && Object.entries(shape).every(([key, test]) => test(data[key]));
  if (!ok) {
    throw new ApiError({
      kind: 'invalid_response',
      message: 'The backend sent a reply this page does not understand. The backend and the web page may be different versions.',
    });
  }
  return data;
}

export function createApiClient({
  baseUrl = import.meta.env?.VITE_API_BASE_URL,
  fetchImpl = (...args) => globalThis.fetch(...args),
  timeouts = TIMEOUTS,
  pageHostname = globalThis.location?.hostname,
} = {}) {
  const root = resolveBaseUrl(baseUrl);
  const declareLoopback = shouldDeclareLoopback(root, pageHostname);

  async function request(name, path, { method = 'GET', body } = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeouts[name]);

    let response;
    let text;
    try {
      const init = {
        method,
        headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
        credentials: 'omit',
        cache: 'no-store',
      };
      if (declareLoopback) init.targetAddressSpace = 'loopback';
      response = await fetchImpl(`${root}${path}`, init);
      text = await response.text();
    } catch (cause) {
      if (timedOut) {
        throw new ApiError({
          kind: 'timeout',
          message: `The backend did not answer within ${Math.round(timeouts[name] / 1000)} seconds.`,
        });
      }
      throw new ApiError({ kind: 'network', message: 'Could not connect to the local backend.' });
    } finally {
      clearTimeout(timer);
    }

    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = null;
      }
    }
    if (!response.ok) {
      throw new ApiError({
        kind: 'http',
        status: response.status,
        code: response.headers?.get?.('x-error-code') ?? null,
        message: explainDetail(data?.detail, response.status),
      });
    }
    return checkShape(name, data);
  }

  return {
    baseUrl: root,
    health: () => request('health', '/health'),
    inspect: (repositoryPath) =>
      request('inspect', '/repository/inspect', { method: 'POST', body: { repository_path: repositoryPath } }),
    status: (repositoryPath) =>
      request('status', '/repository/status', { method: 'POST', body: { repository_path: repositoryPath } }),
    index: (repositoryPath, { maxChars, batchSize } = {}) =>
      request('index', '/repository/index', {
        method: 'POST',
        body: {
          repository_path: repositoryPath,
          ...(maxChars ? { max_chars: maxChars } : {}),
          ...(batchSize ? { batch_size: batchSize } : {}),
        },
      }),
    search: (repositoryPath, query, topK = 5) =>
      request('search', '/repository/search', {
        method: 'POST',
        body: { repository_path: repositoryPath, query, top_k: topK },
      }),
    ask: (repositoryPath, question, { topK = 5 } = {}) =>
      request('ask', '/repository/ask', {
        method: 'POST',
        body: { repository_path: repositoryPath, question, top_k: topK, include_source_text: true },
      }),
    generateReport: (repositoryPath, format = 'md', useAiSummary = true) =>
      request('report', '/api/reports/generate', {
        method: 'POST', body: { repository_path: repositoryPath, format, use_ai_summary: useAiSummary },
      }),
    listReports: () => request('reports', '/api/reports'),
    getReport: (reportId) => request('reportContent', `/api/reports/${encodeURIComponent(reportId)}`),
    analyzeImpact: (repositoryPath, changedFiles) => request('impact', '/repository/impact', {
      method: 'POST', body: { repository_path: repositoryPath, changed_files: changedFiles },
    }),
  };
}

let shared = null;
/** The app-wide client, created lazily so tests and tools can import this module freely. */
export function getApi() {
  if (!shared) shared = createApiClient();
  return shared;
}

/** Like getApi, but a bad VITE_API_BASE_URL gives a client whose calls fail with a clear error. */
export function getApiSafe() {
  try {
    return getApi();
  } catch (error) {
    const fail = () => Promise.reject(error);
    return { baseUrl: '(invalid address)', health: fail, inspect: fail, status: fail, index: fail, search: fail, ask: fail, generateReport: fail, listReports: fail, getReport: fail };
  }
}
