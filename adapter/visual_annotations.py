"""Read hash-bound retrospective notes without changing recorded trial outcomes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _file(directory: Path, relative: str) -> Path:
    path = directory / relative
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("annotation path leaves trial")
    current = path
    while current != directory:
        if current.is_symlink():
            raise ValueError("annotation path contains symlink")
        current = current.parent
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("annotation file missing or too large")
    return path


def _hash(directory: Path, relative: str) -> str:
    with _file(directory, relative).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def trial_annotations(directory: Path) -> dict:
    """Verify stored evidence, not the current live game or save directory."""
    directory = directory.resolve()
    result = {"adjudication": None, "operator_recovery": None, "annotation_issues": []}
    for kind, relative, contract in (
        ("adjudication", "adjudication/receipt.json", "challenge-adjudication-v1"),
        ("operator_recovery", "operator-recovery/receipt.json", "operator-recovery-v1"),
    ):
        if not (directory / relative).exists():
            continue
        try:
            path = _file(directory, relative)
            if path.stat().st_size > 1024 * 1024:
                raise ValueError("annotation receipt too large")
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(receipt, dict) or receipt.get("contract") != contract:
                raise ValueError("unknown annotation contract")
            bindings = receipt.get("source_sha256" if kind == "adjudication" else "raw_artifact_sha256")
            allowed = {"trajectory.jsonl", "run.json", "validation.json", "visual-report.json",
                       "fixture-driver.py", "actor-start.json", "initial-fixture-capture.json"}
            if (not isinstance(bindings, dict) or not {"run.json", "trajectory.jsonl"} <= bindings.keys()
                    or not bindings.keys() <= allowed):
                raise ValueError("missing or unexpected evidence bindings")
            if any(_hash(directory, name) != digest for name, digest in bindings.items()):
                raise ValueError("recorded artifacts differ from annotation")
            texts = ("summary", "scope") if kind == "adjudication" else (
                "recovered_at", "initiator", "reason", "mechanism", "scope")
            booleans = ("written_task_satisfied", "recorded_outcome_kept", "model_observation_error") if kind == "adjudication" else (
                "automatic_cleanup_completed", "manual_recovery_verified", "raw_lifecycle_unchanged")
            if (any(key in receipt and not isinstance(receipt[key], str) for key in texts)
                    or any(key in receipt and type(receipt[key]) is not bool for key in booleans)):
                raise ValueError("invalid annotation field types")
            if kind == "adjudication":
                if receipt.get("recorded_outcome_kept") is not True:
                    raise ValueError("adjudication does not preserve recorded result")
                for prefix in ("evidence", "report"):
                    name = receipt.get(prefix + "_file")
                    if (not isinstance(name, str) or Path(name).name != name
                            or _hash(directory, "adjudication/" + name) != receipt.get(prefix + "_sha256")):
                        raise ValueError("adjudication supporting artifact differs")
                result[kind] = {key: receipt.get(key) for key in (
                    "summary", "scope", "written_task_satisfied", "recorded_outcome_kept", "model_observation_error")}
            else:
                restoration = json.loads(_file(directory, "save-backup/restoration.json").read_text(encoding="utf-8"))
                checks = receipt.get("baseline_checks")
                restored = restoration.get("files", {})
                if (receipt.get("manual_recovery_verified") is not True
                        or type(receipt.get("original_save_count")) is not int
                        or receipt["original_save_count"] < 1
                        or receipt.get("raw_lifecycle_unchanged") is not True
                        or receipt.get("no_game_process") is not True
                        or _hash(directory, "save-backup/restoration.json") != receipt.get("restoration_receipt_sha256")
                        or restoration.get("verified") is not True or not restored
                        or any(v is not True for v in restored.values())
                        or len(restored) != receipt.get("original_save_count")
                        or not isinstance(checks, dict) or not checks or any(v is not True for v in checks.values())):
                    raise ValueError("manual recovery evidence is incomplete")
                result[kind] = {key: receipt.get(key) for key in (
                    "recovered_at", "initiator", "reason", "mechanism", "automatic_cleanup_completed",
                    "manual_recovery_verified", "raw_lifecycle_unchanged", "original_save_count", "scope")}
        except (OSError, ValueError, TypeError, AttributeError) as error:
            result["annotation_issues"].append(kind + ": " + str(error))
    return result
