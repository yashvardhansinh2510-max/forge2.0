import { mkdir, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

// Sites packages the Expo web export as a Cloudflare-compatible worker.

// Metro's graph optimizer and used-export pass are required together. They let
// the static web export remove unused exports from the native runtime and route
// dependencies while preserving Expo Router's production async-route chunks.
// Keep these flags scoped to the web export: native development and EAS builds
// must continue to use Expo's default resolver/runtime behavior.
const productionWebEnv = {
  ...process.env,
  EXPO_UNSTABLE_METRO_OPTIMIZE_GRAPH: '1',
  EXPO_UNSTABLE_TREE_SHAKING: '1',
};

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
    `async function fetchAsset(request, env, pathname) {\n  const base = new URL(request.url);\n  for (const prefix of ['', '/client', '/dist', '/dist/client']) {\n    const candidate = new URL(prefix + (pathname || '/'), base);\n    const response = await env.ASSETS.fetch(new Request(candidate, request));\n    if (response.status !== 404) return response;\n  }\n  return new Response('Not Found', { status: 404 });\n}\n\nconst worker = {\n  async fetch(request, env) {\n    const url = new URL(request.url);\n    const asset = await fetchAsset(request, env, url.pathname);\n    if (asset.status !== 404) return asset;\n    return fetchAsset(request, env, '/index.html');\n  },\n};\n\nexport default worker;\n`,
  );
});

expo.on('error', (error) => {
  console.error(error);
  process.exitCode = 1;
});
