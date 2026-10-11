import type { DashboardState } from "./types";

const labels: Record<string, string> = {
  achieved: "Challenge completed", setup_verified: "Starting conditions verified",
  failed_native_loss: "Ship or crew lost", budget_exhausted: "Trial limit reached",
  infrastructure_failure: "Harness or service failure", model_protocol_failure: "Unusable model response",
  native_goal_not_achieved: "Challenge incomplete", native_game_over: "Game over",
  native_victory: "Victory", decision_budget: "Decision limit reached",
  wall_clock_budget: "Time limit reached", idle_decision_budget: "Idle limit reached",
  cooperative_stop_requested: "Stop requested", operator_interruption: "Trial interrupted",
};

export default function TrialResult({ trial }: { trial: DashboardState["visual_trial"] }) {
  if (!trial) return null;
  const result = trial.outcome || trial.reason || "In progress";
  const checks = trial.setup_only ? trial.setup_checks : trial.outcome_checks;
  return <section className="visual-replay" aria-label="Trial result">
    <div className="visual-title"><div>
      <h2>{trial.operator_recovery ? "Trial interrupted; recovery verified" : labels[result] || result.replace(/_/g, " ")}</h2>
      <p>{trial.challenge?.replace(/-/g, " ") || "Full-game trial"}
        {trial.repetition ? ` · Repetition ${trial.repetition}` : ""}
        {trial.model ? ` · ${trial.model}` : ""}{trial.mode ? ` · ${trial.mode}` : ""}</p>
    </div></div>
    {trial.task ? <p>{trial.task}</p> : null}
    {trial.task_version ? <p className="muted">Task version: {trial.task_version}</p> : null}
    {trial.setup_only ? <p className="muted">Setup check only. No model played this challenge.</p> : null}
    {trial.error ? <p className="api-error">{trial.error}</p> : null}
    <p className="muted">Original saves: {trial.operator_recovery ? `manual recovery verified for ${trial.operator_recovery.original_save_count} saves at ${trial.operator_recovery.recovered_at}`
      : trial.save_restoration === "verified" ? "restored and verified" : "restoration not yet verified"}.</p>
    {trial.operator_recovery ? <div role="note">
      <p>The runner stopped before automatic cleanup finished. Operator recovery closed the game and restored the saved originals.</p>
      <p className="muted">Initiator: {trial.operator_recovery.initiator}. The raw lifecycle remains incomplete; this receipt records recovery, not completed gameplay.</p>
    </div> : null}
    {trial.adjudication ? <div role="note">
      <h3>Scoring review</h3><p>{trial.adjudication.summary}</p>
      {trial.adjudication.model_observation_error ? <p>The review also identified an incorrect model observation.</p> : null}
      <p className="muted">The original recorded outcome is preserved. {trial.adjudication.scope}</p>
    </div> : null}
    {trial.annotation_issues?.map(issue => <p className="api-error" key={issue}>Supplemental evidence could not be verified: {issue}</p>)}
    {Object.keys(checks || {}).length ? <details className="muted"><summary>Recorded outcome checks</summary>
      <ul>{Object.entries(checks).map(([name, passed]) => <li key={name}>
        {passed ? "Passed" : "Not met"}: {name.replace(/_/g, " ")}
      </li>)}</ul>
    </details> : null}
    {trial.limitations?.length ? <details className="muted"><summary>Trial scope</summary>
      <ul>{trial.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </details> : null}
  </section>;
}
