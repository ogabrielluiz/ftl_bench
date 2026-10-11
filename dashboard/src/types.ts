export type ActionKind =
  | "power"
  | "crew"
  | "doors"
  | "fire"
  | "jump"
  | "event"
  | "store"
  | "special"
  | "other";

export interface ActionView {
  kind: ActionKind | string;
  label: string;
  count?: number;
}

export interface EnemyDrone {
  type: string | number;
  firing: boolean;
}

export interface StepState {
  hull?: number | null;
  oxygen?: number | null;
  crew_min?: number | null;
  enemy?: string | null;
  enemy_hostile?: boolean | null;
  fires?: number | null;
  incoming?: number | null;
  enemy_drones?: EnemyDrone[];
}

export interface FeedSummary {
  hull_from?: number | null;
  hull_to?: number | null;
  oxygen_from?: number | null;
  oxygen_to?: number | null;
  fires_from?: number | null;
  fires_to?: number | null;
}

export interface FeedItem {
  i: number | string;
  record_kind?: string;
  thought?: string | null;
  model?: ModelTrace | null;
  visual?: VisualTrace | null;
  ack_timeout?: boolean;
  actions: ActionView[];
  elapsed_seconds?: number | null;
  state: StepState;
  collapsed?: boolean;
  count?: number;
  phase?: string;
  summary?: FeedSummary;
}

export interface VisualFrame {
  path?: string;
  url: string;
  width?: number;
  height?: number;
  frame_id?: number | string;
  sha256?: string;
}

export interface VisualInput {
  type: string;
  x?: number;
  y?: number;
  to_x?: number;
  to_y?: number;
  button?: string;
  key?: string;
  modifiers?: string[];
  delivery?: string;
  reason?: string;
}

export interface VisualTrace {
  observation_mode?: string;
  before?: VisualFrame;
  after?: VisualFrame;
  inputs?: VisualInput[];
  planned_inputs?: VisualInput[];
  external_input_guard?: {
    reason?: string;
    expected_generation?: string | null;
    observed_generation?: string | null;
    external_input_detected?: boolean;
    packet_dispatched?: boolean;
    action_seq?: number | null;
  };
  advance?: {
    requested_frames?: number | null;
    actual_frames?: number | null;
    visual_clock_version?: number;
    fixed_step_numerator?: number;
    fixed_step_denominator?: number;
    simulated_seconds?: number | null;
  };
  outcome?: { status?: string; summary?: string };
  visible_summary?: unknown;
  visible_summary_provenance?: {
    contract?: string;
    image_sha256?: string;
    fields?: Record<string, { status: string; reason?: string; value?: number }>;
  } | null;
}

export interface VisualReplayState {
  selected: string;
  total: number;
  index: number | null;
  item?: { i: number | string; record_kind?: string; thought?: string; model?: ModelTrace; ack_timeout?: boolean; visual: VisualTrace } | null;
}

export interface ModelTrace {
  model?: string;
  provider?: string;
  request_id?: string;
  client_request_id?: string;
  latency_seconds?: number;
  usage?: { input_tokens?: number; output_tokens?: number };
}

export interface ModelUsage {
  recorded_completions: number;
  models: string[];
  providers: string[];
  input_tokens: number | null;
  output_tokens: number | null;
  latency_seconds_mean: number | null;
  recorded_cost_usd: number | null;
  scope: string;
}

export interface InstanceItem {
  comparison_eligible?: boolean;
  name: string;
  label: string;
  run_id?: string | null;
  status: string;
  reason?: string | null;
  error?: string | null;
  partial?: boolean;
  scenario: string;
  attempt?: number | null;
  steps: number;
  live: boolean;
  current: boolean;
  score?: number | null;
  solved?: boolean | null;
  tier?: string | null;
  type?: string | null;
  age: number;
}

export interface SystemStatus {
  name: string;
  power?: number | null;
  max?: number | null;
  damage?: number | null;
  needs_repair?: boolean;
  ion?: number | null;
  powered?: boolean;
}

export interface HeaderState {
  model_usage?: ModelUsage | null;
  instance?: string | null;
  scenario?: string | null;
  agent?: string | null;
  run_id?: string | null;
  status: string;
  live: boolean;
  reason?: string | null;
  error?: string | null;
  partial?: boolean;
  steps: number;
  visual_steps?: number;
  sector?: number | null;
  hull?: number | null;
  hull_max?: number | null;
  oxygen?: number | null;
  fuel?: number | null;
  missiles?: number | null;
  parts?: number | null;
  scrap?: number | null;
  crew?: number | null;
  crew_min?: number | null;
  crew_low?: number | null;
  fires?: number | null;
  fire_rooms?: Array<number | null>;
  intruders?: number | null;
  damaged?: string[];
  repair_needed?: string[];
  offline?: string[];
  systems?: SystemStatus[];
  enemy?: string | null;
  enemy_present?: boolean;
  enemy_hostile?: boolean | null;
  incoming?: number | null;
  enemy_drones?: EnemyDrone[];
  event?: boolean;
  store?: boolean;
  ftl_score?: number | null;
}

export interface AggregateState {
  done: number;
  total: number;
  mean: number | null;
  total_known: boolean;
  scored: number;
  failed: number;
  interrupted: number;
  attempt_failures: number;
  attempt_interrupted: number;
  incomplete: number;
  solved: number;
  attempt_files: number;
  comparison_instances: number;
  comparison_excluded: number;
  recorded_scored: number;
  recorded_mean: number | null;
  recorded_solved: number;
}

export interface ProcessState {
  known: boolean;
  alive?: boolean | null;
  label: string;
}

export interface RunState {
  validation?: {
    status?: string | null;
    comparison_eligible: boolean;
    valid_for_model_comparison?: boolean | null;
    limitations: string[];
  };
  agent?: string | null;
  run_id?: string | null;
  current_instance?: string | null;
  active_instance?: string | null;
  status: string;
  reason?: string | null;
  error?: string | null;
  suite: string;
  bench: string;
  dashboard_built: boolean;
}

export interface SelectedScore {
  score?: number;
  solved?: boolean;
  breakdown?: Record<string, unknown>;
}

export interface DashboardState {
  visual_trial?: {
    challenge?: string | null;
    repetition?: number | null;
    task?: string | null;
    task_version?: string | null;
    model?: string | null;
    mode?: string | null;
    outcome?: string | null;
    reason?: string | null;
    setup_only: boolean;
    setup_checks: Record<string, boolean>;
    outcome_checks: Record<string, boolean>;
    save_restoration?: string | null;
    limitations: string[];
    error?: string | null;
    adjudication?: { summary?: string; scope?: string; written_task_satisfied?: boolean;
      recorded_outcome_kept?: boolean; model_observation_error?: boolean } | null;
    operator_recovery?: { recovered_at?: string; initiator?: string; reason?: string; mechanism?: string;
      automatic_cleanup_completed?: boolean; manual_recovery_verified?: boolean;
      raw_lifecycle_unchanged?: boolean; original_save_count?: number; scope?: string } | null;
    annotation_issues?: string[];
  } | null;
  instances: InstanceItem[];
  selected?: string | null;
  following_live: boolean;
  header: HeaderState;
  feed: FeedItem[];
  agg?: AggregateState | null;
  selected_score?: SelectedScore | null;
  process: ProcessState;
  run: RunState;
  latest_run: RunState;
  now: number;
}
