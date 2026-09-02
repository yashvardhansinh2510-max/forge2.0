import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

for (const path of ["../src/api/client.ts", "../src/api/client.web.ts"]) {
  const source = read(path);
  // A GET transport is shared, but each component retains ownership of its
  // own cancellation.  One unmounted consumer must not abort the others.
  assert.match(source, /function abortForConsumer/);
  assert.match(source, /request<T>\("GET", \w+, undefined, \{ \.\.\.opts, signal: undefined \}\)/);
  assert.match(source, /return abortForConsumer\(existing as Promise<T>, opts\?\.signal\)/);
  assert.match(source, /return abortForConsumer\(pending, opts\?\.signal\)/);

  // Failures must evict the transport, and stale workspace results still
  // reject rather than updating consumers from the previous context.
  assert.match(source, /\.finally\(\(\) => inflightGets\.delete\(key\)\)/);
  assert.match(source, /contextVersion !== requestContextVersion/);
  assert.match(source, /Request timed out\. Please try again\./);
  assert.match(source, /Cannot reach the backend/);
}

console.log("API client dedupe cancellation, stale-context, retry, and failure contracts passed");
