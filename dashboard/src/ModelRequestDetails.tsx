import type { ModelTrace, CliDiagnosticStream } from "./types";

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

export default function ModelRequestDetails({ model, latest = false }: { model: ModelTrace; latest?: boolean }) {
  const failure = model.cli_failure;
  const recovery = model.cli_recovery;
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
