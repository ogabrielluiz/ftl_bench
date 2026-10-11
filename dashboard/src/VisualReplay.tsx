import { useEffect, useState } from "react";
import type { VisualFrame, VisualInput, VisualReplayState } from "./types";

function shown(value: number | string | null | undefined) {
  return value === null || value === undefined ? "unrecorded" : String(value);
}

function point(x?: number, y?: number) {
  return typeof x === "number" && Number.isFinite(x) && typeof y === "number" && Number.isFinite(y);
}

function inputLabel(input: VisualInput) {
  if (input.type === "key") return `Key ${[...(input.modifiers || []), input.key || "unknown"].join(" + ")}`;
  const at = point(input.x, input.y) ? ` (${input.x}, ${input.y})` : "";
  const to = input.type === "drag" && point(input.to_x, input.to_y) ? ` → (${input.to_x}, ${input.to_y})` : "";
  return `${input.type}${input.button ? ` ${input.button}` : ""}${at}${to}`;
}

export function VisualFrameView({ frame, inputs, phase, markers, modelInput = true }: {
  frame?: VisualFrame; inputs: VisualInput[]; phase: "before" | "after"; markers: boolean; modelInput?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [frame?.url]);
  const dimensions = frame && Number.isFinite(frame.width) && Number.isFinite(frame.height)
    && (frame.width || 0) > 0 && (frame.height || 0) > 0;
  if (!frame) return <div className="visual-missing">No {phase} image recorded.</div>;
  return <figure className="visual-frame" style={dimensions ? { maxWidth: frame.width } : undefined}>
    <div className="visual-canvas">
      {failed ? <div className="visual-missing">Recorded image unavailable or changed.</div> : <>
        <img src={frame.url} alt={phase === "before" ? modelInput ? "Exact screenshot supplied to the model" : "Game screenshot before the recorded inputs" : "Game screenshot after the recorded inputs"}
          width={frame.width} height={frame.height} onError={() => setFailed(true)} />
        {markers && dimensions && phase === "before" ? <svg className="input-overlay" viewBox={`0 0 ${frame.width} ${frame.height}`}
          aria-label="Requested input locations in original screenshot coordinates">
          {inputs.map((input, index) => point(input.x, input.y) ? <g key={index}
            className={input.delivery === "rejected" ? "input-marker rejected" : "input-marker"}>
            <title>{`${index + 1}. ${inputLabel(input)} · ${input.delivery || "delivery unrecorded"}`}</title>
            {input.type === "drag" && point(input.to_x, input.to_y) ? <>
              <line x1={input.x} y1={input.y} x2={input.to_x} y2={input.to_y} />
              <circle cx={input.to_x} cy={input.to_y} r="7" />
            </> : null}
            <circle cx={input.x} cy={input.y} r="14" />
            <text x={input.x} y={(input.y || 0) + 5} textAnchor="middle">{index + 1}</text>
          </g> : null)}
        </svg> : null}
      </>}
    </div>
    <figcaption>{phase === "before" ? modelInput ? "Model view" : "Before inputs" : "After inputs"} · Frame {shown(frame.frame_id)} · {shown(frame.width)} × {shown(frame.height)}
      <a href={frame.url} target="_blank" rel="noreferrer">Open original</a></figcaption>
    {markers && phase === "before" && !dimensions ? <p className="muted">Markers unavailable: original image dimensions were not recorded.</p> : null}
    <details className="muted"><summary>Image identity</summary><p>{frame.path || "Path unrecorded"}</p><p>SHA-256 {frame.sha256 || "unrecorded"}</p></details>
  </figure>;
}

export function VisualDecision({ replay, phase, markers }: {
  replay: VisualReplayState; phase: "before" | "after"; markers: boolean;
}) {
  const item = replay.item;
  if (!item) return <p className="muted">No visual decisions recorded.</p>;
  const visual = item.visual;
  const interference = item.record_kind === "external_interference";
  const noDispatch = interference && visual.external_input_guard?.packet_dispatched === false;
  const inputs = noDispatch ? [] : visual.inputs || [];
  const advance = visual.advance;
  const fixedSeconds = advance?.visual_clock_version === 2
    && advance.fixed_step_numerator === 1 && advance.fixed_step_denominator === 60
    && typeof advance.actual_frames === "number" && advance.actual_frames >= 0
    && Number.isInteger(advance.actual_frames)
    && typeof advance.simulated_seconds === "number" && Number.isFinite(advance.simulated_seconds)
    && Math.abs(advance.simulated_seconds - advance.actual_frames / 60) < 1e-9;
  return <>
    <VisualFrameView frame={visual[phase]} phase={phase} inputs={inputs} markers={markers && !noDispatch} modelInput={!!item.model} />
    <div className="visual-facts">
      <span>{item.model ? "Decision" : "Capture"} #{item.i}</span>
      <span>{visual.observation_mode || "Observation mode unrecorded"}</span>
      <span>Advance: {shown(visual.advance?.requested_frames)} requested / {shown(visual.advance?.actual_frames)} simulated frames</span>
      <span>Game time: {fixedSeconds ? `${advance!.simulated_seconds!.toFixed(3)}s (60 updates/s)`
        : advance?.visual_clock_version === 1 ? "variable per update (clock v1)" : "unrecorded"}</span>
      <span>Model response: {item.model?.latency_seconds === undefined ? "unrecorded" : `${item.model.latency_seconds.toFixed(2)}s`}</span>
    </div>
    {item.ack_timeout ? <p className="api-error">Input acknowledgement unavailable. Some inputs may have taken effect.</p> : null}
    {item.record_kind === "model_error" ? <p className="api-error">The model request did not produce a usable decision. No inputs were dispatched.</p> : null}
    {item.record_kind === "model_cancelled" ? <p className="muted">A stop was requested while the model was responding. Its response and usage were saved; no proposed inputs were dispatched.</p> : null}
    {interference ? <p className="api-error">{noDispatch
      ? "Outside input stopped the run before dispatch. No planned inputs were sent."
      : visual.external_input_guard?.packet_dispatched === true
        ? "Outside input stopped the run after an action packet was sent. Input delivery is unverified."
        : "Outside input stopped the run. Dispatch status is unrecorded."}</p> : null}
    {item.thought ? <p className="visual-thought">{item.thought}</p> : null}
    {interference && !!visual.planned_inputs?.length ? <div className="visual-outcome">
      <strong>{noDispatch ? "Planned inputs · not sent" : "Planned inputs · delivery unverified"}</strong>
      <ol>{visual.planned_inputs.map((input, index) => <li key={index}>{inputLabel(input)}</li>)}</ol>
    </div> : null}
    <ol className="visual-inputs">{inputs.map((input, index) => <li key={index}>
      <span>{inputLabel(input)}</span><strong className={input.delivery === "rejected" ? "rejected" : ""}>{input.delivery || "delivery unrecorded"}</strong>
      {input.reason ? <small>{input.reason}</small> : null}
    </li>)}</ol>
    {!inputs.length && !interference ? <p className="muted">No mouse or keyboard inputs in this decision.</p> : null}
    <p className="muted">Delivery describes the input event. It does not establish that the intended game action succeeded.</p>
    <div className="visual-outcome"><strong>Evaluator assessment · {visual.outcome?.status || "unrecorded"}</strong>
      <p>{visual.outcome?.summary || "No game outcome assessment recorded for this decision."}</p></div>
    {visual.visible_summary !== undefined ? <details className="muted"><summary>Text summary supplied to the model</summary>
      <pre className="visual-summary">{typeof visual.visible_summary === "string" ? visual.visible_summary : JSON.stringify(visual.visible_summary, null, 2)}</pre>
      {visual.visible_summary_provenance ? <>
        <p>Read from this screenshot's pixels. Unrecognized values are omitted.</p>
        <p>Image SHA-256 {visual.visible_summary_provenance.image_sha256 || "unrecorded"}</p>
        <ul>{Object.entries(visual.visible_summary_provenance.fields || {}).map(([name, field]) => <li key={name}>
          {name.replace(/_/g, " ")}: {field.status === "recognized" ? field.value : "omitted"}
          {field.reason ? ` (${field.reason.replace(/_/g, " ")})` : ""}
        </li>)}</ul>
      </> : null}
    </details> : null}
    {visual.external_input_guard ? <details className="muted"><summary>Outside-input evidence</summary>
      <p>Input generation: {shown(visual.external_input_guard.expected_generation)} → {shown(visual.external_input_guard.observed_generation)}.
        Action sequence: {shown(visual.external_input_guard.action_seq)}.</p>
    </details> : null}
  </>;
}

export default function VisualReplay({ selection, count }: { selection: string; count: number }) {
  const [index, setIndex] = useState<number | null>(null);
  const [phase, setPhase] = useState<"before" | "after">("before");
  const [markers, setMarkers] = useState(true);
  const [replay, setReplay] = useState<VisualReplayState | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setReplay(null);
    setError(null);
    const params = new URLSearchParams({ sel: selection });
    if (index !== null) params.set("index", String(index));
    fetch(`/api/replay?${params}`, { cache: "no-store", signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(`Replay unavailable (${response.status})`); return response.json(); })
      .then((value: VisualReplayState) => { if (!controller.signal.aborted) setReplay(value); })
      .catch((err: Error) => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [selection, index, count]);
  const position = replay?.index ?? index ?? count - 1;
  return <section className="visual-replay" aria-label="Visual trajectory replay">
    <div className="visual-title"><div><h2>{replay?.item?.model ? "What the model saw" : "Recorded game view"}</h2><p>Replay the recorded game window and inputs.</p></div>
      <span>{position + 1} / {replay?.total ?? count} {replay?.item?.model ? "decisions" : "captures"}</span></div>
    <div className="replay-controls">
      <button type="button" disabled={position <= 0} onClick={() => setIndex(position - 1)}>Previous</button>
      <input aria-label="Replay decision" type="range" min={0} max={Math.max(0, count - 1)} value={Math.max(0, position)} onChange={event => setIndex(Number(event.target.value))} />
      <button type="button" disabled={position >= count - 1} onClick={() => setIndex(position + 1)}>Next</button>
      <button type="button" className={index === null ? "active" : ""} onClick={() => setIndex(null)}>Latest</button>
    </div>
    <div className="replay-controls phase-controls">
      <button type="button" aria-pressed={phase === "before"} onClick={() => setPhase("before")}>Before · {replay?.item?.model ? "model view" : "game view"}</button>
      <button type="button" aria-pressed={phase === "after"} onClick={() => setPhase("after")}>After · result</button>
      <label><input type="checkbox" checked={markers} onChange={event => setMarkers(event.target.checked)} /> Show requested inputs</label>
    </div>
    {error ? <p className="api-error">{error}</p> : replay ? <VisualDecision replay={replay} phase={phase} markers={markers} /> : <p className="muted">Loading decision…</p>}
  </section>;
}
