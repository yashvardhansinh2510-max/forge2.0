import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

// Sites packages the Expo web export as a Cloudflare-compatible worker.

// Keep Expo's standard web graph intact. The experimental Metro graph/tree
// shaking passes can remove Expo's web global initialization, which makes the
// client crash before React mounts (`globalThis.expo.EventEmitter`).
const productionWebEnv = { ...process.env };
const backendUrl = (process.env.BACKEND_URL || '').replace(/\/+$/, '');
try {
  const parsedBackendUrl = new URL(backendUrl);
  if (parsedBackendUrl.protocol !== 'https:' || !parsedBackendUrl.hostname || parsedBackendUrl.username || parsedBackendUrl.password) throw new Error();
} catch {
  throw new Error('BACKEND_URL must be a valid HTTPS URL without embedded credentials for a production Sites build.');
}

const expo = spawn('npx', ['expo', 'export', '--clear', '--platform', 'web', '--output-dir', 'dist/client'], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
  env: productionWebEnv,
});

expo.on('exit', async (code, signal) => {
  if (code !== 0) {
    process.exitCode = code ?? 1;
    return;
  }

  await mkdir('dist', { recursive: true });
  await mkdir('dist/server', { recursive: true });
  await writeFile(
    'dist/server/index.js',
    `// This placeholder is immediately replaced by the worker implementation below.\n`,
  );
  // The worker is the browser-authentication boundary: it exchanges the
  // backend's short-lived login response for an HttpOnly cookie, injects that
  // cookie only on same-origin API proxy calls, and enforces double-submit
  // CSRF on every unsafe cookie-authenticated request.
  const workerSource = await readFile(new URL('./web-worker.mjs', import.meta.url), 'utf8');
  await writeFile('dist/server/index.js', workerSource + '\nexport default createWorker(' + JSON.stringify(backendUrl) + ');\n');
  // Cloudflare Pages advanced mode loads its request handler from _worker.js.
  // Keep the same proxy/auth boundary in the Pages upload so browser API
  // mutations are forwarded to Railway instead of being handled as static
  // asset requests.
  await writeFile('dist/client/_worker.js', await readFile('dist/server/index.js', 'utf8'));
});

expo.on('error', (error) => {
  console.error(error);
  process.exitCode = 1;
});
