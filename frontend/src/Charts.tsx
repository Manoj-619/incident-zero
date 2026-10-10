import type { Encounter, Result } from "./types";
export const probability = (p: number) =>
  p === 0 ? "below precision" : p.toExponential(2);
export const clock = (s: number) =>
  `${Math.floor(s / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(s % 60)
    .toString()
    .padStart(2, "0")}`;
export function EncounterPlot({ event }: { event: Encounter }) {
  const scale = Math.max(
    120,
    ...event.ellipse_3sigma_m.map((v) => v * 1.2),
    ...event.mean_plane_m.map((v) => Math.abs(v) * 1.15),
  );
  const factor = 110 / scale;
  const x = 160 + event.mean_plane_m[0] * factor,
    y = 135 - event.mean_plane_m[1] * factor;
  return (
    <svg
      viewBox="0 0 320 260"
      className="encounter-plot"
      role="img"
      aria-label="Projected encounter covariance at closest approach"
    >
      <defs>
        <radialGradient id="cloud">
          <stop stopColor="#ff866e" stopOpacity=".22" />
          <stop offset="1" stopColor="#ff866e" stopOpacity=".025" />
        </radialGradient>
      </defs>
      {[50, 85, 120, 155, 190, 225, 260].map((v) => (
        <line key={"x" + v} x1={v} y1="20" x2={v} y2="235" stroke="#1a2b38" />
      ))}
      {[30, 65, 100, 135, 170, 205, 240].map((v) => (
        <line key={"y" + v} x1="30" y1={v} x2="290" y2={v} stroke="#1a2b38" />
      ))}
      <line
        x1="30"
        y1="135"
        x2="290"
        y2="135"
        stroke="#476073"
        strokeDasharray="3 5"
      />
      <line
        x1="160"
        y1="20"
        x2="160"
        y2="235"
        stroke="#476073"
        strokeDasharray="3 5"
      />
      <g
        transform={`translate(${x},${y}) rotate(${(-event.ellipse_rotation_rad * 180) / Math.PI})`}
      >
        <ellipse
          rx={event.ellipse_3sigma_m[0] * factor}
          ry={event.ellipse_3sigma_m[1] * factor}
          fill="url(#cloud)"
          stroke="#ff826e"
          strokeOpacity=".5"
        />
        <ellipse
          rx={(event.ellipse_3sigma_m[0] * factor) / 3}
          ry={(event.ellipse_3sigma_m[1] * factor) / 3}
          fill="none"
          stroke="#ff826e"
          strokeDasharray="3 4"
          strokeOpacity=".6"
        />
      </g>
      <circle
        cx="160"
        cy="135"
        r={Math.max(2, event.hard_body_radius_m * factor)}
        fill="#58e5cb"
        fillOpacity=".3"
        stroke="#58e5cb"
      />
      <path d={`M ${x - 4} ${y} h 8 M ${x} ${y - 4} v 8`} stroke="#ff826e" />
      <text x="30" y="253" fill="#819bad" fontSize="9" fontFamily="monospace">
        ±{scale.toFixed(0)} m · 3σ ellipse · encounter plane
      </text>
    </svg>
  );
}
export function SearchPlot({ result }: { result: Result }) {
  const candidates = result.candidate_search;
  const threshold = result.parameters.risk_threshold;
  const minLog = -12,
    maxLog = -1;
  const y = (p: number) =>
    160 -
    ((Math.max(minLog, Math.min(maxLog, Math.log10(Math.max(p, 1e-12)))) -
      minLog) /
      (maxLog - minLog)) *
      135;
  return (
    <svg
      viewBox="0 0 480 190"
      role="img"
      aria-label="Maneuver search: fuel cost against worst stressed collision probability"
    >
      {[-2, -4, -6, -8, -10, -12].map((exponent) => (
        <g key={exponent}>
          <line
            x1="48"
            x2="465"
            y1={y(10 ** exponent)}
            y2={y(10 ** exponent)}
            stroke="#192a36"
          />
          <text x="9" y={y(10 ** exponent) + 3} fill="#8095a7" fontSize="9">
            10^{exponent}
          </text>
        </g>
      ))}
      <line
        x1="48"
        x2="465"
        y1={y(threshold)}
        y2={y(threshold)}
        stroke="#ffb55d"
        strokeDasharray="4 5"
      />
      <text x="350" y={y(threshold) - 5} fill="#ffb55d" fontSize="9">
        ACCEPTANCE LIMIT
      </text>
      {candidates.map((candidate, i) => (
        <circle
          key={i}
          cx={
            48 + (candidate.delta_v_ms / result.parameters.max_delta_v_ms) * 410
          }
          cy={y(candidate.worst_probability)}
          r="2.4"
          fill={candidate.feasible ? "#58e5cb" : "#ff826e"}
          opacity=".55"
        />
      ))}
      {result.maneuver && (
        <circle
          cx={
            48 +
            (result.maneuver.delta_v_ms / result.parameters.max_delta_v_ms) *
              410
          }
          cy={y(result.maneuver.worst_stress_probability)}
          r="6"
          fill="none"
          stroke="#fff"
          strokeWidth="1.5"
        />
      )}
      <text x="48" y="185" fill="#819bad" fontSize="9">
        0 m/s
      </text>
      <text x="380" y="185" fill="#819bad" fontSize="9">
        {result.parameters.max_delta_v_ms.toFixed(2)} m/s Δv
      </text>
      {!candidates.length && (
        <text x="140" y="90" fill="#58e5cb" fontSize="12">
          NO MANEUVER SEARCH REQUIRED
        </text>
      )}
    </svg>
  );
}
