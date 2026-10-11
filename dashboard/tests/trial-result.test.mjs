import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { after, test } from "node:test";
import { build } from "esbuild";
const directory = await mkdtemp(join(tmpdir(), "ftl-result-tests-"));
const target = join(directory, "result.cjs");
await build({ stdin: { contents: `export { default as TrialResult } from "./src/TrialResult";
  export { VisualDecision } from "./src/VisualReplay";
  export { createElement } from "react"; export { renderToStaticMarkup } from "react-dom/server";`,
  resolveDir: process.cwd(), loader: "tsx" }, outfile: target, bundle: true, platform: "node", format: "cjs", jsx: "automatic" });
const { TrialResult, VisualDecision, createElement, renderToStaticMarkup } = createRequire(import.meta.url)(target);
after(async () => rm(directory, { recursive: true, force: true }));
const render = (Component, props) => renderToStaticMarkup(createElement(Component, props));
test("scoring review remains separate from original budget result", () => {
  const html = render(TrialResult, {trial: {outcome: "budget_exhausted", setup_checks: {}, outcome_checks: {},
    adjudication: {summary: "Written task was satisfied; evaluator added healing requirement.", recorded_outcome_kept: true,
      model_observation_error: true}}});
  assert.match(html, /Trial limit reached/);
  assert.match(html, /Scoring review/);
  assert.match(html, /original recorded outcome is preserved/);
  assert.doesNotMatch(html, /<h2>Challenge completed/);
});
test("manual recovery distinguishes incomplete raw lifecycle from successful cleanup", () => {
  const html = render(TrialResult, {trial: {setup_checks: {}, outcome_checks: {}, operator_recovery: {
    recovered_at: "2026-10-11T01:16:01Z", original_save_count: 7, initiator: "assistant_operator"}}});
  assert.match(html, /Trial interrupted; recovery verified/);
  assert.match(html, /manual recovery verified for 7 saves/);
  assert.match(html, /raw lifecycle remains incomplete/);
  assert.doesNotMatch(html, /<h2>In progress/);
});
test("cancelled model response is inspectable and never described as delivered input", () => {
  const html = render(VisualDecision, {replay: {selected:"test", index:0, total:1, item: {i:0,
    record_kind:"model_cancelled", model:{latency_seconds:2}, visual:{inputs:[]}}}, phase:"before", markers:false});
  assert.match(html, /response and usage were saved/);
  assert.match(html, /no proposed inputs were dispatched/);
});
