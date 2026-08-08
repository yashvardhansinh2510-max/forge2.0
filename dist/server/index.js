async function fetchAsset(request, env, pathname) {
  const base = new URL(request.url);
  for (const prefix of ['', '/client', '/dist', '/dist/client']) {
    const candidate = new URL(prefix + (pathname || '/'), base);
    const response = await env.ASSETS.fetch(new Request(candidate, request));
    if (response.status !== 404) return response;
  }
  return new Response('Not Found', { status: 404 });
}

const worker = {
  async fetch(request, env) {
    const url = new URL(request.url);
    const asset = await fetchAsset(request, env, url.pathname);
    if (asset.status !== 404) return asset;
    return fetchAsset(request, env, '/index.html');
  },
};

export default worker;
