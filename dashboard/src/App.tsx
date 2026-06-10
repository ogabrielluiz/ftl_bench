import { useEffect, useMemo, useState } from "react";
import type {
  ActionView,
  DashboardState,
  FeedItem,
  HeaderState,
  InstanceItem,
  StepState,
  SystemStatus
} from "./types";

const POLL_MS = 2000;

type Tone = "good" | "warn" | "danger" | "neutral" | "info";

function clamp(value: number, min = 0, max = 100) {
  return Math.min(max, Math.max(min, value));
}

function asNumber(value: number | null | undefined, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function display(value: number | string | null | undefined, fallback = "--") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function percent(value: number | null | undefined, max = 100) {
  return clamp((asNumber(value) / max) * 100);
}

function shortPath(path: string | null | undefined) {
  if (!path) return "path unknown";
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts.slice(-3).join("/");
}

function toneForLowGood(value: number | null | undefined, warn: number, danger: number): Tone {
  if (value === null || value === undefined) return "neutral";
  if (value <= danger) return "danger";
  if (value <= warn) return "warn";
  return "good";
}

function timeAgo(seconds: number) {
  if (seconds < 5) return "now";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function parsePair(pair: string | null | undefined) {
  if (!pair) return null;
  const match = /^(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)$/.exec(pair);
  if (!match) return null;
  const current = Number(match[1]);
  const max = Number(match[2]);
  if (!Number.isFinite(current) || !Number.isFinite(max) || max <= 0) return null;
  return { current, max, pct: clamp((current / max) * 100) };
}

function formatDelta(from: number | null | undefined, to: number | null | undefined, suffix = "") {
  if (from === null || from === undefined || to === null || to === undefined) return "--";
  if (from === to) return `${to}${suffix}`;
  return `${from}${suffix} -> ${to}${suffix}`;
}

function feedTone(item: FeedItem): Tone {
  if (item.collapsed) return item.phase === "recovery" ? "warn" : "info";
  const kinds = new Set(item.actions.map((action) => action.kind));
  if (kinds.has("fire") || kinds.has("event")) return "danger";
  if (kinds.has("jump")) return "good";
  if (kinds.has("store")) return "info";
  return "neutral";
}

function actionMix(feed: FeedItem[]) {
  const counts = new Map<string, number>();
  for (const item of feed) {
    for (const action of item.actions) {
      counts.set(action.kind, (counts.get(action.kind) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 6);
}

function buildAttention(header: HeaderState) {
  const items: Array<{ label: string; value: string; tone: Tone }> = [];
  const oxygen = header.oxygen;
  const hull = header.hull;
  const hullMax = header.hull_max || 30;
  const crewMin = header.crew_min;
  const fires = asNumber(header.fires);
  const intruders = asNumber(header.intruders);
  const repairNeeded = new Set(header.repair_needed ?? []);

  if (hull !== null && hull !== undefined && hull <= Math.max(8, hullMax * 0.35)) {
    items.push({ label: "Hull", value: `${hull}/${hullMax}`, tone: hull <= 6 ? "danger" : "warn" });
  }
  if (oxygen !== null && oxygen !== undefined && oxygen < 60) {
    items.push({ label: "Oxygen", value: `${oxygen}%`, tone: oxygen <= 20 ? "danger" : "warn" });
  }
  if (crewMin !== null && crewMin !== undefined && crewMin <= 35) {
    items.push({ label: "Crew health", value: `${crewMin.toFixed(0)} hp min`, tone: crewMin <= 12 ? "danger" : "warn" });
  }
  if (fires > 0) {
    items.push({ label: "Fire", value: `${fires} active`, tone: "danger" });
  }
  if (intruders > 0) {
    items.push({ label: "Intruders", value: `${intruders} aboard`, tone: "danger" });
  }
  for (const name of repairNeeded) {
    items.push({ label: "Repair", value: name, tone: name === "oxygen" ? "danger" : "warn" });
  }
  const incoming = asNumber(header.incoming);
  if (incoming > 0) {
    items.push({ label: "Incoming fire", value: `${incoming} inbound`, tone: incoming >= 2 ? "danger" : "warn" });
  }
  for (const drone of header.enemy_drones ?? []) {
    items.push({ label: "Enemy drone", value: `${drone.type}${drone.firing ? " - firing" : ""}`, tone: "danger" });
  }
  for (const name of header.offline ?? []) {
    if (repairNeeded.has(name)) continue;
    items.push({ label: "Offline", value: name, tone: name === "oxygen" ? "danger" : "warn" });
  }
  for (const name of header.damaged ?? []) {
    if (repairNeeded.has(name)) continue;
    items.push({ label: "Damaged", value: name, tone: "warn" });
  }
  if (header.event) {
    items.push({ label: "Blocking event", value: "choice open", tone: "info" });
  }
  if (header.store) {
    items.push({ label: "Store", value: "available", tone: "info" });
  }
  if (items.length === 0) {
    items.push({ label: "Ship state", value: "no urgent faults", tone: "good" });
  }
  return items.slice(0, 8);
}

function Bar({ value, tone = "info" }: { value: number; tone?: Tone }) {
  return (
    <div className="bar" aria-hidden="true">
      <div className={`bar-fill ${tone}`} style={{ width: `${clamp(value)}%` }} />
    </div>
  );
}

function StatusDot({ tone }: { tone: Tone }) {
  return <span className={`status-dot ${tone}`} aria-hidden="true" />;
}

function MetricCard({
  label,
  value,
  sub,
  tone = "neutral",
  bar
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  bar?: number;
}) {
  return (
    <section className={`metric-card ${tone}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub ? <div className="metric-sub">{sub}</div> : null}
      {bar !== undefined ? <Bar value={bar} tone={tone} /> : null}
    </section>
  );
}

function ActionChip({ action }: { action: ActionView }) {
  return <span className={`action-chip ${action.kind}`}>{action.label}</span>;
}

function ThoughtBlock({ text, label }: { text?: string | null; label?: string }) {
  const [expanded, setExpanded] = useState(false);
  const value = text || "No reasoning text recorded.";
  const canExpand = value.length > 180;
  const recordedTruncated = /(?:\.\.\.|…)$/.test(value.trim());

  return (
    <div className="thought-block">
      <p className={`thought ${canExpand && !expanded ? "clamped" : ""}`}>
        {label ? <span>{label}</span> : null}
        {value}
      </p>
      <div className="thought-tools">
        {recordedTruncated ? <span className="source-note">recorded text ends here</span> : null}
        {canExpand ? (
          <button className="text-button" onClick={() => setExpanded((next) => !next)} type="button">
            {expanded ? "show less" : "show full"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function StatePills({ state }: { state: StepState }) {
  return (
    <div className="state-pills">
      <span>Hull {display(state.hull)}</span>
      <span>O2 {display(state.oxygen)}%</span>
      {state.crew_min !== null && state.crew_min !== undefined ? <span>Crew min {state.crew_min.toFixed(0)}</span> : null}
      <span>Enemy {display(state.enemy, "none")}</span>
      <span>Fire {display(state.fires, "0")}</span>
      {state.incoming ? <span className="threat">Incoming {state.incoming}</span> : null}
      {state.enemy_drones && state.enemy_drones.length ? (
        <span className="threat">Drone {state.enemy_drones.map((drone) => drone.type).join(", ")}</span>
      ) : null}
    </div>
  );
}

function Delta({ label, value }: { label: string; value: string }) {
  return (
    <div className="delta">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TimelineItem({ item }: { item: FeedItem }) {
  const tone = feedTone(item);
  const title = item.collapsed
    ? `${item.count ?? 0} ${item.phase ?? "stabilize"} turns`
    : item.actions.some((action) => action.kind === "jump")
      ? "Navigation"
      : item.actions.some((action) => action.kind === "fire")
        ? "Combat"
        : item.actions.some((action) => action.kind === "event")
          ? "Event"
          : "Decision";

  return (
    <article className={`timeline-card ${tone}`}>
      <div className="timeline-marker">
        <StatusDot tone={tone} />
        <span>#{item.i}</span>
      </div>
      <div className="timeline-body">
        <div className="timeline-head">
          <h3>{title}</h3>
          <span>{item.advance ? `${item.advance} frames` : "advance pending"}</span>
        </div>

        {item.collapsed ? (
          <div className="collapsed-block">
            <div className="delta-grid">
              <Delta label="Hull" value={formatDelta(item.summary?.hull_from, item.summary?.hull_to)} />
              <Delta label="Oxygen" value={formatDelta(item.summary?.oxygen_from, item.summary?.oxygen_to, "%")} />
              <Delta label="Fires" value={formatDelta(item.summary?.fires_from, item.summary?.fires_to)} />
            </div>
            <ThoughtBlock label="Latest reasoning: " text={item.thought} />
          </div>
        ) : (
          <ThoughtBlock text={item.thought} />
        )}

        <div className="action-row">
          {item.actions.length ? item.actions.map((action, index) => <ActionChip action={action} key={`${action.label}-${index}`} />) : <span className="action-chip other">advance</span>}
        </div>
        <StatePills state={item.state} />
      </div>
    </article>
  );
}

function Timeline({ feed }: { feed: FeedItem[] }) {
  if (!feed.length) {
    return (
      <section className="empty-panel">
        <h2>No trajectory steps yet</h2>
        <p>The live run has not written decisions to the selected JSONL file.</p>
      </section>
    );
  }
  const newestFirst = [...feed].reverse();
  return (
    <section className="timeline-list">
      {newestFirst.map((item, index) => (
        <TimelineItem item={item} key={`${item.i}-${index}`} />
      ))}
    </section>
  );
}

function InstanceButton({
  item,
  selected,
  onSelect
}: {
  item: InstanceItem;
  selected: boolean;
  onSelect: (name: string) => void;
}) {
  const tone: Tone = item.solved ? "good" : item.score !== null && item.score !== undefined ? "warn" : item.live ? "info" : "neutral";
  return (
    <button className={`instance-button ${selected ? "selected" : ""}`} onClick={() => onSelect(item.name)}>
      <span className="instance-main">
        <span className="instance-name">
          <StatusDot tone={item.live ? "good" : item.current ? "info" : tone} />
          {item.name}
        </span>
        <span className="instance-meta">
          {item.steps} steps {item.age !== undefined ? `- ${timeAgo(item.age)} ago` : ""}
        </span>
      </span>
      <span className={`score-pill ${tone}`}>
        {item.score !== null && item.score !== undefined ? item.score : item.live ? "live" : "--"}
        {item.solved ? " solved" : ""}
      </span>
    </button>
  );
}

function Sidebar({
  data,
  query,
  setQuery,
  selection,
  setSelection
}: {
  data: DashboardState;
  query: string;
  setQuery: (value: string) => void;
  selection: string;
  setSelection: (value: string) => void;
}) {
  const filtered = data.instances.filter((item) => {
    const haystack = `${item.name} ${item.scenario} ${item.type ?? ""} ${item.tier ?? ""}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });
  const current = filtered.filter((item) => item.current);
  const other = filtered.filter((item) => !item.current);

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">ftl</span>
        <span>bench live</span>
      </div>

      <button className={`follow-button ${data.following_live ? "active" : ""}`} onClick={() => setSelection("live")}>
        <span>Follow latest run</span>
        <small>{data.process.label}</small>
      </button>

      <input
        className="search"
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Filter instances"
        value={query}
      />

      <div className="side-section">
        <div className="side-heading">
          <span>Current run</span>
          <span>{current.length || 0}</span>
        </div>
        <div className="instance-list">
          {current.map((item) => (
            <InstanceButton item={item} key={item.name} onSelect={setSelection} selected={selection !== "live" && selection === item.name} />
          ))}
        </div>
      </div>

      <div className="side-section">
        <div className="side-heading">
          <span>History</span>
          <span>{other.length}</span>
        </div>
        <div className="instance-list">
          {other.map((item) => (
            <InstanceButton item={item} key={item.name} onSelect={setSelection} selected={selection === item.name} />
          ))}
        </div>
      </div>

      <div className="sidebar-footer">
        <div>
          <span>Done</span>
          <strong>{data.agg ? `${data.agg.done}/${data.agg.total}` : "--"}</strong>
        </div>
        <div>
          <span>Mean</span>
          <strong>{data.agg ? data.agg.mean : "--"}</strong>
        </div>
        <div>
          <span>Solved</span>
          <strong>{data.agg ? `${data.agg.solved}/${data.agg.total}` : "--"}</strong>
        </div>
      </div>
    </aside>
  );
}

function SystemStrip({ systems }: { systems?: SystemStatus[] }) {
  if (!systems?.length) return null;
  return (
    <div className="system-strip">
      {systems.map((system) => {
        const power = asNumber(system.power);
        const max = asNumber(system.max);
        const powerPct = max > 0 ? (power / max) * 100 : 0;
        const needsRepair = Boolean(system.needs_repair);
        const tone: Tone = needsRepair && system.name === "oxygen"
          ? "danger"
          : needsRepair || system.damage || system.ion
            ? "warn"
            : max > 0 && power === 0
              ? "danger"
              : "good";
        const status = needsRepair
          ? "repair"
          : system.damage
            ? `damage ${system.damage}`
            : system.ion
              ? `ion ${system.ion}`
              : max > 0 && power === 0
                ? "offline"
                : "online";
        return (
          <div className={`system-tile ${tone}`} key={system.name}>
            <div>
              <span>{system.name}</span>
              <strong>{max ? `${power}/${max}` : "--"}</strong>
            </div>
            <Bar value={powerPct} tone={tone} />
            <small>{status}</small>
          </div>
        );
      })}
    </div>
  );
}

function TopPanel({ data, lastUpdated }: { data: DashboardState; lastUpdated: Date | null }) {
  const header = data.header;
  const hullMax = header.hull_max || 30;
  const enemy = parsePair(header.enemy);
  const score = data.selected_score?.score ?? header.ftl_score;
  const runLabel = data.following_live ? "following live" : "inspecting history";
  const processTone: Tone = data.process.alive === true ? "good" : data.process.alive === false ? "danger" : "neutral";
  const currentInstance = data.run.current_instance || "none";

  return (
    <header className="top-panel">
      <div className="run-title">
        <div>
          <div className="eyebrow">
            <StatusDot tone={processTone} />
            {runLabel}
          </div>
          <h1>{header.instance || "No instance selected"}</h1>
          <p>{header.scenario || "Waiting for a trajectory file"}</p>
        </div>
        <div className="run-meta">
          <span>{display(header.agent, "agent unknown")}</span>
          <span>{display(data.run.run_id || header.run_id, "run id pending")}</span>
          <span>{lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : "not refreshed"}</span>
        </div>
      </div>

      <div className={`source-banner ${data.following_live ? "live" : "history"}`}>
        <strong>{data.following_live ? "Live trajectory" : "Historical snapshot"}</strong>
        <span>
          {data.following_live
            ? `${display(header.instance)} from ${shortPath(data.run.bench)}`
            : `${display(header.instance)} is not the live FTL window. Live file: ${currentInstance} in ${shortPath(data.run.bench)}.`}
        </span>
      </div>

      <div className="metric-grid">
        <MetricCard
          label="Hull"
          value={`${display(header.hull)}/${hullMax}`}
          sub={`sector ${display(header.sector, "0")} - ${header.steps} steps`}
          tone={toneForLowGood(header.hull, 16, 8)}
          bar={percent(header.hull, hullMax)}
        />
        <MetricCard
          label="Oxygen"
          value={`${display(header.oxygen)}%`}
          sub={header.fires ? `${header.fires} fire tiles` : "rooms stable"}
          tone={toneForLowGood(header.oxygen, 60, 25)}
          bar={percent(header.oxygen)}
        />
        <MetricCard
          label="Crew"
          value={`${display(header.crew)} alive`}
          sub={header.crew_min !== null && header.crew_min !== undefined ? `min ${header.crew_min.toFixed(0)} hp` : "health unknown"}
          tone={header.crew_low ? "warn" : "good"}
          bar={percent(header.crew_min ?? 100)}
        />
        <MetricCard
          label={header.enemy_present ? "Enemy" : "Score"}
          value={header.enemy_present ? display(header.enemy) : display(score)}
          sub={header.enemy_present ? "enemy hull" : data.selected_score?.solved ? "solved" : "current FTL score"}
          tone={header.enemy_present ? "danger" : data.selected_score?.solved ? "good" : "info"}
          bar={header.enemy_present && enemy ? enemy.pct : percent(score ?? 0, 350)}
        />
      </div>

      <div className="resource-row">
        <span>Fuel {display(header.fuel)}</span>
        <span>Missiles {display(header.missiles)}</span>
        <span>Drone parts {display(header.parts)}</span>
        <span>Scrap {display(header.scrap)}</span>
        {header.event ? <span className="accent">Event open</span> : null}
        {header.store ? <span className="accent">Store</span> : null}
      </div>

      <SystemStrip systems={header.systems} />
    </header>
  );
}

function InsightPanel({ data }: { data: DashboardState }) {
  const attention = buildAttention(data.header);
  const mix = actionMix(data.feed);
  const aggregate = data.agg;
  const progress = aggregate ? percent(aggregate.done, aggregate.total) : 0;

  return (
    <aside className="insight-panel">
      <section className="panel-section">
        <div className="panel-head">
          <h2>Attention</h2>
          <span>{attention.length}</span>
        </div>
        <div className="attention-list">
          {attention.map((item, index) => (
            <div className={`attention-item ${item.tone}`} key={`${item.label}-${item.value}-${index}`}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <div className="panel-head">
          <h2>Run Progress</h2>
          <span>{aggregate ? `${aggregate.done}/${aggregate.total}` : "--"}</span>
        </div>
        <Bar value={progress} tone={aggregate && aggregate.solved === aggregate.total ? "good" : "info"} />
        <dl className="summary-list">
          <div>
            <dt>Mean FTL</dt>
            <dd>{aggregate ? aggregate.mean : "--"}</dd>
          </div>
          <div>
            <dt>Solved</dt>
            <dd>{aggregate ? `${aggregate.solved}/${aggregate.total}` : "--"}</dd>
          </div>
          <div>
            <dt>Attempt files</dt>
            <dd>{aggregate ? aggregate.attempt_files : "--"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel-section">
        <div className="panel-head">
          <h2>Visible Actions</h2>
          <span>{data.feed.length}</span>
        </div>
        <div className="mix-list">
          {mix.length ? (
            mix.map(([kind, count]) => (
              <div key={kind}>
                <span>{kind}</span>
                <strong>{count}</strong>
              </div>
            ))
          ) : (
            <p className="muted">No actions recorded.</p>
          )}
        </div>
      </section>

      <section className="panel-section paths">
        <h2>Sources</h2>
        <p>{data.run.bench}</p>
        <p>{data.run.suite}</p>
      </section>
    </aside>
  );
}

function App() {
  const [data, setData] = useState<DashboardState | null>(null);
  const [selection, setSelection] = useState("live");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(`/api/state?sel=${encodeURIComponent(selection)}`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const next = (await response.json()) as DashboardState;
        if (!cancelled) {
          setData(next);
          setError(null);
          setLastUpdated(new Date());
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load dashboard state");
        }
      }
    }

    load();
    const id = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selection]);

  const selectedName = useMemo(() => {
    if (!data) return selection;
    return data.following_live ? "live" : data.selected ?? selection;
  }, [data, selection]);

  if (!data) {
    return (
      <main className="loading-screen">
        <div>
          <span className="brand-mark">ftl</span>
          <h1>Loading dashboard</h1>
          <p>{error ? `API error: ${error}` : "Waiting for /api/state"}</p>
        </div>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar data={data} query={query} selection={selectedName} setQuery={setQuery} setSelection={setSelection} />
      <main className="main">
        <TopPanel data={data} lastUpdated={lastUpdated} />
        {error ? <div className="api-error">API refresh failed: {error}</div> : null}
        <div className="content-grid">
          <Timeline feed={data.feed} />
          <InsightPanel data={data} />
        </div>
      </main>
    </div>
  );
}

export default App;
