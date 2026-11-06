import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { after, test } from "node:test";
import { build } from "esbuild";

const directory = await mkdtemp(join(tmpdir(), "ftl-replay-tests-"));
const target = join(directory, "replay.cjs");
await build({ stdin: { contents: `export { VisualFrameView, VisualDecision } from "./src/VisualReplay";
  export { TimelineItem } from "./src/App";
  export { createElement } from "react"; export { renderToStaticMarkup } from "react-dom/server";`,
  resolveDir: process.cwd(), loader: "tsx" }, outfile: target, bundle: true, platform: "node", format: "cjs", jsx: "automatic" });
const { VisualFrameView, VisualDecision, TimelineItem, createElement, renderToStaticMarkup } = createRequire(import.meta.url)(target);
after(async () => rm(directory, { recursive: true, force: true }));

const frame = { url: "/api/artifact?sel=test&record=1&phase=before", width: 1280, height: 720, frame_id: "frame-1" };
const inputs = [{ type: "click", x: 1024, y: 576, delivery: "delivered" },
  { type: "drag", x: 10, y: 20, to_x: 100, to_y: 200, delivery: "rejected" }];
const render = (Component, props) => renderToStaticMarkup(createElement(Component, props));

test("input markers keep original screenshot coordinates at every display size", () => {
  const html = render(VisualFrameView, { frame, inputs, phase: "before", markers: true });
  assert.match(html, /viewBox="0 0 1280 720"/);
  assert.match(html, /cx="1024" cy="576"/);
  assert.match(html, /x1="10" y1="20" x2="100" y2="200"/);
  assert.match(html, /input-marker rejected/);
  assert.match(html, /Exact screenshot supplied to the model/);
});

test("result screenshots and missing dimensions do not pretend inputs were aimed on that image", () => {
  assert.doesNotMatch(render(VisualFrameView, { frame, inputs, phase: "after", markers: true }), /<svg/);
  const html = render(VisualFrameView, { frame: { ...frame, width: undefined }, inputs, phase: "before", markers: true });
  assert.doesNotMatch(html, /<svg/);
  assert.match(html, /dimensions were not recorded/);
});

test("delivery, evaluator uncertainty, simulated frames and model latency remain distinct", () => {
  const replay = { selected: "test", index: 0, total: 1, item: { i: 0,
    model: { latency_seconds: 2.5 }, visual: { observation_mode: "hybrid", before: frame, inputs,
      advance: { requested_frames: 60, actual_frames: 12 }, outcome: { status: "unknown", summary: "Jump unverified." } } } };
  const html = render(VisualDecision, { replay, phase: "before", markers: false });
  assert.match(html, /60 requested \/ 12 simulated frames/);
  assert.match(html, /Model response: 2.50s/);
  assert.match(html, /Evaluator assessment · unknown/);
  assert.match(html, /Jump unverified/);
  assert.match(html, /does not establish that the intended game action succeeded/);
  assert.doesNotMatch(html, /<svg/);
});

test("selected replay shows typed API stages alongside the original screenshot", () => {
  const replay = { item: { i: 0, record_kind: "model_error", visual: { before: frame }, model: {
    api_audit_version: 1, decision_complete: false, api_calls: [
      { stage: "control", status: "completed", confidence: 0.6, choice: "click", usage: { input_tokens: 18 } },
      { stage: "pixel", status: "error", http_status: 429, artifact: "api/decision-1/02-pixel" },
    ],
  } } };
  const html = render(VisualDecision, { replay, phase: "before", markers: true });
  assert.match(html, /Exact screenshot supplied to the model/);
  assert.match(html, /Decision incomplete · 2 HTTP stages recorded/);
  assert.match(html, /Choice click · confidence 60.0%/);
  assert.match(html, /HTTP 429/);
  assert.match(html, /api\/decision-1\/02-pixel/);
  assert.match(html, /No inputs were dispatched/);
});

test("replay distinguishes late API decisions from interrupted API chains", () => {
  const visual = { before: frame, inputs: [] };
  const model = { api_audit_version: 1, api_calls: [], decision_complete: true };
  const cancelled = (trace, decision) => render(VisualDecision, { phase: "before", markers: true,
    replay: { item: { i: 0, record_kind: "model_cancelled", model: decision, visual: trace } } });
  const late = cancelled({ ...visual, cancellation_reason: "wall_clock_budget" }, model);
  assert.match(late, /The wall-clock budget elapsed before dispatch/);
  assert.match(late, /The completed decision and any reported usage were saved/);
  assert.doesNotMatch(late, /A stop was requested/);

  const interrupted = cancelled(visual, { ...model, decision_complete: false });
  assert.match(interrupted, /The typed decision was interrupted before completion/);
  assert.match(interrupted, /Recorded HTTP stages and available usage were retained/);
  assert.match(interrupted, /No proposed inputs were dispatched/);
  assert.doesNotMatch(interrupted, /The completed decision|Its response and usage were saved/);
});

test("unrecorded timing is displayed as unrecorded, never zero or elapsed wall time", () => {
  const replay = { selected: "test", index: 0, total: 1, item: { i: 0, visual: { before: frame } } };
  const html = render(VisualDecision, { replay, phase: "before", markers: false });
  assert.match(html, /unrecorded requested \/ unrecorded simulated frames/);
  assert.match(html, /Model response: unrecorded/);
  assert.match(html, /Game screenshot before the recorded inputs/);
  assert.doesNotMatch(html, /Exact screenshot supplied to the model/);
});

test("fixed game time requires the v2 contract and matching frame accounting", () => {
  const advance = { actual_frames: 120, requested_frames: 120, visual_clock_version: 2,
    fixed_step_numerator: 1, fixed_step_denominator: 60, simulated_seconds: 2 };
  const view = value => render(VisualDecision, { replay: { item: { i: 0,
    visual: { before: frame, advance: value } } }, phase: "before", markers: false });
  assert.match(view(advance), /Game time: 2.000s \(60 updates\/s\)/);
  assert.match(view({ ...advance, simulated_seconds: 3 }), /Game time: unrecorded/);
  assert.match(view({ ...advance, fixed_step_denominator: 30 }), /Game time: unrecorded/);
  assert.match(view({ actual_frames: 120, requested_frames: 120 }), /Game time: unrecorded/);
  assert.match(view({ ...advance, visual_clock_version: 1 }), /Game time: variable per update/);
});

test("a refused decision displays its plan as not sent and never draws planned click markers", () => {
  const item = { i: 125, record_kind: "external_interference", actions: [], state: {}, model: {},
    visual: { before: frame, inputs, planned_inputs: inputs, external_input_guard: {
      packet_dispatched: false, expected_generation: "0", observed_generation: "1", action_seq: 124 } } };
  const html = render(VisualDecision, { replay: { item }, phase: "before", markers: true });
  assert.match(html, /No planned inputs were sent/);
  assert.match(html, /Planned inputs · not sent/);
  assert.match(html, /click \(1024, 576\)/);
  assert.match(html, /Input generation: 0 → 1/);
  assert.doesNotMatch(html, /<svg|input-marker|>delivered</);
  const timeline = render(TimelineItem, { item });
  assert.match(timeline, /Outside input stopped the run/);
  assert.match(timeline, /No input sent/);
  assert.doesNotMatch(timeline, />advance</);
});

test("interference after packet dispatch preserves unknown delivery instead of claiming no input", () => {
  const item = { i: 125, record_kind: "external_interference", actions: [], state: {},
    visual: { before: frame, planned_inputs: inputs,
      inputs: [{ ...inputs[0], delivery: "unknown" }], external_input_guard: { packet_dispatched: true } } };
  const html = render(VisualDecision, { replay: { item }, phase: "before", markers: false });
  assert.match(html, /after an action packet was sent. Input delivery is unverified/);
  assert.match(html, /Planned inputs · delivery unverified/);
  assert.match(html, />unknown</);
  assert.doesNotMatch(html, /No planned inputs were sent|>delivered</);
  const timeline = render(TimelineItem, { item });
  assert.match(timeline, /Delivery unverified/);
  assert.doesNotMatch(timeline, />advance<|No input sent/);
});
