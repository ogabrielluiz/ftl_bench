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
  thought?: string | null;
  actions: ActionView[];
  advance?: number | null;
  state: StepState;
  collapsed?: boolean;
  count?: number;
  phase?: string;
  summary?: FeedSummary;
}

export interface InstanceItem {
  name: string;
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
  instance?: string | null;
  scenario?: string | null;
  agent?: string | null;
  run_id?: string | null;
  steps: number;
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
  incoming?: number | null;
  enemy_drones?: EnemyDrone[];
  event?: boolean;
  store?: boolean;
  ftl_score?: number | null;
}

export interface AggregateState {
  done: number;
  total: number;
  mean: number;
  solved: number;
  attempt_files: number;
}

export interface ProcessState {
  known: boolean;
  alive?: boolean | null;
  label: string;
}

export interface RunState {
  agent?: string | null;
  run_id?: string | null;
  current_instance?: string | null;
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
  instances: InstanceItem[];
  selected?: string | null;
  following_live: boolean;
  header: HeaderState;
  feed: FeedItem[];
  agg?: AggregateState | null;
  selected_score?: SelectedScore | null;
  process: ProcessState;
  run: RunState;
  now: number;
}
