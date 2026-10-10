import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  CircleDot,
  Crosshair,
  Expand,
  Layers,
  Orbit,
  Pause,
  Play,
  Radio,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Terminal,
  TriangleAlert,
  Waypoints,
  X,
} from "lucide-react";
import OrbitScene from "./OrbitScene";
import { EncounterPlot, SearchPlot, clock, probability } from "./Charts";
import {
  approveMission,
  downloadReport,
  eventStream,
  getMission,
  startMission,
} from "./api";
import type { Decision, Event, Recording, Result, ScenarioId } from "./types";

const scenarios: { id: ScenarioId; name: string; description: string }[] = [
  {
    id: "crossing",
    name: "Crossing paths",
    description: "High-speed crossing · 2 debris objects",
  },
  {
    id: "uncertain",
    name: "Uncertainty trap",
    description: "Inflated covariance · nominal miss can mislead",
  },
  {
    id: "clear",
    name: "Quiet orbit",
    description: "Benign encounter · conserve propellant",
  },
];
const roles = [
  {
    key: "tracker",
    title: "TRACKER",
    icon: Crosshair,
    description: "Propagate & detect",
  },
  {
    key: "risk_analyst",
    title: "RISK ANALYST",
    icon: Activity,
    description: "Challenge uncertainty",
  },
  {
    key: "planner",
    title: "MANEUVER PLANNER",
    icon: Waypoints,
    description: "Search & minimize Δv",
  },
  {
    key: "verifier",
    title: "VERIFIER",
    icon: ShieldCheck,
    description: "Independent cross-check",
  },
];
const describe = (event: Event) => {
  const payload = event.payload;
  if (event.kind === "tool_started")
    return String(payload.tool).replaceAll("_", " ");
  if (event.kind === "search_progress")
    return `${payload.evaluations} candidates evaluated · ${payload.feasible_directions} feasible directions`;
  if (event.kind === "decision")
    return `Mission decision: ${String(payload.decision).replaceAll("_", " ")}`;
  if (event.kind === "provider_policy")
    return "Gemini selected a bounded tool policy";
  if (event.kind === "provider_review")
    return "Gemini review returned with evidence citations";
  if (event.kind === "no_burn") return "Risk below threshold · preserve fuel";
  if (event.kind === "error") return String(payload.message);
  if (event.kind === "approval") return "Human accepted the simulated maneuver";
  return `Evidence recorded: ${payload.id ?? event.kind}`;
};

export default function App() {
  const [result, setResult] = useState<Result | null>(null),
    [scenario, setScenario] = useState<ScenarioId>("crossing");
  const [events, setEvents] = useState<Event[]>([]),
    [running, setRunning] = useState(false),
    [error, setError] = useState("");
  const [online, setOnline] = useState(false),
    [geminiAvailable, setGeminiAvailable] = useState(false),
    [mode, setMode] = useState("numerical");
  const [budget, setBudget] = useState(1),
    [threshold, setThreshold] = useState(1e-4),
    [operator, setOperator] = useState("");
  const [time, setTime] = useState(0),
    [playing, setPlaying] = useState(false),
    [after, setAfter] = useState(false),
    [decision, setDecision] = useState<Decision>("approval_pending");
  const [source, setSource] = useState<"replay" | "backend">("replay"),
    [missionId, setMissionId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false),
    [approving, setApproving] = useState(false),
    [tab, setTab] = useState<"risk" | "verification" | "assumptions">("risk");
  const [cinema, setCinema] = useState(false);
  const abort = useRef<AbortController | null>(null),
    replayTimer = useRef<ReturnType<typeof setTimeout> | null>(null),
    journalRef = useRef<HTMLDivElement>(null);
  const loadRecording = async (id: ScenarioId) => {
    const response = await fetch(`/demo/${id}.json`);
    if (!response.ok)
      throw new Error(
        "Recorded mission could not be loaded. Start the backend to compute a mission.",
      );
    return response.json() as Promise<Recording>;
  };
  useEffect(() => {
    let active = true;
    loadRecording("crossing")
      .then((recording) => {
        if (active) {
          setResult(recording.result);
          setEvents(recording.events);
          setDecision(recording.result.decision);
        }
      })
      .catch((e) => setError(e.message));
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((health) => {
        if (active) {
          setOnline(true);
          setGeminiAvailable(health.gemini_configured);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      abort.current?.abort();
      if (replayTimer.current) clearTimeout(replayTimer.current);
    };
  }, []);
  useEffect(() => {
    if (!playing || !result) return;
    let last = performance.now();
    let frame: number;
    const animate = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setTime((value) => {
        const next = value + dt * 45;
        if (next >= result.horizon_s) {
          setPlaying(false);
          return result.horizon_s;
        }
        return next;
      });
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [playing, result]);
  useEffect(() => {
    if (journalRef.current)
      journalRef.current.scrollTop = journalRef.current.scrollHeight;
  }, [events]);
  async function run() {
    setError("");
    setRunning(true);
    setDecision("blocked");
    setPlaying(false);
    setAfter(false);
    setTime(0);
    setEvents([]);
    setMissionId(null);
    abort.current?.abort();
    try {
      if (!online) {
        if (mode !== "numerical" || budget !== 1 || threshold !== 1e-4)
          throw new Error(
            "Bundled replay uses fixed parameters: 1 m/s budget and 10⁻⁴ threshold. Start the backend for custom runs.",
          );
        const recording = await loadRecording(scenario);
        let i = 0;
        const step = () => {
          const event = recording.events[i];
          setEvents((previous) => [...previous, event]);
          i++;
          if (i < recording.events.length) {
            replayTimer.current = setTimeout(step, 320);
          } else {
            setSource("replay");
            setResult(recording.result);
            setDecision(recording.result.decision);
            setRunning(false);
          }
        };
        step();
      } else {
        const created = await startMission(
          scenario,
          mode,
          budget,
          threshold,
          operator,
        );
        setMissionId(created.id);
        abort.current = new AbortController();
        await eventStream(
          created.id,
          (event) => setEvents((previous) => [...previous, event]),
          abort.current.signal,
        );
        const mission = await getMission(created.id);
        if (mission.error) throw new Error(mission.error);
        if (!mission.result)
          throw new Error(
            "Mission did not complete. Retry after checking the backend.",
          );
        setSource("backend");
        setResult(mission.result);
        setDecision(mission.status as Decision);
        setRunning(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mission failed.");
      setRunning(false);
    }
  }
  async function approve() {
    if (!result?.verification.passed) return;
    setApproving(true);
    try {
      if (source === "backend") {
        if (!missionId)
          throw new Error("No completed backend mission is available.");
        await approveMission(missionId);
      }
      setDecision("approved");
      setAfter(true);
      setTime(0);
      setPlaying(true);
      setConfirm(false);
      setEvents((previous) => [
        ...previous,
        {
          sequence: previous.length + 1,
          role: "human",
          kind: "approval",
          payload: { simulation_only: true },
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approval failed.");
    } finally {
      setApproving(false);
    }
  }
  if (!result)
    return (
      <div className="loading">
        <Orbit size={42} />
        <h1>ORBIT SENTINEL</h1>
        <p>{error || "Loading mission control…"}</p>
      </div>
    );
  const baseline = result.baseline[0],
    current = after
      ? result.after.find((event) => event.object_id === baseline.object_id)!
      : baseline;
  const lastRole = events.at(-1)?.role;
  const displayedRisk = after
    ? current.worst_stress_probability
    : baseline.worst_stress_probability;
  const changed =
    result.scenario !== scenario ||
    result.parameters.max_delta_v_ms !== budget ||
    result.parameters.risk_threshold !== threshold ||
    result.mode !== mode;
  return (
    <div className={`app ${cinema ? "cinema" : ""}`}>
      <header className="topbar">
        <a className="brand" href="#">
          <span className="logo">
            <Orbit size={27} />
          </span>
          <span>
            ORBIT<span className="brand-light"> SENTINEL</span>
            <small>CONJUNCTION INTELLIGENCE / V0.1</small>
          </span>
        </a>
        <div className="top-status">
          <span className="status-dot" />
          {online ? "COMPUTE ONLINE" : "BUNDLED REPLAY"}
          <span className="separator">/</span>
          <span>SYNTHETIC MISSION</span>
        </div>
        <a
          className="repo-link"
          href="https://github.com/Manoj-619/incident-zero/tree/orbit-sentinel"
          target="_blank"
          rel="noreferrer"
        >
          MANOJ ABRAHAM <ArrowRight size={14} />
        </a>
      </header>
      <aside className="sidebar">
        <div className="rail-label">MISSION / SETUP</div>
        <h2>
          Every burn
          <br />
          needs evidence.
        </h2>
        <p className="intro">
          Detect the encounter. Challenge the risk. Verify the escape.
        </p>
        <label className="field-label">SCENARIO</label>
        <div className="scenario-options">
          {scenarios.map((item) => (
            <button
              key={item.id}
              disabled={running}
              className={`scenario ${scenario === item.id ? "selected" : ""}`}
              onClick={() => setScenario(item.id)}
            >
              <span className="scenario-radio" />
              <span>
                <strong>{item.name}</strong>
                <small>{item.description}</small>
              </span>
              {scenario === item.id && <ChevronRight size={15} />}
            </button>
          ))}
        </div>
        <label className="field-label" htmlFor="mode">
          ORCHESTRATION
        </label>
        <select
          id="mode"
          disabled={running}
          value={mode}
          onChange={(event) => setMode(event.target.value)}
        >
          <option value="numerical">Numerical agents · no API key</option>
          <option value="gemini" disabled={!geminiAvailable}>
            Gemini-assisted planning
          </option>
        </select>
        {mode === "gemini" && (
          <label className="secret-label">
            Operator secret
            <input
              type="password"
              autoComplete="off"
              value={operator}
              onChange={(event) => setOperator(event.target.value)}
              disabled={running}
            />
            <small>Held in memory for this session.</small>
          </label>
        )}
        <div className="slider-label">
          <label className="field-label" htmlFor="budget">
            MANEUVER BUDGET
          </label>
          <strong>
            {budget.toFixed(2)} <span>m/s</span>
          </strong>
        </div>
        <input
          id="budget"
          type="range"
          min="0.05"
          max="2"
          step="0.05"
          value={budget}
          disabled={running || !online}
          onChange={(event) => setBudget(Number(event.target.value))}
        />
        <div className="range-ends">
          <span>0.05 m/s</span>
          <span>2.00 m/s</span>
        </div>
        <label className="field-label" htmlFor="threshold">
          RISK ACCEPTANCE LIMIT
        </label>
        <select
          id="threshold"
          disabled={running || !online}
          value={threshold}
          onChange={(event) => setThreshold(Number(event.target.value))}
        >
          <option value={1e-3}>10⁻³ · exploratory</option>
          <option value={1e-4}>10⁻⁴ · default</option>
          <option value={1e-5}>10⁻⁵ · strict</option>
          <option value={1e-6}>10⁻⁶ · very strict</option>
        </select>
        <button className="primary launch" disabled={running} onClick={run}>
          {running ? (
            <>
              <span className="spinner" /> MISSION IN PROGRESS
            </>
          ) : (
            <>
              <Play size={15} />
              {online ? "RUN INVESTIGATION" : "PLAY RECORDED MISSION"}
              <ArrowRight size={15} />
            </>
          )}
        </button>
        <p className="setup-note">
          {online
            ? "Computes new trajectories and records an auditable event journal."
            : "Replay contains actual precomputed tool results. Start the backend for fresh calculations."}
        </p>
        <div className="sidebar-bottom">
          <ShieldCheck size={19} />
          <div>
            HUMAN AUTHORITY
            <small>Approval changes simulation state only.</small>
          </div>
        </div>
      </aside>
      <main>
        <section className="mission-heading">
          <div>
            <span className="eyebrow">
              MISSION CONTROL <span>/</span> {result.title}
            </span>
            <h1>
              Space is unforgiving.
              <br />
              <span>Decisions shouldn’t be opaque.</span>
            </h1>
          </div>
          <div className="heading-meta">
            <span
              className={`source-badge ${source === "backend" ? "compute" : ""}`}
            >
              <Radio size={12} />
              {source === "replay"
                ? "RECORDED NUMERICAL RUN"
                : result.mode === "gemini"
                  ? "GEMINI + NUMERICAL TOOLS"
                  : "FRESH NUMERICAL RUN"}
            </span>
            <small>ECI / km · seconds · Δv in m/s</small>
          </div>
        </section>
        {error && (
          <div className="error-banner" role="alert">
            <TriangleAlert size={16} />
            {error}
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {changed && (
          <div className="pending-banner">
            Setup changed. Run the investigation to update the displayed
            results.
          </div>
        )}
        <section className="metrics">
          <div>
            <span>STRESSED COLLISION RISK</span>
            <strong
              className={
                displayedRisk > result.parameters.risk_threshold
                  ? "coral"
                  : "mint"
              }
            >
              {probability(displayedRisk)}
            </strong>
            <small>Worst of 0.5× / 1× / 2× sigma</small>
          </div>
          <div>
            <span>NOMINAL MISS DISTANCE</span>
            <strong>
              {current.miss_distance_m.toFixed(1)} <em>m</em>
            </strong>
            <small>At closest approach · {clock(current.tca_s)}</small>
          </div>
          <div>
            <span>SELECTED MANEUVER</span>
            <strong>
              {result.maneuver?.delta_v_ms.toFixed(3) ?? "0.000"} <em>m/s</em>
            </strong>
            <small>
              {result.maneuver
                ? `Impulse at T+${clock(result.maneuver.burn_time_s)}`
                : "No fuel spent · no burn required"}
            </small>
          </div>
          <div>
            <span>INDEPENDENT VERIFICATION</span>
            <strong className={result.verification.passed ? "mint" : "coral"}>
              {result.verification.passed ? "PASSED" : "BLOCKED"}{" "}
              <ShieldCheck size={19} />
            </strong>
            <small>RK4 + separate probability quadrature</small>
          </div>
        </section>
        <section className="visual-row">
          <div className="panel orbit-panel">
            <div className="panel-heading">
              <span>
                <CircleDot size={13} /> ORBITAL THEATER
              </span>
              <button
                className="icon-button"
                aria-label={cinema ? "Exit cinema view" : "Enter cinema view"}
                onClick={() => setCinema(!cinema)}
              >
                <Expand size={15} />
              </button>
            </div>
            <OrbitScene result={result} time={time} after={after} />
            <div className="scene-label">
              <span className="scene-cross" />
              <strong>EARTH / LEO</strong>
              <small>Two-body simulation · procedural globe</small>
            </div>
            <div className="scene-time">
              <small>MISSION ELAPSED</small>
              <strong>T+{clock(time)}</strong>
            </div>
            <div className="legend">
              <span>
                <i className="mint-dot" />
                SENTINEL / 01
              </span>
              <span>
                <i className="coral-dot" />
                DEBRIS / 17
              </span>
              <span>
                <i className="blue-dot" />
                DEBRIS / 42
              </span>
            </div>
            <div className="view-toggle">
              <button
                className={!after ? "active" : ""}
                onClick={() => setAfter(false)}
              >
                BASELINE
              </button>
              <button
                className={after ? "active" : ""}
                disabled={!result.maneuver}
                onClick={() => setAfter(true)}
              >
                {decision === "approved"
                  ? "ACCEPTED MANEUVER"
                  : "MANEUVER PREVIEW"}
              </button>
            </div>
            <div className="timeline">
              <button
                className="icon-button"
                aria-label={
                  playing ? "Pause orbit animation" : "Play orbit animation"
                }
                onClick={() => setPlaying(!playing)}
              >
                {playing ? <Pause size={15} /> : <Play size={15} />}
              </button>
              <input
                aria-label="Mission time"
                type="range"
                min="0"
                max={result.horizon_s}
                step="1"
                value={time}
                onChange={(event) => {
                  setPlaying(false);
                  setTime(Number(event.target.value));
                }}
              />
              <span>{clock(result.horizon_s)}</span>
              <button
                className="icon-button"
                aria-label="Reset mission time"
                onClick={() => setTime(0)}
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>
          <div className="panel encounter-panel">
            <div className="panel-heading">
              <span>
                <Crosshair size={13} /> ENCOUNTER GEOMETRY
              </span>
              <span className="tiny-tag">
                {after ? "POST-BURN" : "BASELINE"}
              </span>
            </div>
            <EncounterPlot event={current} />
            <div className="encounter-meta">
              <div>
                <small>RELATIVE SPEED</small>
                <strong>{current.relative_speed_kms.toFixed(2)} km/s</strong>
              </div>
              <div>
                <small>COMBINED RADIUS</small>
                <strong>{current.hard_body_radius_m.toFixed(0)} m</strong>
              </div>
            </div>
            <div className="risk-note">
              <TriangleAlert size={14} />
              <span>
                Nominal miss distance alone does not determine risk. Covariance
                changes the conclusion.
              </span>
            </div>
          </div>
        </section>
        <section className="workflow">
          {roles.map((role, index) => {
            const completed = events.some(
              (event) =>
                event.role === role.key &&
                ["evidence", "no_burn"].includes(event.kind),
            );
            const active = running && lastRole === role.key;
            return (
              <div
                key={role.key}
                className={`agent ${active ? "working" : ""} ${completed ? "done" : ""}`}
              >
                <div className="agent-top">
                  <role.icon size={17} />
                  <span>0{index + 1}</span>
                  {active ? (
                    <span className="spinner" />
                  ) : completed ? (
                    <Check size={14} />
                  ) : (
                    <span className="waiting-dot" />
                  )}
                </div>
                <strong>{role.title}</strong>
                <small>{role.description}</small>
                <div className="agent-line" />
              </div>
            );
          })}
        </section>
        <section className="analysis-row">
          <div className="panel analysis-panel">
            <div className="tabs" role="tablist" aria-label="Mission analysis">
              {(["risk", "verification", "assumptions"] as const).map(
                (item) => (
                  <button
                    role="tab"
                    aria-selected={tab === item}
                    key={item}
                    className={tab === item ? "active" : ""}
                    onClick={() => setTab(item)}
                  >
                    {item === "risk" ? "MANEUVER FRONTIER" : item.toUpperCase()}
                  </button>
                ),
              )}
            </div>
            {tab === "risk" ? (
              <>
                <div className="chart-caption">
                  <span>Cost vs. worst stressed risk</span>
                  <small>
                    {result.candidate_search.length} candidates · finite RTN
                    search
                  </small>
                </div>
                <SearchPlot result={result} />
                <div className="comparison-table">
                  <div className="table-head">
                    <span>OBJECT</span>
                    <span>BEFORE / Pc</span>
                    <span>AFTER / Pc</span>
                    <span>MISS / m</span>
                  </div>
                  {result.baseline.map((before) => {
                    const post = result.after.find(
                      (event) => event.object_id === before.object_id,
                    )!;
                    return (
                      <div key={before.object_id}>
                        <span>{before.object_id.toUpperCase()}</span>
                        <span>{probability(before.probability)}</span>
                        <span className="mint">
                          {probability(post.probability)}
                        </span>
                        <span>
                          {before.miss_distance_m.toFixed(0)} →{" "}
                          {post.miss_distance_m.toFixed(0)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : tab === "verification" ? (
              <div className="verification-content">
                <div className="verify-hero">
                  <ShieldCheck size={28} />
                  <strong>
                    {result.verification.passed
                      ? "Two methods. One consistent result."
                      : "Independent verification rejected the result."}
                  </strong>
                </div>
                <p>
                  {result.verification.integrator}
                  <br />
                  {result.verification.probability_method}
                </p>
                <div className="verify-stats">
                  <span>
                    Maximum path disagreement
                    <strong>
                      {result.verification.max_trajectory_disagreement_m.toExponential(
                        2,
                      )}{" "}
                      m
                    </strong>
                  </span>
                  <span>
                    Unforced energy drift
                    <strong>
                      {result.energy_relative_drift.toExponential(2)}
                    </strong>
                  </span>
                  <span>
                    Monte Carlo hits
                    <strong>
                      {result.verification.monte_carlo.hits} /{" "}
                      {result.verification.monte_carlo.samples.toLocaleString()}
                    </strong>
                  </span>
                </div>
                <p className="muted">{result.verification.monte_carlo.note}</p>
                <small>
                  95% Wilson interval: [
                  {result.verification.monte_carlo.wilson_95
                    .map(probability)
                    .join(", ")}
                  ]
                </small>
              </div>
            ) : (
              <div className="assumptions">
                <p>The confidence is conditional on these assumptions.</p>
                {result.assumptions.map((assumption, i) => (
                  <div key={assumption}>
                    <span>0{i + 1}</span>
                    {assumption}
                  </div>
                ))}
                <p className="muted">
                  Numerical agreement tests implementation consistency. It does
                  not validate the physical assumptions.
                </p>
              </div>
            )}
          </div>
          <div className="panel journal-panel">
            <div className="panel-heading">
              <span>
                <Terminal size={13} /> AGENT JOURNAL
              </span>
              <span className="tiny-tag">{events.length} EVENTS</span>
            </div>
            <div className="journal" ref={journalRef} aria-live="polite">
              {events.map((event, i) => (
                <div
                  className={`journal-event ${event.kind === "error" ? "failed" : ""}`}
                  key={i}
                >
                  <span className="event-number">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <small>
                      {event.role.replaceAll("_", " ").toUpperCase()}
                    </small>
                    <p>{describe(event)}</p>
                  </div>
                  <span className="event-dot" />
                </div>
              ))}
            </div>
          </div>
        </section>
        {result.ai_review && (
          <section className="panel ai-review">
            <Sparkles size={18} />
            <div>
              <strong>GEMINI REVIEW / ADVISORY</strong>
              <p>{result.ai_review.summary}</p>
              <small>
                Evidence: {result.ai_review.evidence_ids.join(" · ")}
              </small>
            </div>
          </section>
        )}
        <section
          className={`decision-panel ${decision === "blocked" ? "blocked" : ""}`}
        >
          <div className="decision-icon">
            {decision === "blocked" ? (
              <TriangleAlert size={27} />
            ) : (
              <ShieldCheck size={27} />
            )}
          </div>
          <div>
            <span className="eyebrow">HUMAN APPROVAL GATE</span>
            <h3>
              {running
                ? "Investigation in progress"
                : decision === "approved"
                  ? "Simulated maneuver accepted"
                  : decision === "no_burn"
                    ? "Stand down. Preserve propellant."
                    : decision === "blocked"
                      ? "Hold. No verified maneuver available."
                      : "Verified candidate. Your decision."}
            </h3>
            <p>
              {decision === "approval_pending"
                ? "The verifier passed. Review the evidence before accepting the maneuver preview."
                : "Simulation only. This system never transmits spacecraft commands."}
            </p>
          </div>
          <div className="decision-actions">
            <button
              className="secondary"
              disabled={running || !!error}
              onClick={() =>
                downloadReport({ result, events, status: decision, source })
              }
            >
              <ArrowDownToLine size={15} /> REPORT
            </button>
            {decision === "approval_pending" && (
              <button
                className="primary"
                disabled={running || !result.verification.passed}
                onClick={() => setConfirm(true)}
              >
                REVIEW & APPROVE <ArrowRight size={15} />
              </button>
            )}
          </div>
        </section>
        <footer>
          <span>
            <Layers size={13} /> MODEL-BOUND EVIDENCE. HUMAN-OWNED DECISIONS.
          </span>
          <span>
            40-MINUTE HORIZON / SYNTHETIC COVARIANCE / NO LIVE COMMANDS
          </span>
        </footer>
      </main>
      {confirm && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="approval-title"
          >
            <button
              className="close-modal"
              aria-label="Close approval dialog"
              onClick={() => setConfirm(false)}
            >
              <X size={18} />
            </button>
            <ShieldCheck size={36} />
            <span className="eyebrow">SIMULATION AUTHORIZATION</span>
            <h2 id="approval-title">Accept this maneuver?</h2>
            <p>
              You are accepting a simulated trajectory change. No spacecraft
              command will be generated or transmitted.
            </p>
            <div className="approval-summary">
              <span>
                Delta-v
                <strong>{result.maneuver!.delta_v_ms.toFixed(3)} m/s</strong>
              </span>
              <span>
                Burn time
                <strong>T+{clock(result.maneuver!.burn_time_s)}</strong>
              </span>
              <span>
                Worst stressed Pc
                <strong>
                  {probability(result.maneuver!.worst_stress_probability)}
                </strong>
              </span>
            </div>
            <p className="muted">
              Only the listed synthetic objects and declared model assumptions
              have been checked.
            </p>
            <button
              className="primary"
              autoFocus
              disabled={approving}
              onClick={approve}
            >
              {approving ? "ACCEPTING…" : "ACCEPT SIMULATED MANEUVER"}
              <Check size={16} />
            </button>
            <button
              className="secondary"
              disabled={approving}
              onClick={() => setConfirm(false)}
            >
              KEEP UNDER REVIEW
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
