import { useEffect, useState } from "react";

type Calls = {
  usage?: { complete_totals?: Record<string, number | null> };
  latency_seconds?: { total?: number | null };
  response_model_identity?: { reported_models?: string[]; status?: string };
};
type Counts = { total: number; planned: number; running: number; finished: number; unknown: number };
type Trial = { id: string; model: string; mode: string; challenge?: string; repetition?: number;
  status: string; kind: string; outcome_category?: string | null; reason?: string | null;
  eligible?: boolean | null; exclusions: string[]; decisions?: number | null; model_calls?: Calls | null;
  selection?: string | null; replay_url?: string | null;
  scope?: string; native_outcome?: string | null; integrity_passed?: boolean | null;
  verified_fullgame_complete?: boolean | null; metrics?: Record<string, number | null> | null;
  cleanup_evidence?: Array<{ path: string; sha256: string; checked_at: string }> };
type Condition = { scenario: string; model: string; mode: string; attempts: number; eligible_trials: number;
  excluded_trials: number; outcomes: Record<string, number>; model_calls_all_attempts?: Calls;
  matched_pair_trials: number; paired_task_success_rate?: number | null };
export type Comparison = { key: string; name: string; protocol_sha256: string; partial: boolean;
  contract?: string;
  stored_admission?: { source: string; spec: Record<string, unknown>; candidate: Record<string, unknown>;
    build_origin: Record<string, unknown>; review: Record<string, unknown>; reviewer: Record<string, unknown>;
    runtime: Record<string, unknown>; runtime_files: Record<string, unknown>; evidence_files: Record<string, unknown> } | null;
  experiment_kind?: "challenge" | "full_game";
  fullgame_summary?: { fullgame_attempts: number; verified_fullgame_completions: number;
    victories: number; defeats: number; incomplete_fullgames: number } | null;
  artifact_sha256?: Record<string, string | null>;
  counts: Counts; reported_trials: number; qualified_scoped_comparison: boolean;
  requested_models: string[]; budgets?: { decisions: number; wall_seconds: number; idle_decisions: number };
  conditions: Condition[]; trials: Trial[]; limitations: string[]; issues: string[]; source: string };
type Catalog = { comparisons: Array<Pick<Comparison, "key" | "name" | "counts" | "experiment_kind">> };
const number = (value: number | null | undefined) => value == null ? "unavailable" : value.toLocaleString();
const seconds = (value: number | null | undefined) => value == null ? "unavailable" : `${value.toFixed(1)}s`;
const words = (value: string) => value.replace(/[_-]/g, " ");
const kinds: Record<string, string> = { model_trial: "Model trial", scripted_probe: "Scripted probe", setup_check: "Setup check" };

function ReplayLink({ trial, onSelect }: { trial: Trial; onSelect: (selection: string) => void }) {
  return trial.selection && trial.replay_url ? <a href={trial.replay_url} onClick={event => {
    if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
      event.preventDefault(); onSelect(trial.selection!);
    }
  }}>Open exact replay</a> : <span className="muted">Replay not available</span>;
}

function fullgameOutcome(trial: Trial) {
  if (trial.scope === "sector_pilot") return trial.outcome_category ? `Pilot: ${words(trial.outcome_category.replace(/^pilot_/, ""))} (excluded from full-game totals)` : "No saved pilot result";
  if (trial.verified_fullgame_complete === true) return `Verified native ${trial.native_outcome}`;
  if (trial.integrity_passed === false) return "Audit failed · incomplete";
  if (trial.verified_fullgame_complete === false) return "Incomplete";
  return "No verified native ending saved";
}

export function ComparisonView({ value, onSelect }: { value: Comparison; onSelect: (selection: string) => void }) {
  const c = value.counts;
  const fullgame = value.experiment_kind === "full_game";
  const summary = value.fullgame_summary;
  return <div className="comparison-body">
    <p className="comparison-scope"><strong>{value.partial ? "Partial experiment" : "Recorded experiment"}</strong>
      {fullgame ? <> · Single-seed full-game attempts. Only verified native victory or defeat completes a full game.
        {" "}The pilot and budget stops are excluded from completed-game totals. This is not a model ranking.</> : <>
        {" · "}{value.qualified_scoped_comparison ? "Matched challenge comparison qualified" : "Matched comparison not yet qualified"}.
        {" "}Challenge results are not a model ranking or full-game scores.</>}</p>
    <div className="comparison-counts" aria-label="Experiment progress">
      <span><b>{c.total}</b> planned total</span><span><b>{c.planned}</b> waiting</span>
      <span><b>{c.running}</b> running</span><span><b>{c.finished}</b> finished</span>
      {c.unknown ? <span><b>{c.unknown}</b> status unavailable</span> : null}
    </div>
    <p className="muted">Requested models: {value.requested_models.join(", ")}. These names do not verify the backend’s resolved weights.</p>
    {value.budgets ? <p className="muted">Same trial limits: {value.budgets.decisions} decisions,
      {" "}{value.budgets.wall_seconds}s wall time, {value.budgets.idle_decisions} idle decisions.</p> : null}
    {value.issues.map(issue => <p className="api-error" key={issue}>{issue}</p>)}
    {fullgame ? <>
      {summary ? <p className="comparison-scope">Saved full-game attempts: {summary.fullgame_attempts} · Verified native endings: {summary.verified_fullgame_completions}
        {" "}({summary.victories} victories, {summary.defeats} defeats) · Incomplete attempts: {summary.incomplete_fullgames}.</p>
        : <p className="muted">Saved native-ending totals are unavailable or updating.</p>}
      <div className="comparison-table-wrap"><table className="comparison-table">
        <caption>Saved pilot and full-game conditions</caption>
        <thead><tr><th>Condition</th><th>Execution status</th><th>Saved outcome</th><th>Model response time</th><th>Input / output tokens</th><th>Replay</th></tr></thead>
        <tbody>{value.trials.map(trial => <tr key={trial.id}>
          <th scope="row">{trial.model}<small>{trial.mode} · {trial.scope === "sector_pilot" ? "Sector-one pilot" : "Full game"}</small></th>
          <td>{words(trial.status)}</td><td>{fullgameOutcome(trial)}{trial.reason ? <small>{words(trial.reason)}</small> : null}</td>
          <td>{seconds(trial.model_calls?.latency_seconds?.total)}</td>
          <td>{number(trial.model_calls?.usage?.complete_totals?.input_tokens)} / {number(trial.model_calls?.usage?.complete_totals?.output_tokens)}</td>
          <td><ReplayLink trial={trial} onSelect={onSelect} /></td>
        </tr>)}</tbody>
      </table></div>
    </> : <><div className="comparison-table-wrap"><table className="comparison-table">
      <caption>Saved outcomes by requested model, observation mode, and challenge</caption>
      <thead><tr><th>Condition</th><th>Recorded attempts</th><th>Saved outcomes</th><th>Eligible / excluded</th>
        <th>Model response time</th><th>Input / output tokens</th></tr></thead>
      <tbody>{value.conditions.map(condition => <tr key={`${condition.model}/${condition.mode}/${condition.scenario}`}>
        <th scope="row">{condition.model}<small>{condition.mode} · {words(condition.scenario)}</small></th>
        <td>{condition.attempts}</td>
        <td>{Object.entries(condition.outcomes).map(([name, count]) => <div key={name}>{words(name)}: {count}</div>)}</td>
        <td>{condition.eligible_trials} / {condition.excluded_trials}<small>{condition.matched_pair_trials} matched trials</small></td>
        <td>{seconds(condition.model_calls_all_attempts?.latency_seconds?.total)}</td>
        <td>{number(condition.model_calls_all_attempts?.usage?.complete_totals?.input_tokens)} / {number(condition.model_calls_all_attempts?.usage?.complete_totals?.output_tokens)}</td>
      </tr>)}</tbody>
    </table></div>
    {!value.conditions.length ? <p className="muted">No scored trial results have been saved yet.</p> : null}</>}
    <p className="muted">Usage and response time cover recorded attempts only. Missing values mean unavailable; they are not zero.</p>
    <details className="comparison-trials"><summary>Exact trials and replays ({value.trials.length})</summary>
      <ul>{value.trials.map(trial => <li key={trial.id}>
        <div><strong>{trial.model} · {trial.mode} · {fullgame ? trial.scope === "sector_pilot" ? "Sector-one pilot" : "Full game" : `${words(trial.challenge || "challenge")} · Repeat ${trial.repetition}`}</strong>
          <small>{kinds[trial.kind] || words(trial.kind)} · {words(trial.status)}
            {trial.outcome_category ? ` · ${words(trial.outcome_category)}` : ""}
            {trial.reason ? ` · ${words(trial.reason)}` : ""}</small>
          {trial.decisions != null ? <small>{trial.decisions} decisions · Model response time {seconds(trial.model_calls?.latency_seconds?.total)}</small> : null}
          {trial.model_calls ? <small>Resolved model: {trial.model_calls.response_model_identity?.reported_models?.join(", ") || "not reported"}</small> : null}
          {trial.exclusions?.length ? <small>Excluded: {trial.exclusions.map(words).join(", ")}</small> : null}
          {fullgame ? <small>{fullgameOutcome(trial)}</small> : null}
          {fullgame && trial.metrics ? <small>Final hull: {number(trial.metrics.final_hull)} · Living crew: {number(trial.metrics.crew_alive)}</small> : null}
          {trial.cleanup_evidence?.length ? <details><summary>Saved cleanup checks ({trial.cleanup_evidence.length})</summary>
            <ul>{trial.cleanup_evidence.map(check => <li key={check.path}>{check.checked_at} · Point-in-time cleanup passed<br />
              <code>{check.sha256}</code></li>)}</ul></details> : null}
        </div>
        <ReplayLink trial={trial} onSelect={onSelect} />
      </li>)}</ul>
    </details>
    <details className="muted"><summary>Scope and report identity</summary>
      <p>{value.source}</p><p>Protocol: <code>{value.protocol_sha256}</code></p>
      {value.contract ? <p>Contract: <code>{value.contract}</code></p> : null}
      {value.artifact_sha256 ? <ul>{Object.entries(value.artifact_sha256).map(([name, hash]) => <li key={name}>{name}: <code>{hash || "unavailable"}</code></li>)}</ul> : null}
      <ul>{value.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </details>
    {value.stored_admission ? <details className="muted"><summary>Stored portable admission provenance</summary>
      <p>{value.stored_admission.source}</p>
      {(["spec", "candidate", "build_origin", "review", "reviewer", "runtime", "runtime_files", "evidence_files"] as const).map(name =>
        <details key={name}><summary>{words(name)}</summary><pre><code>{JSON.stringify(value.stored_admission![name], null, 2)}</code></pre></details>)}
    </details> : null}
  </div>;
}

export default function ComparisonOverview({ onSelect }: { onSelect: (selection: string) => void }) {
  const [catalog, setCatalog] = useState<Catalog>({ comparisons: [] });
  const [key, setKey] = useState("");
  const [value, setValue] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let active = true, inFlight = false;
    async function load() {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch("/api/comparisons", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error(`Comparison catalog: HTTP ${response.status}`);
        const next = await response.json() as Catalog;
        if (!active) return;
        setCatalog(next);
        const selected = key || next.comparisons[0]?.key;
        if (selected) {
          const report = await fetch(`/api/comparisons?key=${encodeURIComponent(selected)}`, { signal: controller.signal, cache: "no-store" });
          if (!report.ok) throw new Error(`Comparison report: HTTP ${report.status}`);
          const result = await report.json() as Comparison;
          if (active) setValue(result);
        } else setValue(null);
        if (active) setError(null);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Comparison unavailable");
      } finally { inFlight = false; }
    }
    load();
    const timer = window.setInterval(load, 10000);
    return () => { active = false; controller.abort(); window.clearInterval(timer); };
  }, [key]);
  if (!catalog.comparisons.length && !error) return null;
  return <section className="visual-replay comparison-overview" aria-label="Saved experiment overview">
    <div className="visual-title"><h2>{value?.experiment_kind === "full_game" ? "Full-game experiment" : "Challenge experiment"}</h2>
      <label>Saved experiment <select value={key || value?.key || ""} onChange={event => { setValue(null); setKey(event.target.value); }}>
        {catalog.comparisons.map(item => <option key={item.key} value={item.key}>{item.name} · {item.experiment_kind === "full_game" ? "Full game" : "Challenges"}</option>)}
      </select></label>
    </div>
    {error ? <p className="api-error">{error}. Any visible report is the previous successful refresh.</p> : null}
    {value ? <ComparisonView value={value} onSelect={onSelect} /> : <p className="muted">Loading saved report…</p>}
  </section>;
}
