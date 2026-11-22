/**
 * Dev-server proxy. Same targets as before (backend on :8765), but with a real
 * error handler: JSON config cannot hold functions, so the old "on.error" string was ignored
 * and every dropped /ws socket printed a noisy ECONNABORTED stack trace.
 */
const TARGET = 'http://127.0.0.1:8765';
const QUIET_CODES = new Set(['ECONNABORTED', 'ECONNRESET', 'EPIPE', 'ECONNREFUSED']);

function quietErrors(proxy) {
  const swallow = (err) => {
    if (err && QUIET_CODES.has(err.code)) return;
    console.warn('[proxy]', err && err.message);
  };
  proxy.on('error', swallow);
  proxy.on('proxyReqWs', (_req, socket) => socket.on('error', swallow));
}

const base = { target: TARGET, secure: false, changeOrigin: true, logLevel: 'warn' };

module.exports = {
  '/api': { ...base },
  '/ws': { ...base, ws: true, configure: quietErrors },
  '/news_reports': { ...base },
  '/reports': { ...base },
};
