import { isLoopbackHost } from '../services/api.js';

/** Shown when the backend cannot be reached: concrete steps, tailored to where this page is hosted. */
export default function BackendHelp({ baseUrl }) {
  const hosted = !isLoopbackHost(globalThis.location?.hostname ?? 'localhost');
  return (
    <div className="notice notice-bad" role="alert">
      <strong>The local backend is not reachable</strong>
      <p>Nothing answered at <code>{baseUrl}</code>.</p>
      <ol>
        <li>On the computer that holds your code, double-click <code>start.bat</code> and keep its window open.</li>
        <li>Use "Check again".</li>
        {hosted ? (
          <>
            <li>
              This page is hosted online. Chrome, Edge and Firefox may ask whether this site may connect to "devices on your local network" or
              "loopback": choose Allow. If you chose Block earlier, re-enable it in the browser's site settings for this page.
            </li>
            <li>
              Safari blocks a secure web page from talking to a plain-HTTP local address. In Safari, open the page that start.bat serves at{' '}
              <code>http://127.0.0.1:5173</code> instead.
            </li>
            <li>The backend must list this site in <code>RAG_TRUSTED_ORIGINS</code> (backend\.env).</li>
          </>
        ) : null}
      </ol>
    </div>
  );
}
