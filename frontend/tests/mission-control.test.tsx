// @vitest-environment jsdom
import React from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import App from "../src/App";

vi.mock("../src/OrbitScene", () => ({
  default: () => <div>Mocked WebGL renderer</div>,
}));
const recordings = Object.fromEntries(
  ["crossing", "uncertain", "clear"].map((id) => [
    id,
    JSON.parse(readFileSync(`public/demo/${id}.json`, "utf8")),
  ]),
);

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input === "/api/health") return { ok: false };
      const id = input.split("/").at(-1)!.replace(".json", "");
      return { ok: true, json: async () => recordings[id] };
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function playRecording() {
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: /PLAY RECORDED MISSION/ }),
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    vi.advanceTimersByTime(10_000);
  });
}

describe("recorded mission control", () => {
  it("finishes a replay without shifting or losing the final event", async () => {
    render(<App />);
    await screen.findByText("Verified candidate. Your decision.");
    await playRecording();
    expect(screen.getByText("Mission decision: approval pending")).toBeTruthy();
    expect(screen.getByText("Evidence recorded: baseline")).toBeTruthy();
    expect(screen.getByText("Verified candidate. Your decision.")).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: /PLAY RECORDED MISSION/ })
        .hasAttribute("disabled"),
    ).toBe(false);
  });

  it("selects the quiet recording and offers no maneuver approval", async () => {
    render(<App />);
    await screen.findByText("Verified candidate. Your decision.");
    fireEvent.click(screen.getByRole("button", { name: /Quiet orbit/ }));
    await playRecording();
    expect(screen.getByText("Stand down. Preserve propellant.")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /REVIEW & APPROVE/ }),
    ).toBeNull();
    expect(screen.getByText("Mission decision: no burn")).toBeTruthy();
  });

  it("requires an explicit simulation authorization before accepting a maneuver", async () => {
    render(<App />);
    await screen.findByText("Verified candidate. Your decision.");
    fireEvent.click(screen.getByRole("button", { name: /REVIEW & APPROVE/ }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.queryByText("Simulated maneuver accepted")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: /ACCEPT SIMULATED MANEUVER/ }),
    );
    await screen.findByText("Simulated maneuver accepted");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some((call) => String(call[0]).includes("/approve")),
    ).toBe(false);
  });
  it("keeps recorded provenance after a failed fresh computation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => {
        if (input === "/api/health")
          return { ok: true, json: async () => ({ gemini_configured: false }) };
        if (input === "/api/missions")
          return {
            ok: false,
            json: async () => ({ detail: "Capacity reached." }),
          };
        return { ok: true, json: async () => recordings.crossing };
      }),
    );
    render(<App />);
    await screen.findByRole("button", { name: /RUN INVESTIGATION/ });
    await screen.findByText("Verified candidate. Your decision.");
    fireEvent.click(screen.getByRole("button", { name: /RUN INVESTIGATION/ }));
    await screen.findByRole("alert");
    expect(screen.getByText("RECORDED NUMERICAL RUN")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /REVIEW & APPROVE/ }),
    ).toBeNull();
  });
});
