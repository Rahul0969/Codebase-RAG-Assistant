import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { getApiSafe } from '../services/api.js';
import { checkPathInput, initialOperation, operationReducer } from '../utils/repo.js';

const STORAGE_KEY = 'rag.repositoryPath';
const HEALTH_INTERVAL_MS = 20_000;

function loadPath() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return ''; // storage can be unavailable (private mode); the path is not secret
  }
}

function savePath(value) {
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* ignore */
  }
}

let nextAskId = 1;

/** All state and actions for the workspace. Components only render and call these. */
export function useWorkspace(api = getApiSafe()) {
  const [health, setHealth] = useState({ state: 'checking', data: null, error: null });
  const [modelRouting, setModelRouting] = useState({ models: [], preferences: { mode: 'AUTO', model: '' } });
  const [lastUsedModel, setLastUsedModel] = useState('');
  const [repoPath, setRepoPathState] = useState(loadPath);
  const [inspect, dispatchInspect] = useReducer(operationReducer, initialOperation);
  const [index, dispatchIndex] = useReducer(operationReducer, initialOperation);
  const [indexInfo, setIndexInfo] = useState(null);
  const [search, dispatchSearch] = useReducer(operationReducer, initialOperation);
  const [lastQuery, setLastQuery] = useState('');
  const [asks, setAsks] = useState([]);
  const [pathError, setPathError] = useState(null);

  // Results that arrive after the user switched repository must be ignored.
  const pathRef = useRef(repoPath);
  pathRef.current = repoPath;

  const refreshModelRouting = useCallback(async () => {
    try { const data = await api.listModels(); setModelRouting(data); return data; }
    catch { return null; }
  }, [api]);

  const checkBackend = useCallback(async () => {
    try {
      const data = await api.health();
      setHealth({ state: 'online', data, error: null });
      await refreshModelRouting();
    } catch (error) {
      setHealth({ state: 'offline', data: null, error });
    }
  }, [api, refreshModelRouting]);

  useEffect(() => {
    checkBackend();
    const timer = setInterval(checkBackend, HEALTH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [checkBackend]);

  const refreshIndexInfo = useCallback(
    async (path) => {
      try {
        const info = await api.status(path);
        if (pathRef.current === path) setIndexInfo(info);
        return info;
      } catch {
        if (pathRef.current === path) setIndexInfo(null);
        return null;
      }
    },
    [api],
  );

  const setRepoPath = useCallback((value) => {
    setRepoPathState(value);
    savePath(value);
    setPathError(null);
    dispatchInspect({ type: 'reset' });
    dispatchIndex({ type: 'reset' });
    dispatchSearch({ type: 'reset' });
    setIndexInfo(null);
    setAsks([]);
    setLastQuery('');
  }, []);

  const inspectRepository = useCallback(async () => {
    const problem = checkPathInput(repoPath);
    setPathError(problem);
    if (problem) return;
    const path = repoPath.trim();
    dispatchInspect({ type: 'start' });
    try {
      const data = await api.inspect(path);
      if (pathRef.current !== repoPath) return;
      dispatchInspect({ type: 'success', data });
      await refreshIndexInfo(path);
    } catch (error) {
      if (pathRef.current === repoPath) dispatchInspect({ type: 'error', error });
    }
  }, [api, repoPath, refreshIndexInfo]);

  const indexRepository = useCallback(async () => {
    const problem = checkPathInput(repoPath);
    setPathError(problem);
    if (problem) return;
    const path = repoPath.trim();
    dispatchIndex({ type: 'start' });
    try {
      const data = await api.index(path);
      if (pathRef.current !== repoPath) return;
      dispatchIndex({ type: 'success', data });
      await refreshIndexInfo(path);
    } catch (error) {
      if (pathRef.current === repoPath) dispatchIndex({ type: 'error', error });
    }
  }, [api, repoPath, refreshIndexInfo]);

  const runSearch = useCallback(
    async (query, topK) => {
      const cleaned = query.trim();
      if (!cleaned) return;
      const path = repoPath.trim();
      setLastQuery(cleaned);
      dispatchSearch({ type: 'start' });
      try {
        const data = await api.search(path, cleaned, topK);
        if (pathRef.current === repoPath) dispatchSearch({ type: 'success', data });
      } catch (error) {
        if (pathRef.current === repoPath) dispatchSearch({ type: 'error', error });
      }
    },
    [api, repoPath],
  );

  const askQuestion = useCallback(
    async (question, topK) => {
      const cleaned = question.trim();
      if (!cleaned) return;
      const path = repoPath.trim();
      const id = nextAskId++;
      setAsks((items) => [...items, { id, question: cleaned, status: 'loading', result: null, error: null }]);
      const finish = (patch) =>
        setAsks((items) => items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
      try {
        const result = await api.ask(path, cleaned, { topK });
        finish({ status: 'done', result });
        if (result?.model) setLastUsedModel(result.model);
      } catch (error) {
        finish({ status: 'error', error });
      }
    },
    [api, repoPath],
  );

  const clearAsks = useCallback(() => setAsks([]), []);

  const repositoryReady = !!indexInfo && indexInfo.indexed && indexInfo.chunk_count > 0;
  const asking = asks.some((item) => item.status === 'loading');

  return {
    api, health, checkBackend, modelRouting, refreshModelRouting, lastUsedModel, repoPath, setRepoPath, pathError,
    inspect, inspectRepository, index, indexRepository, indexInfo, repositoryReady,
    search, lastQuery, runSearch, asks, asking, askQuestion, clearAsks,
  };
}
