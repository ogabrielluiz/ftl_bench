"""Try a typed API on one explicit PNG without opening FTL or sending game input."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from visual_agent import VisualObservation, read_screenshot
from visual_choice_agent import DEFAULT_MODELS, TypedVisualAgent, write_exclusive
from visual_decision_audit import audit_decision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=tuple(DEFAULT_MODELS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", default="Play this FTL run to victory.")
    args = parser.parse_args(argv)
    image_bytes, identity = read_screenshot(args.image)
    directory = args.output.resolve()
    agent = TypedVisualAgent(args.backend, args.model, audit_root=directory / "api-decisions", task=args.task)
    agent.require_credentials()
    directory.mkdir(parents=True, exist_ok=False)
    image_path = directory / "input.png"
    image_path.write_bytes(image_bytes)
    result = {"scope": "One archived screenshot; no FTL launch or game input", "model_comparison": False,
              "backend": args.backend, "model": agent.model, "image": identity}
    try:
        decision = agent.decide(VisualObservation(image_path, "offline-probe", expected_image_sha256=identity["sha256"]))
        result["decision"] = decision.as_dict()
        result["metadata"] = decision.metadata
        result["audit"] = audit_decision(directory / decision.metadata["artifact"])
        if not result["audit"]["valid"]:
            raise RuntimeError("Saved API decision did not pass replay verification")
        result["status"] = "completed"
    except BaseException as error:
        result.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        write_exclusive(directory / "probe.json", result)
    print(json.dumps({"status": result["status"], "backend": args.backend, "model": agent.model,
                      "decision": result["decision"], "output": str(directory), "audit_valid": True}))


if __name__ == "__main__":
    main()
