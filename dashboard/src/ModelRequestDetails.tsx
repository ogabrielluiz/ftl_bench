import type { ModelTrace, CliDiagnosticStream, TypedVisualApiCall } from "./types";

function Stream({ name, stream }: { name: string; stream?: CliDiagnosticStream }) {
  if (!stream) return null;
  return <details><summary>Retained {name} · {stream.available === false ? "unavailable" : `${stream.retained_bytes ?? "unknown"} bytes`}
    {stream.truncated ? " · truncated" : ""}{stream.redacted ? " · redacted" : ""}</summary>
    <p>Original bytes: {stream.bytes ?? "unknown"} · retained bytes: {stream.retained_bytes ?? "unknown"}
      {stream.utf8_valid === false ? " · invalid original UTF-8" : ""}</p>
    <p>Original SHA256: {stream.sha256 || "unavailable"}<br />Retained redacted SHA256: {stream.retained_sha256 || "unavailable"}</p>
    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "24rem", overflow: "auto" }}>{stream.text || "No retained text"}</pre>
  </details>;
}

function RawUsage({ text }: { text?: string }) {
  const completions: unknown[] = [];
  for (const line of (text || "").split(/\r?\n/)) {
    try {
      const event = JSON.parse(line);
      if (event?.type === "turn.completed" && event.usage && typeof event.usage === "object") completions.push(event.usage);
    } catch { /* A bounded stream can end within an event. */ }
  }
  return completions.length ? <details><summary>Raw completion usage · diagnostic only</summary>
    <p>Parsed from retained stdout. This does not establish an accepted call or replace reported usage; truncated output may omit events.</p>
    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(completions, null, 2)}</pre>
  </details> : null;
}

function probability(value?: number) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1
    ? `${(value * 100).toFixed(1)}%` : "unavailable";
}

function TypedStage({ call }: { call: TypedVisualApiCall }) {
  const usage = call.usage;
  const choices = Array.isArray(call.top_choices) ? call.top_choices.slice(0, 5) : [];
  return <li>
    <strong>{call.stage || "Stage unavailable"} · {call.status === "invalid_response" ? "invalid response" : call.status}</strong>
    {typeof call.latency_seconds === "number" ? ` · ${call.latency_seconds.toFixed(2)}s` : null}
    <p>{call.provider || "Provider unavailable"} · {call.model || "response model unavailable"}
      {call.requested_model ? ` · Requested ${call.requested_model}` : null}
      {call.http_status !== undefined ? ` · HTTP ${call.http_status}` : null}
      {call.attempts === 0 ? " · Preflight failed" : null}
      {call.request_id || call.client_request_id ? ` · Request ${call.request_id || call.client_request_id}` : null}</p>
    <p>Input {usage?.input_tokens ?? "unavailable"} · output {usage?.output_tokens ?? "unavailable"}
      {" · "}cached {usage?.cached_input_tokens ?? usage?.input_tokens_details?.cached_tokens ?? "unavailable"}
      {" · "}reasoning {usage?.reasoning_tokens ?? usage?.output_tokens_details?.reasoning_tokens ?? "unavailable"} tokens</p>
    {call.choice !== undefined ? <p>Choice {call.choice} · confidence {probability(call.confidence)}
      {" · "}selected probability {probability(call.selected_probability)}
      {call.option_count !== undefined ? ` · ${call.option_count} options` : null}</p> : null}
    {choices.length ? <p>Top choices {choices.map(choice =>
      `${choice.value} ${probability(choice.probability)}`).join(", ")}</p> : null}
    {call.artifact ? <p>Saved HTTP audit <code>{call.artifact}</code></p> : null}
  </li>;
}

export default function ModelRequestDetails({ model, latest = false }: { model: ModelTrace; latest?: boolean }) {
  const failure = model.cli_failure;
  const recovery = model.cli_recovery;
  const stages = model.api_audit_version === 1 && Array.isArray(model.api_calls)
    ? model.api_calls.filter(call => call && typeof call === "object") : null;
  if (stages) {
    const displayLimit = 32;
    return <details className="muted">
      <summary>Typed visual decision · {model.model || model.provider || "identity unavailable"}
        {model.latency_seconds !== undefined ? ` · ${model.latency_seconds.toFixed(2)}s` : ""}</summary>
      <p>{model.decision_complete === true ? "Decision completed" : "Decision incomplete"} · {stages.length} HTTP stages recorded</p>
      <p>Total reported usage across all stages · input {model.usage?.input_tokens ?? "unavailable"}
        {" · "}output {model.usage?.output_tokens ?? "unavailable"} tokens</p>
      <ol aria-label="Typed API stages">{stages.slice(0, displayLimit).map((call, i) => <TypedStage call={call} key={i} />)}</ol>
      {stages.length > displayLimit ? <p>Showing the first {displayLimit} stages.</p> : null}
    </details>;
  }
  return <details className="muted">
    <summary>{latest ? "Latest model request" : "Model request"}: {model.model || model.provider || "identity unavailable"}
      {model.latency_seconds !== undefined ? ` · ${model.latency_seconds.toFixed(2)}s` : ""}</summary>
    <p>Reported call usage: input {model.usage?.input_tokens ?? "unavailable"} · output {model.usage?.output_tokens ?? "unavailable"}</p>
    <p>Request {model.request_id || model.client_request_id || "unavailable"}</p>
    {model.cli_exit_code !== undefined ? <p>CLI exit code: {model.cli_exit_code}</p> : null}
    {recovery ? <section><p>CLI reconnect recovery · {model.cli_event_policy || "policy unavailable"}</p>
      <p>Reported usage covers the completed turn only. Aborted internal sampling usage: {recovery.aborted_sampling_usage || "unavailable"}. No benchmark call retry is implied.</p>
      <ul>{(recovery.notices || model.reconnect_notices || []).map((notice, i) => <li key={i}>Event {notice.event_index} · reconnect {notice.attempt}/{notice.max_attempts}: {notice.message}</li>)}</ul>
      <RawUsage text={recovery.stdout?.text} />
      <Stream name="stdout" stream={recovery.stdout} /><Stream name="stderr" stream={recovery.stderr} />
    </section> : null}
    {failure ? <section><p>Rejected CLI call: {failure.kind || "reason unavailable"}{failure.partial ? " · partial output" : ""}. Diagnostic evidence does not make this call valid.</p>
      {failure.error ? <p>{failure.error}</p> : null}
      {failure.event_type ? <p>Event: {failure.event_type}{failure.event_index !== undefined ? ` · index ${failure.event_index}` : ""}{failure.item_type ? ` · item ${failure.item_type}` : ""}</p> : null}
      <RawUsage text={failure.stdout?.text} />
      <Stream name="stdout" stream={failure.stdout} /><Stream name="stderr" stream={failure.stderr} />
    </section> : null}
  </details>;
}
