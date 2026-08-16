const BACKEND = 'https://buildcon-backend-production.up.railway.app';

const SECURITY_HEADERS = {
  'Content-Security-Policy': "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https://*.ingest.sentry.io; form-action 'self'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Strict-Transport-Security': 'max-age=63072000; includeSubDomains',
};

function cookie(req, name) {
  return req.headers.cookie?.split(';').map((part) => part.trim()).find((part) => part.startsWith(`${name}=`))?.slice(name.length + 1);
}

function writeSecurityHeaders(res) {
  Object.entries(SECURITY_HEADERS).forEach(([key, value]) => res.setHeader(key, value));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

export const config = { api: { bodyParser: false } };

export default async function handler(req, res) {
  writeSecurityHeaders(res);
  const path = Array.isArray(req.query.path) ? req.query.path.join('/') : req.query.path;
  if (!path) return res.status(404).json({ detail: 'Not Found' });

  const session = cookie(req, 'forge_session');
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(req.method);
  const origin = req.headers.origin;
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  const expectedOrigin = host ? `https://${host}` : undefined;
  if (unsafe && session && (origin !== expectedOrigin || req.headers['x-csrf-token'] !== cookie(req, 'forge_csrf'))) {
    return res.status(403).json({ detail: 'CSRF validation failed' });
  }

  const upstream = new URL(`/api/${path}`, BACKEND);
  Object.entries(req.query).forEach(([key, value]) => {
    if (key !== 'path') upstream.searchParams.set(key, Array.isArray(value) ? value[0] : value);
  });
  const headers = new Headers();
  Object.entries(req.headers).forEach(([key, value]) => {
    if (!['cookie', 'host', 'connection'].includes(key) && value) headers.set(key, Array.isArray(value) ? value.join(', ') : value);
  });
  if (session && !headers.has('authorization')) headers.set('authorization', `Bearer ${decodeURIComponent(session)}`);
  headers.set('x-forwarded-proto', 'https');
  if (host) headers.set('x-forwarded-host', host);

  const body = unsafe ? await readBody(req) : undefined;
  const upstreamResponse = await fetch(upstream, { method: req.method, headers, body: body?.length ? body : undefined });
  const isLogin = upstreamResponse.ok && (path === 'auth/login' || path === 'auth/customer/login');
  if (isLogin) {
    const payload = await upstreamResponse.json();
    const token = payload?.access_token;
    if (token) {
      const csrf = crypto.randomUUID() + crypto.randomUUID();
      res.setHeader('Set-Cookie', [
        `forge_session=${encodeURIComponent(token)}; Path=/api; Secure; HttpOnly; SameSite=Strict`,
        `forge_csrf=${encodeURIComponent(csrf)}; Path=/; Secure; SameSite=Strict`,
      ]);
      payload.access_token = '';
      return res.status(upstreamResponse.status).json(payload);
    }
  }
  if (path === 'auth/logout') {
    res.setHeader('Set-Cookie', [
      'forge_session=; Path=/api; Max-Age=0; Secure; HttpOnly; SameSite=Strict',
      'forge_csrf=; Path=/; Max-Age=0; Secure; SameSite=Strict',
    ]);
  }
  const contentType = upstreamResponse.headers.get('content-type');
  if (contentType) res.setHeader('Content-Type', contentType);
  return res.status(upstreamResponse.status).send(Buffer.from(await upstreamResponse.arrayBuffer()));
}
