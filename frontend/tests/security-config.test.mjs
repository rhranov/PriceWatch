import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url)));
const config = await readFile(new URL("../next.config.ts", import.meta.url), "utf8");
const middleware = await readFile(new URL("../middleware.ts", import.meta.url), "utf8");
const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");

test("development and production servers bind to loopback", () => {
  assert.match(packageJson.scripts.dev, /--hostname 127\.0\.0\.1/);
  assert.match(packageJson.scripts.start, /--hostname 127\.0\.0\.1/);
});

test("anti-framing and content security headers are configured", () => {
  assert.match(config, /X-Frame-Options/);
  assert.match(config, /nosniff/);
  assert.match(middleware, /frame-ancestors 'none'/);
});

test("CSP uses per-response nonces and limits eval to development", () => {
  assert.match(middleware, /crypto\.randomUUID\(\)/);
  assert.match(middleware, /'nonce-\$\{nonce\}'/);
  assert.match(middleware, /'strict-dynamic'/);
  assert.match(middleware, /NODE_ENV === "development"/);
  assert.match(middleware, /isDevelopment \? " 'unsafe-eval'" : ""/);
  assert.doesNotMatch(config, /Content-Security-Policy/);
  assert.match(layout, /dynamic = "force-dynamic"/);
  assert.match(middleware, /"style-src 'self' 'unsafe-inline'"/);
  assert.match(middleware, /ws:\/\/localhost:8000/);
});

test("credential proxy rejects missing keys and cross-origin mutations", () => {
  assert.match(middleware, /apiKey\.length < 32/);
  assert.match(middleware, /origin !== request\.nextUrl\.origin/);
  assert.match(middleware, /pathname\.startsWith\("\/api\/"\)/);
});
