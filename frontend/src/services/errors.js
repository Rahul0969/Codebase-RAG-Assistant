// Turns an ApiError (or anything else) into a short, friendly message for the UI.

const BY_CODE = {
  not_indexed: {
    title: 'This repository is not indexed yet',
    hint: 'Open the Repository page and click "Index repository", then try again.',
  },
  repository_path_invalid: {
    title: 'This folder cannot be used',
    hint: 'Choose a normal project folder, for example C:\\Users\\You\\Desktop\\my-project.',
  },
  invalid_request: {
    title: 'The request was not accepted',
    hint: 'Check the folder path and your input, then try again.',
  },
  ollama_unavailable: {
    title: 'Ollama is not running',
    hint: 'Install and start Ollama (open the Ollama app or run "ollama serve"), then try again.',
  },
  model_not_found: {
    title: 'The language model is not installed',
    hint: 'Download it once with the command shown above, then try again.',
  },
  llm_timeout: {
    title: 'The model took too long to answer',
    hint: 'Small computers can be slow. Try again, ask a shorter question, or use a smaller model.',
  },
  llm_bad_response: {
    title: 'The model returned an unusable reply',
    hint: 'Try again. If it keeps happening, restart Ollama.',
  },
  llm_config_invalid: {
    title: 'The model settings are invalid',
    hint: 'Check the OLLAMA_* values in backend\\.env.',
  },
  service_unavailable: {
    title: 'A local service is unavailable',
    hint: 'Check that the backend packages are installed (run setup.bat) and look at the backend window for details.',
  },
};

export function describeError(error, { baseUrl = '' } = {}) {
  if (!error || error.name !== 'ApiError') {
    return {
      title: 'Something unexpected happened',
      message: 'The page hit an unexpected problem. Reload it and try again.',
      hint: '',
      kind: 'unknown',
    };
  }
  if (error.kind === 'network') {
    return {
      title: 'Cannot reach the local backend',
      message: baseUrl ? `Nothing answered at ${baseUrl}.` : error.message,
      hint: 'Start the backend (start.bat), check the address in Settings, and allow "local network" access if your browser asks. See the README, section "Hosted frontend and your browser".',
      kind: 'network',
    };
  }
  if (error.kind === 'timeout') {
    return {
      title: 'The backend is taking too long',
      message: error.message,
      hint: 'Large repositories and low-memory computers can be slow. Wait a little and try again.',
      kind: 'timeout',
    };
  }
  if (error.kind === 'invalid_response') {
    return {
      title: 'Unexpected reply from the backend',
      message: error.message,
      hint: 'Update the backend and the web page to the same version.',
      kind: 'invalid_response',
    };
  }
  if (error.kind === 'config') {
    return { title: 'Backend address problem', message: error.message, hint: 'Check VITE_API_BASE_URL.', kind: 'config' };
  }
  const known = BY_CODE[error.code];
  if (known) return { ...known, message: error.message, kind: error.code };
  if (error.status === 422) {
    return { title: 'Check your input', message: error.message, hint: '', kind: 'validation' };
  }
  return {
    title: 'The backend reported a problem',
    message: error.message,
    hint: 'Look at the backend window for details.',
    kind: 'http',
  };
}
