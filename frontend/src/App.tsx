import { useCallback, useEffect, useMemo, useState } from "react";
import type { InvestigationState, ScenarioSummary } from "./types";

const API = "";
const sessionToken = sessionStorage.getItem("incident-session") ?? crypto.randomUUID();
sessionStorage.setItem("incident-session", sessionToken);
async function api(path: string, options: RequestInit = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 150000);
  try {
    const response = await fetch(API + path, {...options, signal: controller.signal,
      headers: {...options.headers, "X-Session-Token": sessionToken}});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "Request rejected");
    return value;
  } finally { clearTimeout(timeout); }
}

function confidenceBar(value: number, tone: "rose" | "emerald" | "amber") {
  const color =
    tone === "rose" ? "bg-rose-500" : tone === "emerald" ? "bg-emerald-500" : "bg-amber-400";
  return (
    <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
      <div className={`h-full ${color} transition-all duration-700`} style={{ width: `${value * 100}%` }} />
    </div>
  );
}

export default function App() {
  const [scenario, setScenario] = useState<ScenarioSummary | null>(null);
  const [state, setState] = useState<InvestigationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publicConfig, setPublicConfig] = useState<{ gemini_configured: boolean; allow_public_live: boolean } | null>(
    null,
  );
  const [operatorSecret, setOperatorSecret] = useState("");
  const [approving, setApproving] = useState(false);
  const [guidedStep, setGuidedStep] = useState(0);
  const guidedDemo = true;

  useEffect(() => {
    Promise.all([api("/api/scenarios"), api("/api/config/public")])
      .then(([list, config]) => {setScenario(list[0] ?? null); setPublicConfig(config);})
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load dashboard"));
  }, []);

  const run = useCallback(async (mode: "replay" | "live") => {
    if (!scenario) return;
    setLoading(true);
    setError(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const secret = operatorSecret;
      if (secret) headers["X-Demo-Secret"] = secret;
      const data: InvestigationState = await api("/api/investigations", {
        method: "POST", headers,
        body: JSON.stringify({ scenario_id: scenario.scenario_id, mode }),
      });
      setState(data);
      setGuidedStep(0);
      if (mode === "replay" && guidedDemo) {
        const steps = data.events.length || 6;
        for (let i = 1; i <= steps; i += 1) {
          await new Promise((r) => setTimeout(r, 900));
          setGuidedStep(i);
        }
      } else {
        setGuidedStep(999);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, [scenario, operatorSecret]);

  const approveRemediation = async () => {
    if (!state?.remediation) return;
    setApproving(true);
    try {
      setState(await api("/api/remediation/approve", {method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({investigation_id:state.investigation_id,approved:true})}));
    } catch (e) {setError(e instanceof Error ? e.message : "Approval failed");}
    finally {setApproving(false);}

  };

  const initialHyp = state?.hypotheses[0];
  const skepticHyp = state?.hypotheses[1];
  const experiment = state?.experiments[0];

  const timeline = useMemo(() => state?.events ?? [], [state]);

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_#27272a_0%,_#09090b_55%)]">
      <header className="border-b border-zinc-800/80 backdrop-blur sticky top-0 z-10 bg-zinc-950/70">
        <div className="max-w-6xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-amber-400/90 mono">Incident response</p>
            <h1 className="text-2xl font-semibold tracking-tight">INCIDENT ZERO</h1>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => run("replay")}
              disabled={loading || !scenario}
              className="px-4 py-2 rounded-lg bg-amber-500 text-zinc-950 font-medium hover:bg-amber-400 disabled:opacity-50"
            >
              Run replay demo
            </button>
            <button
              type="button"
              onClick={() => run("live")}
              disabled={loading || !scenario || !publicConfig?.gemini_configured || (!publicConfig.allow_public_live && !operatorSecret)}
              className="px-4 py-2 rounded-lg border border-zinc-600 hover:border-zinc-400 disabled:opacity-50"
              title={publicConfig?.allow_public_live ? "Live LLM investigation" : "Requires server DEMO_SECRET / ALLOW_PUBLIC_LIVE"}
            >
              Live investigation
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 pt-4 text-sm text-zinc-400">
        <p>SIMULATION ENVIRONMENT · Replay is an illustrative scripted trace · Confidence scores are heuristic estimates.</p>
        {publicConfig?.gemini_configured && !publicConfig.allow_public_live && <input aria-label="Operator access secret" type="password" autoComplete="off" placeholder="Operator access secret" value={operatorSecret} onChange={e => setOperatorSecret(e.target.value)} className="mt-3 bg-zinc-900 border border-zinc-700 rounded px-3 py-2" />}
      </div>
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {scenario && (
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
            <h2 className="text-lg font-semibold mb-1">{scenario.title}</h2>
            <p className="text-zinc-400 text-sm mb-3">{scenario.public_summary}</p>
            <p className="mono text-sm text-rose-300/90 bg-zinc-950/60 rounded-lg px-4 py-3 border border-rose-900/40">
              {scenario.alert_text}
            </p>
          </section>
        )}

        {error && (
          <div className="rounded-xl border border-rose-800 bg-rose-950/30 px-4 py-3 text-rose-200 text-sm">{error}</div>
        )}

        {loading && <p className="text-zinc-400 animate-pulse">Running investigation pipeline…</p>}

        {state && <div className="flex gap-3 text-sm">
          <button className="border border-zinc-700 rounded px-3 py-2" onClick={() => {setState(null); setGuidedStep(0);}}>Reset view</button>
          <button className="border border-zinc-700 rounded px-3 py-2" onClick={() => {
            const text = `# INCIDENT ZERO — Simulation postmortem\n\nMode: ${state.replay ? "Illustrative replay" : "Live AI on synthetic telemetry"}\n\n## Verdict\n${state.verdict?.leading_hypothesis ?? "Undetermined"}\n\n${state.verdict?.explanation ?? "Investigation incomplete"}\n\n## Evidence\n${state.verdict?.evidence_ids.join(", ") ?? "None"}\n\n## Timeline\n${state.events.map(e => `- ${e.phase}: ${e.message}`).join("\n")}\n\n## Limitations\nSynthetic telemetry; simulations test explicit assumptions and do not establish real-world causality. Confidence is heuristic.\n\n## Artifacts\n\n\`\`\`json\n${JSON.stringify(state, null, 2)}\n\`\`\`\n`;
            const url = URL.createObjectURL(new Blob([text], {type:"text/markdown"}));
            const a = document.createElement("a"); a.href=url; a.download=`incident-${state.investigation_id}.md`; a.click(); URL.revokeObjectURL(url);
          }}>Download postmortem</button>
        </div>}
        {state && (
          <>
            {guidedDemo && guidedStep < 999 && (
              <p className="text-center text-sm text-amber-300/90 animate-pulse">
                Guided demo · step {Math.min(guidedStep, state.events.length)} / {state.events.length}
              </p>
            )}
            <section className="grid lg:grid-cols-2 gap-6">
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold">Hypothesis Battle</h3>
                  <span className="text-xs mono text-zinc-500">{state.replay ? "REPLAY" : "LIVE"}</span>
                </div>
                {initialHyp && guidedStep >= 1 && (
                  <div className="mb-6">
                    <p className="text-sm text-zinc-400 mb-1">Initial read</p>
                    <p className="font-medium">{initialHyp.hypothesis}</p>
                    <div className="mt-2">{confidenceBar(initialHyp.posterior_confidence, "amber")}</div>
                    <p className="text-xs text-zinc-500 mt-1">{Math.round(initialHyp.posterior_confidence * 100)}% confidence</p>
                  </div>
                )}
                {skepticHyp && guidedStep >= 2 && (
                  <div>
                    <p className="text-sm text-zinc-400 mb-1">After Skeptic (evidence-weighted)</p>
                    <p className="font-medium">{skepticHyp.hypothesis}</p>
                    <div className="mt-2">{confidenceBar(skepticHyp.posterior_confidence, "rose")}</div>
                    <p className="text-xs text-zinc-500 mt-1">{Math.round(skepticHyp.posterior_confidence * 100)}% confidence</p>
                    <p className="text-sm text-zinc-300 mt-3 leading-relaxed">{skepticHyp.rationale}</p>
                    {skepticHyp.contradicting_evidence_ids.length > 0 && (
                      <p className="mono text-xs text-rose-300/80 mt-2">
                        Contradictions: {skepticHyp.contradicting_evidence_ids.join(", ")}
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
                <h3 className="text-base font-semibold mb-4">Counterfactual Lab</h3>
                {experiment && guidedStep >= 3 ? (
                  <>
                    <p className="text-sm text-zinc-400 mb-2">Deterministic Python simulation</p>
                    <p className="text-sm mb-3">{experiment.summary}</p>
                    <pre className="mono text-xs bg-zinc-950 rounded-lg p-4 border border-zinc-800 overflow-x-auto text-emerald-200/90">
                      {experiment.stdout}
                    </pre>
                    <p className="mono text-xs text-zinc-500 mt-2">experiment_id: {experiment.experiment_id}</p>
                  </>
                ) : (
                  <p className="text-zinc-500 text-sm">No experiment yet.</p>
                )}
              </div>
            </section>

            {guidedStep >= 1 && (
            <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
              <h3 className="text-base font-semibold mb-4">Evidence (tool outputs)</h3>
              <div className="space-y-3">
                {state.tool_calls.map((t) => (
                  <details key={t.evidence_id} className="rounded-lg border border-zinc-800 bg-zinc-950/50 px-4 py-3">
                    <summary className="cursor-pointer mono text-sm">
                      {t.evidence_id} · {t.tool_name}
                    </summary>
                    <pre className="mono text-xs mt-3 overflow-x-auto text-zinc-400">
                      {JSON.stringify(t.output, null, 2)}
                    </pre>
                  </details>
                ))}
              </div>
            </section>
            )}

            {state.verdict && guidedStep >= 4 && (
              <section className="rounded-2xl border border-emerald-900/50 bg-emerald-950/20 p-6">
                <h3 className="text-base font-semibold text-emerald-200 mb-2">Judge verdict</h3>
                <p className="text-lg font-medium">{state.verdict.leading_hypothesis}</p>
                <p className="text-sm text-zinc-300 mt-2 leading-relaxed">{state.verdict.explanation}</p>
                <p className="mono text-xs text-zinc-500 mt-3">
                  confidence {Math.round(state.verdict.confidence * 100)}% · cites {state.verdict.evidence_ids.join(", ")}
                </p>
              </section>
            )}

            {state.remediation && guidedStep >= 5 && (
              <section className="rounded-2xl border border-zinc-800 p-6 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="font-semibold">Simulated remediation</h3>
                  <p className="text-sm text-zinc-400 mt-1">{state.remediation.action}</p>
                  {state.remediation.executed && <pre className="text-xs mt-2">{JSON.stringify(state.remediation.recovery, null, 2)}</pre>}
                  <p className="text-xs text-zinc-500 mt-2">
                    {state.remediation.executed
                      ? "Executed after approval"
                      : "Blocked until you explicitly approve"}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={state.remediation.executed || approving}
                  onClick={approveRemediation}
                  className="px-4 py-2 rounded-lg bg-zinc-100 text-zinc-900 font-medium disabled:opacity-40"
                >
                  Approve simulation
                </button>
              </section>
            )}

            <section className="rounded-xl border border-zinc-800/80 p-4">
              <h3 className="text-sm font-semibold text-zinc-400 mb-2">Timeline</h3>
              <ul className="space-y-1 text-sm">
                {timeline.map((ev, i) => (
                  <li key={`${ev.phase}-${i}`} className="flex gap-3">
                    <span className="mono text-xs text-amber-400/80 w-24 shrink-0">{ev.phase}</span>
                    <span className="text-zinc-300">{ev.message}</span>
                  </li>
                ))}
              </ul>
              <p className="mono text-xs text-zinc-600 mt-3">
                budget: {state.budget.tool_calls} tools · {state.budget.llm_rounds} llm rounds · {state.budget.elapsed_seconds}s
              </p>
            </section>
          </>
        )}

        {!state && !loading && (
          <p className="text-zinc-500 text-center py-16">
            Start with <span className="text-amber-400">Run replay demo</span> — no API key, illustrative example trace.
          </p>
        )}
      </main>
    </div>
  );
}
