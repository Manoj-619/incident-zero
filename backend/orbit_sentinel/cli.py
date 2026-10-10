"""Headless reproducible mission runner: python -m orbit_sentinel.cli."""

import argparse
import json
from pathlib import Path

from .agents.workflow import run_mission
from .models import MissionRequest


def main():
    parser = argparse.ArgumentParser(description="Run a synthetic ORBIT SENTINEL mission")
    parser.add_argument(
        "--scenario", choices=["crossing", "uncertain", "clear"], default="crossing"
    )
    parser.add_argument("--mode", choices=["numerical", "gemini"], default="numerical")
    parser.add_argument("--output", type=Path, default=Path("mission.json"))
    args = parser.parse_args()
    events = []

    def record(role, kind, payload):
        events.append({"sequence": len(events) + 1, "role": role, "kind": kind, "payload": payload})
        print(f"[{role}] {kind}")

    result = run_mission(MissionRequest(scenario=args.scenario, mode=args.mode), record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"result": result, "events": events}, indent=2, allow_nan=False) + "\n"
    )
    print(f"{result['decision']} | {args.output}")


if __name__ == "__main__":
    main()
