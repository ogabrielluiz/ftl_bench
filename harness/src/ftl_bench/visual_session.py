"""Paused, render-synchronized visual transport. Native observations stay evaluator-side."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Any

from .observation import Observation
from .session import AgentSession

VISUAL_CLOCK_VERSION = 2
FIXED_STEP_NUMERATOR = 1
FIXED_STEP_DENOMINATOR = 60
_CLOCK_FIELDS = ("visual_clock_version", "world_updates", "fixed_step_numerator",
                 "fixed_step_denominator", "simulated_updates")
_CAPTURE_FIELDS = ("capture_id", "frame_id", "path", "width", "height", "action_seq",
                   "paused", "visual_io_version", "coordinate_space",
                   "external_input_generation", "external_input_detected",
                   *_CLOCK_FIELDS)


class VisualTransportError(RuntimeError):
    pass


def validate_visual_clock(obs: Observation, *, require_snapshot: bool = True,
                          synchronized: bool = False) -> str:
    """Require the fixed-step native clock; return captured cumulative updates.

    Clock v1 gated update count but did not fix engine time per update. It is not
    admitted to new runs or silently treated as a 60 Hz simulation.
    """
    capabilities = (obs.raw or {}).get("capabilities") or {}
    if (not isinstance(capabilities, dict)
            or type(capabilities.get("visual_clock_version")) is not int
            or capabilities.get("visual_clock_version") != VISUAL_CLOCK_VERSION):
        raise VisualTransportError("Native visual clock version 2 capability is required")

    def counter(value):
        if (not isinstance(value, str) or not value or not value.isascii()
                or not value.isdecimal()):
            raise VisualTransportError("Native world-update counter is missing or malformed")
        return value

    def fixed_step(metadata, updates):
        if (type(metadata.get("fixed_step_numerator")) is not int
                or metadata["fixed_step_numerator"] != FIXED_STEP_NUMERATOR
                or type(metadata.get("fixed_step_denominator")) is not int
                or metadata["fixed_step_denominator"] != FIXED_STEP_DENOMINATOR):
            raise VisualTransportError("Native fixed simulation step must be 1/60 second")
        simulated = counter(metadata.get("simulated_updates"))
        if simulated != updates:
            raise VisualTransportError("Native simulated-update counter disagrees with world updates")

    live_updates = counter(capabilities.get("world_updates"))
    fixed_step(capabilities, live_updates)
    visual = (obs.raw or {}).get("visual")
    if not visual and not require_snapshot:
        return live_updates
    if (not isinstance(visual, dict) or type(visual.get("visual_clock_version")) is not int
            or visual.get("visual_clock_version") != VISUAL_CLOCK_VERSION):
        raise VisualTransportError("Native visual clock version 2 snapshot is required")
    captured_updates = counter(visual.get("world_updates"))
    fixed_step(visual, captured_updates)
    if synchronized and live_updates != captured_updates:
        raise VisualTransportError("World updated beyond the paused screenshot")
    return captured_updates


class ExternalInputInterference(VisualTransportError):
    """The actor no longer has exclusive control; the trial must end."""

    def __init__(self, observation: Observation, *, expected_generation: str | None = None,
                 dispatched: bool = False):
        super().__init__("External game input was detected; the visual trial cannot continue")
        self.observation = observation
        self.dispatched = dispatched
        visual = (observation.raw or {}).get("visual") or {}
        self.evidence = {"reason": "external_input_since_capture",
                         "expected_generation": expected_generation,
                         "observed_generation": visual.get("external_input_generation"),
                         "external_input_detected": visual.get("external_input_detected"),
                         "packet_dispatched": dispatched, "action_seq": observation.last_action_seq}


@dataclass(frozen=True)
class VisualFrame:
    observation: Observation
    image_path: Path
    reference: dict[str, Any]
    capture_id: Any


class VisualSession:
    """Single-writer transport with exact screenshot identity and no input retries."""

    def __init__(self, session: AgentSession, run_directory: Path):
        self.session = session
        self.root = Path(run_directory).resolve()
        self.screens = self.root / "screens"
        self.screens.mkdir(parents=True, exist_ok=True)
        self.ordinal = 0

    @staticmethod
    def _visual(obs: Observation) -> dict:
        visual = (obs.raw or {}).get("visual")
        return visual if isinstance(visual, dict) else {}

    @classmethod
    def _check_external_input(cls, obs: Observation, *, require_snapshot: bool = True,
                              expected_generation: str | None = None, dispatched: bool = False) -> str | None:
        visual = cls._visual(obs)
        detected = visual.get("external_input_detected")
        generation = visual.get("external_input_generation")
        if detected is True or (expected_generation is not None and generation is not None
                                and generation != expected_generation):
            raise ExternalInputInterference(obs, expected_generation=expected_generation, dispatched=dispatched)
        capabilities = (obs.raw or {}).get("capabilities") or {}
        if not isinstance(capabilities, dict) or capabilities.get("external_input_guard") is not True:
            raise VisualTransportError("Native external-input guard capability is required")
        if generation is None and detected is None and not require_snapshot:
            # Before the first visual capture, there need not be a visual snapshot.
            return None
        if (type(detected) is not bool or not isinstance(generation, str)
                or not generation or not generation.isascii() or not generation.isdecimal()):
            raise VisualTransportError("Native external-input guard snapshot is missing or malformed")
        return generation

    def _archive(self, obs: Observation) -> VisualFrame:
        generation = self._check_external_input(obs, dispatched=True)
        world_updates = validate_visual_clock(obs, synchronized=True)
        visual = self._visual(obs)
        if (type(visual.get("visual_io_version")) is not int
                or visual.get("visual_io_version") != 1 or obs.paused is not True
                or visual.get("paused") is not True
                or type(visual.get("action_seq")) is not int
                or visual.get("action_seq") != obs.last_action_seq):
            raise VisualTransportError("Missing or unsynchronized paused visual-v1 observation")
        capture_id = visual.get("capture_id")
        frame_id = visual.get("frame_id")
        if (type(capture_id) not in (int, str) or capture_id == ""
                or not isinstance(frame_id, str) or not frame_id):
            raise VisualTransportError("Screenshot identity is missing")
        relative = Path(str(visual.get("path", "")))
        save = self.session.user_folder.resolve()
        source = (save / relative).resolve()
        if relative.is_absolute() or not source.is_relative_to(save) or source == save:
            raise VisualTransportError("Screenshot path escapes the game save folder")
        try:
            with source.open("rb") as image:
                data = image.read(16 * 1024 * 1024 + 1)
        except OSError as error:
            raise VisualTransportError("Native screenshot is missing or unreadable") from error
        if len(data) > 16 * 1024 * 1024:
            raise VisualTransportError("Native screenshot exceeds the 16 MiB limit")
        if len(data) < 33 or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
            raise VisualTransportError("Native screenshot is not a PNG")
        width, height = struct.unpack(">II", data[16:24])
        if not (1 <= width <= 8192 and 1 <= height <= 8192):
            raise VisualTransportError("Unsupported screenshot dimensions")
        if (width, height) != (visual.get("width"), visual.get("height")):
            raise VisualTransportError("Screenshot dimensions disagree with native metadata")
        latest = self.session.observe()
        self._check_external_input(latest, expected_generation=generation, dispatched=True)
        validate_visual_clock(latest, synchronized=True)
        if (any(self._visual(latest).get(key) != visual.get(key) for key in _CAPTURE_FIELDS)
                or latest.last_action_seq != obs.last_action_seq or latest.paused is not True):
            raise VisualTransportError("Game changed while archiving the screenshot")
        digest = hashlib.sha256(data).hexdigest()
        dest = self.screens / f"{self.ordinal:05d}-{digest[:16]}.png"
        self.ordinal += 1
        with dest.open("xb") as output:
            output.write(data)
        reference = {"path": dest.relative_to(self.root).as_posix(), "width": width,
                     "height": height, "frame_id": frame_id, "capture_id": capture_id,
                     "sha256": digest, "action_seq": obs.last_action_seq,
                     "external_input_generation": generation,
                     **{key: visual[key] for key in _CLOCK_FIELDS},
                     "coordinate_space": visual.get("coordinate_space", "client")}
        return VisualFrame(obs, dest, reference, capture_id)

    def capture(self) -> VisualFrame:
        """Request the first paused image; this also opts into visual-v1 mode."""
        return self._dispatch([], 0, None)

    def step(self, before: VisualFrame, actions: list[dict], advance_frames: int) -> VisualFrame:
        if type(advance_frames) is not int or not 0 <= advance_frames <= 600:
            raise ValueError("advance_frames must be an integer in 0..600")
        if not isinstance(actions, list) or len(actions) > 4:
            raise ValueError("At most four primitive inputs are allowed per decision")
        if any(not isinstance(a, dict) or a.get("type") not in ("click", "move", "drag", "key") for a in actions):
            raise ValueError("Visual transport accepts only mouse/key primitives")
        try:
            digest = hashlib.sha256(before.image_path.read_bytes()).hexdigest()
        except OSError as error:
            raise VisualTransportError("Archived decision screenshot is missing or unreadable") from error
        if digest != before.reference["sha256"]:
            raise VisualTransportError("Archived decision screenshot changed")
        return self._dispatch(actions, advance_frames, before)

    def _dispatch(self, actions: list[dict], advance: int, before: VisualFrame | None) -> VisualFrame:
        current = self.session._sync_seq()
        if current is None:
            raise VisualTransportError("Game must be paused before visual input")
        expected_generation = before.reference.get("external_input_generation") if before else None
        if before is not None and (not isinstance(expected_generation, str)
                                   or expected_generation != self._visual(before.observation).get("external_input_generation")):
            raise VisualTransportError("Archived capture is missing its external-input generation identity")
        self._check_external_input(current, require_snapshot=before is not None,
                                   expected_generation=expected_generation)
        validate_visual_clock(current, require_snapshot=before is not None, synchronized=True)
        if current.paused is not True:
            raise VisualTransportError("Game must be paused before visual input")
        if before is not None:
            visual = self._visual(current)
            expected_visual = self._visual(before.observation)
            if any(before.reference.get(key) != expected_visual.get(key)
                   for key in _CLOCK_FIELDS):
                raise VisualTransportError("Archived capture is missing its visual clock identity")
            if (any(visual.get(key) != expected_visual.get(key) for key in _CAPTURE_FIELDS)
                    or visual.get("capture_id") != before.capture_id
                    or visual.get("frame_id") != before.reference["frame_id"]
                    or visual.get("action_seq") != before.observation.last_action_seq
                    or visual.get("paused") is not True
                    or current.last_action_seq != before.observation.last_action_seq):
                raise VisualTransportError("Stale screenshot: no inputs were dispatched")
        self.session.action_seq += 1
        seq = self.session.action_seq
        packet = {"seq": seq, "advance_frames": advance, "actions": actions,
                  "observation_mode": "visual-v1"}
        if before is not None:
            packet["expected_capture_id"] = before.capture_id
            packet["expected_external_input_generation"] = expected_generation
        self.session._write_action_atomic(packet)

        def acknowledged(observation):
            # A physical event can race the Python preflight and the native input
            # dispatcher. Stop as soon as any polled observation reports it, even
            # before the ordinary acknowledgement is otherwise complete.
            self._check_external_input(observation, require_snapshot=False,
                                       expected_generation=expected_generation, dispatched=True)
            validate_visual_clock(observation, require_snapshot=False)
            return (observation.last_action_seq == seq and observation.paused
                    and self._visual(observation).get("action_seq") == seq)

        obs = self.session._wait_for(
            acknowledged,
            timeout=max(self.session.step_timeout, advance / 30 + 10),
        )
        visual = self._visual(obs)
        self._check_external_input(obs, expected_generation=expected_generation, dispatched=True)
        world_updates = validate_visual_clock(obs, synchronized=True)
        if before is not None and (visual.get("capture_id") == before.capture_id
                                   or visual.get("frame_id") == before.reference["frame_id"]):
            raise VisualTransportError("Native acknowledgement reused the preceding screenshot identity")
        if type(visual.get("requested_frames")) is not int or visual.get("requested_frames") != advance:
            raise VisualTransportError("Native frame request acknowledgement mismatch")
        actual = visual.get("actual_frames")
        if type(actual) is not int or not 0 <= actual <= advance:
            raise VisualTransportError("Native frame accounting is missing or exceeds the budget")
        if before is not None and int(world_updates) - int(before.reference["world_updates"]) != actual:
            raise VisualTransportError("Native world-update counter disagrees with actual_frames")
        feedback = visual.get("input_feedback")
        if not isinstance(feedback, list) or len(feedback) != len(actions):
            raise VisualTransportError("Native input-delivery acknowledgement is incomplete")
        for index, (action, item) in enumerate(zip(actions, feedback)):
            if (not isinstance(item, dict) or type(item.get("index")) is not int
                    or item.get("index") != index or item.get("type") != action["type"]
                    or item.get("status") not in ("delivered", "rejected")):
                raise VisualTransportError("Native input-delivery acknowledgement mismatch")
        return self._archive(obs)
