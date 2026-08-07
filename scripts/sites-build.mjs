import { mkdir, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';

const expo = spawn('npx', ['expo', 'export', '--platform', 'web', '--output-dir', 'dist'], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

expo.on('exit', async (code, signal) => {
  if (code !== 0) {
    process.exitCode = code ?? 1;
    return;
  }

  await mkdir('dist/server', { recursive: true });
  await writeFile(
    'dist/server/index.js',
    `const worker = {\n  async fetch(request, env) {\n    const asset = await env.ASSETS.fetch(request);\n    if (asset.status !== 404) return asset;\n    const url = new URL(request.url);\n    if (url.pathname.startsWith('/_expo/') || url.pathname.includes('.')) return asset;\n    return env.ASSETS.fetch(new Request(new URL('/index.html', url), request));\n  },\n};\n\nexport default worker;\n`,
  );
});

expo.on('error', (error) => {
  console.error(error);
  process.exitCode = 1;
});
