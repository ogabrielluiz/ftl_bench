import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { after, test } from "node:test";
import { build } from "esbuild";
const directory = await mkdtemp(join(tmpdir(), "ftl-cli-ui-tests-"));
const target = join(directory, "request.cjs");
await build({ stdin: { contents: `export { default as Panel } from "./src/ModelRequestDetails";
  export { createElement } from "react"; export { renderToStaticMarkup } from "react-dom/server";`,
  resolveDir: process.cwd(), loader: "tsx" }, outfile: target, bundle: true, platform: "node", format: "cjs", jsx: "automatic" });
const { Panel, createElement, renderToStaticMarkup } = createRequire(import.meta.url)(target);
after(async () => rm(directory, { recursive: true, force: true }));
const render = model => renderToStaticMarkup(createElement(Panel, { model }));
test("failed raw completion usage stays diagnostic and does not fill reported usage", () => {
  const model = { cli_exit_code: 0, cli_failure: { kind: "unsupported_event", event_type: "error", event_index: 2,
    stdout: { text: '{"type":"turn.completed","usage":{"input_tokens":99,"output_tokens":3}}\r\n',
      bytes: 100, retained_bytes: 90, sha256: "original", retained_sha256: "retained", redacted: true, truncated: true },
    stderr: { text: "<script>unsafe</script>", retained_bytes: 23 } } };
  const before = JSON.stringify(model);
  const html = render(model);
  assert.match(html, /Reported call usage: input unavailable/);
  assert.match(html, /Raw completion usage · diagnostic only/);
  assert.match(html, /does not establish an accepted call/);
  assert.match(html, /CLI exit code: 0/);
  assert.match(html, /truncated/);
  assert.match(html, /Original SHA256: original/);
  assert.match(html, /&lt;script&gt;unsafe/);
  assert.doesNotMatch(html, /<details[^>]*open/);
  assert.equal(JSON.stringify(model), before);
});
test("partial invalid stdout and absent streams remain inspectable without fake usage", () => {
  const html = render({cli_failure: {kind: "timeout", partial: true, stdout: {text: '{"type":', utf8_valid: false, available: true}, stderr: {available: false}}});
  assert.match(html, /partial output/);
  assert.match(html, /invalid original UTF-8/);
  assert.match(html, /Retained stderr · unavailable/);
  assert.doesNotMatch(html, /Raw completion usage/);
});
test("legacy successful reported usage remains visible", () => {
  const html = render({model: "sol", usage: {input_tokens: 0, output_tokens: 7}, request_id: "request"});
  assert.match(html, /Reported call usage: input 0 · output 7/);
  assert.doesNotMatch(html, /Rejected CLI|Retained stdout/);
});
test("accepted reconnect notices expose completed-turn scope and unknown aborted sampling", () => {
  const html = render({ usage: {input_tokens: 10, output_tokens: 2}, cli_exit_code: 0,
    cli_event_policy: "ftl-codex-cli-reconnect-v1", cli_recovery: {kind: "recovered_reconnect",
      aborted_sampling_usage: "unavailable", notices: [{event_index: 1, attempt: 1, max_attempts: 5, message: "Reconnecting... 1/5"}],
      stdout: {text: '{"type":"turn.completed","usage":{"input_tokens":10}}', retained_bytes: 60} } });
  assert.match(html, /CLI reconnect recovery/);
  assert.match(html, /reconnect 1\/5: Reconnecting/);
  assert.match(html, /completed turn only/);
  assert.match(html, /Aborted internal sampling usage: unavailable/);
  assert.match(html, /Reported call usage: input 10 · output 2/);
  assert.doesNotMatch(html, /Rejected CLI call/);
});
