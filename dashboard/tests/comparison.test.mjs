import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { after, test } from "node:test";
import { build } from "esbuild";

const directory = await mkdtemp(join(tmpdir(), "ftl-comparison-tests-"));
const target = join(directory, "comparison.cjs");
await build({ stdin: { contents: `export { ComparisonView } from "./src/ComparisonOverview";
  export { createElement } from "react"; export { renderToStaticMarkup } from "react-dom/server";`,
  resolveDir: process.cwd(), loader: "tsx" }, outfile: target, bundle: true, platform: "node", format: "cjs", jsx: "automatic" });
const { ComparisonView, createElement, renderToStaticMarkup } = createRequire(import.meta.url)(target);
after(async () => rm(directory, { recursive: true, force: true }));
const base = { key: "matrix", name: "matrix", protocol_sha256: "hash", partial: true,
  qualified_scoped_comparison: false, counts: { total: 36, planned: 34, running: 1, finished: 1, unknown: 0 },
  requested_models: ["gpt-6.1-sol", "gpt-6-luna"], conditions: [], trials: [], limitations: [], issues: [], source: "Saved report" };
const render = value => renderToStaticMarkup(createElement(ComparisonView, { value, onSelect: () => {} }));

test("portable admission identities remain explicitly stored metadata", () => {
  const html = render({ ...base, contract: "ftl-visual-challenge-matrix-v2", stored_admission: {
    source: "Stored protocol admission metadata only; the dashboard does not rerun admission or a live runtime audit.",
    spec: { path: "admission.json", sha256: "spechash" }, candidate: { sha256: "candidatehash" },
    reviewer: { id: "explicit-reviewer", independent_of_producer: true }, build_origin: { sha256: "originhash" },
    review: { sha256: "reviewhash" }, runtime: { dll_sha256: "dllhash" },
    runtime_files: { "Hyperspace.dll": "dllhash" }, evidence_files: { "admission.json": "spechash" } } });
  assert.match(html, /Stored portable admission provenance/);
  assert.match(html, /does not rerun admission or a live runtime audit/);
  for (const identity of ["spechash", "candidatehash", "originhash", "reviewhash", "explicit-reviewer", "dllhash"])
    assert.ok(html.includes(identity));
  assert.match(html, /Matched comparison not yet qualified/);
});

test("partial experiments show progress and explicitly avoid ranking claims", () => {
  const html = render(base);
  assert.match(html, /Partial experiment/);
  assert.match(html, /Matched comparison not yet qualified/);
  assert.match(html, /not a model ranking or full-game scores/);
  assert.match(html, /<b>36<\/b> planned total/);
  assert.match(html, /<b>1<\/b> running/);
  assert.match(html, /Requested models: gpt-6.1-sol, gpt-6-luna/);
});

test("budgets and protocol errors remain separately named outcomes", () => {
  const html = render({ ...base, conditions: [{ model: "sol", mode: "image", scenario: "combat", attempts: 3,
    eligible_trials: 2, excluded_trials: 1, matched_pair_trials: 0,
    outcomes: { task_success: 1, budget_exhausted: 1, protocol_failure: 1 },
    model_calls_all_attempts: { usage: { complete_totals: { input_tokens: null, output_tokens: 50 } }, latency_seconds: { total: null } } }] });
  assert.match(html, /task success: 1/);
  assert.match(html, /budget exhausted: 1/);
  assert.match(html, /protocol failure: 1/);
  assert.match(html, /unavailable \/ 50/);
  assert.match(html, /<td>unavailable<\/td>/);
});

test("exact trial link, setup classification and unreported backend identity are explicit", () => {
  const html = render({ ...base, trials: [{ id: "one", model: "sol", mode: "hybrid", challenge: "combat",
    repetition: 2, status: "finished", kind: "setup_check", exclusions: [], decisions: 0,
    model_calls: { response_model_identity: { reported_models: [] } },
    selection: "matrix/exact/trajectory", replay_url: "/?sel=matrix%2Fexact%2Ftrajectory" }] });
  assert.match(html, /Setup check/);
  assert.match(html, /Repeat 2/);
  assert.match(html, /Resolved model: not reported/);
  assert.match(html, /href="\/\?sel=matrix%2Fexact%2Ftrajectory"/);
});

test("complete qualified scope still does not become a full-game ranking", () => {
  const html = render({ ...base, partial: false, qualified_scoped_comparison: true });
  assert.match(html, /Matched challenge comparison qualified/);
  assert.match(html, /not a model ranking or full-game scores/);
  assert.doesNotMatch(html, /Partial experiment/);
});

const full = { ...base, experiment_kind: "full_game", counts: { total: 5, planned: 1, running: 1, finished: 3, unknown: 0 },
  fullgame_summary: { fullgame_attempts: 2, verified_fullgame_completions: 1, victories: 1, defeats: 0, incomplete_fullgames: 1 },
  trials: [
    { id: "pilot", model: "sol", mode: "image", scope: "sector_pilot", status: "finished", kind: "model_trial", outcome_category: "pilot_defeat", native_outcome: "defeat", verified_fullgame_complete: false, exclusions: [] },
    { id: "win", model: "sol", mode: "image", scope: "full_game", status: "finished", kind: "model_trial", native_outcome: "victory", verified_fullgame_complete: true, exclusions: [], selection: "full/win/trajectory", replay_url: "/?sel=full%2Fwin%2Ftrajectory",
      cleanup_evidence: [{ path: "saved.json", checked_at: "2026-10-11T01:00:00Z", sha256: "exacthash" }] },
    { id: "budget", model: "sol", mode: "hybrid", scope: "full_game", status: "finished", kind: "model_trial", reason: "decision_budget", verified_fullgame_complete: false, exclusions: [] },
    { id: "running", model: "luna", mode: "image", scope: "full_game", status: "running", kind: "model_trial", exclusions: [] },
    { id: "planned", model: "luna", mode: "hybrid", scope: "full_game", status: "planned", kind: "model_trial", exclusions: [] }
  ] };

test("all five fullgame conditions show pilot, native ending, budget and pending distinctions", () => {
  const html = render(full);
  assert.match(html, /Saved pilot and full-game conditions/);
  assert.match(html, /Sector-one pilot/);
  assert.match(html, /excluded from full-game totals/);
  assert.match(html, /Verified native victory/);
  assert.match(html, /decision budget/);
  assert.match(html, /<b>1<\/b> running/);
  assert.match(html, /No verified native ending saved/);
  assert.match(html, /Verified native endings: 1/);
  assert.doesNotMatch(html, /Matched challenge comparison qualified/);
  assert.doesNotMatch(html, /Repeat undefined|undefined/);
});

test("fullgame saved evidence and exact replay are retained with unavailable usage", () => {
  const html = render(full);
  assert.match(html, /href="\/\?sel=full%2Fwin%2Ftrajectory"/);
  assert.match(html, /Saved cleanup checks \(1\)/);
  assert.match(html, /Point-in-time cleanup passed/);
  assert.match(html, /exacthash/);
  assert.match(html, /unavailable \/ unavailable/);
});

test("missing fullgame totals stay unavailable and failed audit remains incomplete", () => {
  const html = render({ ...full, fullgame_summary: null, trials: [{ ...full.trials[1], integrity_passed: false, verified_fullgame_complete: false }] });
  assert.match(html, /native-ending totals are unavailable or updating/);
  assert.match(html, /Audit failed · incomplete/);
  assert.doesNotMatch(html, /Verified native victory|Verified native endings: 0/);
});
