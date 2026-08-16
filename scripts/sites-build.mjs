import { mkdir, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

// Sites packages the Expo web export as a Cloudflare-compatible worker.

// Keep Expo's standard web graph intact. The experimental Metro graph/tree
// shaking passes can remove Expo's web global initialization, which makes the
// client crash before React mounts (`globalThis.expo.EventEmitter`).
const productionWebEnv = { ...process.env };

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
    `const SECURITY_HEADERS = { 'Content-Security-Policy': \"default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https://buildcon-backend-production.up.railway.app https://*.ingest.sentry.io; form-action 'self'\", 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()', 'Strict-Transport-Security': 'max-age=63072000; includeSubDomains' };\nfunction secure(response) { const headers = new Headers(response.headers); for (const [key, value] of Object.entries(SECURITY_HEADERS)) headers.set(key, value); return new Response(response.body, { status: response.status, statusText: response.statusText, headers }); }\nasync function fetchAsset(request, env, pathname) { const base = new URL(request.url); for (const prefix of ['', '/client', '/dist', '/dist/client']) { const candidate = new URL(prefix + (pathname || '/'), base); const response = await env.ASSETS.fetch(new Request(candidate, request)); if (response.status !== 404) return response; } return new Response('Not Found', { status: 404 }); }\nconst worker = { async fetch(request, env) { const url = new URL(request.url); if (url.pathname.startsWith('/api/')) { const upstream = new URL(url.pathname + url.search, 'https://buildcon-backend-production.up.railway.app'); const headers = new Headers(request.headers); headers.set('X-Forwarded-Proto', 'https'); headers.set('X-Forwarded-Host', url.host); return secure(await fetch(new Request(upstream, { method: request.method, headers, body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body, redirect: 'manual' }))); } const asset = await fetchAsset(request, env, url.pathname); if (asset.status !== 404) return secure(asset); return secure(await fetchAsset(request, env, '/index.html')); } };\nexport default worker;\n`,
  );
  // The worker is the browser-authentication boundary: it exchanges the
  // backend's short-lived login response for an HttpOnly cookie, injects that
  // cookie only on same-origin API proxy calls, and enforces double-submit
  // CSRF on every unsafe cookie-authenticated request.
  await writeFile('dist/server/index.js', String.raw`const SECURITY_HEADERS = { 'Content-Security-Policy': "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https://*.ingest.sentry.io; form-action 'self'", 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()', 'Strict-Transport-Security': 'max-age=63072000; includeSubDomains' };
function secure(response) { const headers = new Headers(response.headers); for (const [key, value] of Object.entries(SECURITY_HEADERS)) headers.set(key, value); return new Response(response.body, { status: response.status, statusText: response.statusText, headers }); }
function cookie(request, name) { return request.headers.get('Cookie')?.split(';').map((part) => part.trim()).find((part) => part.startsWith(name + '='))?.slice(name.length + 1); }
function clearWebSession(response) { const headers = new Headers(response.headers); headers.append('Set-Cookie', 'forge_session=; Path=/api; Max-Age=0; Secure; HttpOnly; SameSite=Strict'); headers.append('Set-Cookie', 'forge_csrf=; Path=/api; Max-Age=0; Secure; SameSite=Strict'); return new Response(response.body, { status: response.status, statusText: response.statusText, headers }); }
async function loginWebSession(response) { const payload = await response.clone().json(); const token = payload?.access_token; if (!token) return response; const csrf = crypto.randomUUID() + crypto.randomUUID(); const headers = new Headers(response.headers); headers.append('Set-Cookie', 'forge_session=' + encodeURIComponent(token) + '; Path=/api; Secure; HttpOnly; SameSite=Strict'); headers.append('Set-Cookie', 'forge_csrf=' + encodeURIComponent(csrf) + '; Path=/api; Secure; SameSite=Strict'); payload.access_token = ''; return new Response(JSON.stringify(payload), { status: response.status, headers }); }
async function fetchAsset(request, env, pathname) { const base = new URL(request.url); for (const prefix of ['', '/client', '/dist', '/dist/client']) { const candidate = new URL(prefix + (pathname || '/'), base); const response = await env.ASSETS.fetch(new Request(candidate, request)); if (response.status !== 404) return response; } return new Response('Not Found', { status: 404 }); }
const worker = { async fetch(request, env) { const url = new URL(request.url); if (url.pathname.startsWith('/api/')) { const session = cookie(request, 'forge_session'); const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method); if (unsafe && session && (request.headers.get('Origin') !== url.origin || request.headers.get('X-CSRF-Token') !== cookie(request, 'forge_csrf'))) return secure(new Response(JSON.stringify({ detail: 'CSRF validation failed' }), { status: 403, headers: { 'Content-Type': 'application/json' } })); const upstream = new URL(url.pathname + url.search, 'https://buildcon-backend-production.up.railway.app'); const headers = new Headers(request.headers); headers.delete('Cookie'); if (session && !headers.has('Authorization')) headers.set('Authorization', 'Bearer ' + decodeURIComponent(session)); headers.set('X-Forwarded-Proto', 'https'); headers.set('X-Forwarded-Host', url.host); let response = await fetch(new Request(upstream, { method: request.method, headers, body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body, redirect: 'manual' })); if (response.ok && (url.pathname === '/api/auth/login' || url.pathname === '/api/auth/customer/login')) response = await loginWebSession(response); if (url.pathname === '/api/auth/logout') response = clearWebSession(response); return secure(response); } const asset = await fetchAsset(request, env, url.pathname); if (asset.status !== 404) return secure(asset); return secure(await fetchAsset(request, env, '/index.html')); } };
export default worker;
`);
});

expo.on('error', (error) => {
  console.error(error);
  process.exitCode = 1;
});
