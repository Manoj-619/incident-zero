import type { Event, Result, ScenarioId } from "./types";
const TOKEN_KEY = "orbit-sentinel-capability";
export function token(): string {
  let value = sessionStorage.getItem(TOKEN_KEY);
  if (!value) {
    value = crypto.randomUUID() + crypto.randomUUID();
    sessionStorage.setItem(TOKEN_KEY, value);
  }
  return value;
}
async function request(
  path: string,
  options: RequestInit = {},
  operator?: string,
) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": token(),
      ...(operator ? { "X-Operator-Secret": operator } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Request failed." }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Invalid mission parameters.",
    );
  }
  return response;
}
export async function startMission(
  scenario: ScenarioId,
  mode: string,
  budget: number,
  threshold: number,
  operator: string,
) {
  return (
    await request(
      "/missions",
      {
        method: "POST",
        body: JSON.stringify({
          scenario,
          mode,
          max_delta_v_ms: budget,
          risk_threshold: threshold,
          seed: 42,
        }),
      },
      operator,
    )
  ).json() as Promise<{ id: string }>;
}
export async function getMission(id: string) {
  return (await request("/missions/" + id)).json() as Promise<{
    status: string;
    error: string | null;
    result: Result | null;
  }>;
}
export async function approveMission(id: string) {
  return (
    await request("/missions/" + id + "/approve", { method: "POST" })
  ).json();
}
export async function eventStream(
  id: string,
  onEvent: (event: Event) => void,
  signal: AbortSignal,
) {
  const response = await request("/missions/" + id + "/events", { signal });
  const reader = response.body!.getReader();
  let buffer = "";
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = chunk
          .split("\n")
          .find((line) => line.startsWith("data: "));
        if (chunk.includes("event: mission") && data)
          onEvent(JSON.parse(data.slice(6)));
      }
    }
  } finally {
    reader.releaseLock();
  }
}
export function downloadReport(data: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "orbit-sentinel-report.json";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
