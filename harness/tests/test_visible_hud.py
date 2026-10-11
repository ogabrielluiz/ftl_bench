"""Pixel-reader regressions using independently transcribed archived HUD strips."""
import hashlib
import inspect
import json
from pathlib import Path
import struct
import zlib

import pytest

import visible_hud as reader


FIXTURES = Path(__file__).parent / "fixtures" / "visible_hud"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _png(rows, width=1280, height=720):
    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + bytes(row) for row in rows)))
            + chunk(b"IEND", b""))


def _mutate(tmp_path, box, transform, filename="changed.png"):
    rows = [bytearray(row) for row in reader._decode_png((FIXTURES / "ship.png").read_bytes())[2]]
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        for x in range(x0, x1):
            rows[y][x * 3:x * 3 + 3] = bytes(transform(tuple(rows[y][x * 3:x * 3 + 3])))
    output = tmp_path / filename
    output.write_bytes(_png(rows))
    return output


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda case: case["name"])
def test_archived_pixels_match_manual_transcriptions(case):
    path = FIXTURES / case["fixture"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case["fixture_sha256"]
    result = reader.extract_visible_hud(path)
    assert result["values"] == case["expected_values"]
    assert result["provenance"]["image_sha256"] == case["fixture_sha256"]
    assert result["provenance"]["contract"] == MANIFEST["contract"]["contract"]
    assert result["provenance"]["config_sha256"] == MANIFEST["contract"]["config_sha256"]
    assert set(result["values"]).isdisjoint({"paused", "hull_max"})
    for name in case["conservative_omissions"]:
        assert result["provenance"]["fields"][name]["status"] == "omitted"


@pytest.mark.parametrize("name,box", [
    ("fuel", (165, 56, 169, 70)),  # erase the entire leading 1 in 16
    ("fuel", (171, 56, 181, 70)),  # erase the entire trailing 6
    ("scrap", (449, 21, 459, 35)),  # erase the entire leading 3 in 30
    ("scrap", (461, 21, 471, 35)),  # erase the entire trailing 0
    ("hull_current", (335, 48, 345, 62)),
    ("hull_current", (347, 48, 357, 62)),
])
def test_whole_digit_dark_occlusion_does_not_shorten_value(tmp_path, name, box):
    result = reader.extract_visible_hud(_mutate(tmp_path, box, lambda _: (20, 20, 20)))
    assert name not in result["values"]
    assert result["provenance"]["fields"][name]["status"] == "omitted"


def test_one_pixel_glyph_damage_is_omitted(tmp_path):
    result = reader.extract_visible_hud(_mutate(tmp_path, (167, 56, 168, 57), lambda _: (20, 20, 20)))
    assert "fuel" not in result["values"]
    assert result["provenance"]["fields"]["fuel"]["reason"] == "unrecognized_glyph"


def test_dimmed_hud_has_no_retained_resources(tmp_path):
    path = _mutate(tmp_path, (0, 0, 505, 80), lambda p: tuple(channel // 3 for channel in p))
    result = reader.extract_visible_hud(path)
    assert result["values"] == {}
    assert result["provenance"]["status"] == "omitted"


def test_occluding_window_has_no_retained_resources(tmp_path):
    path = _mutate(tmp_path, (0, 0, 505, 80), lambda _: (50, 50, 50))
    assert reader.visible_hud(path) == {}


def test_foreign_bright_label_inside_numeral_crop_is_omitted(tmp_path):
    path = _mutate(tmp_path, (160, 60, 163, 63), lambda _: (255, 255, 0))
    result = reader.extract_visible_hud(path)
    assert "fuel" not in result["values"]
    assert result["provenance"]["fields"]["fuel"]["reason"] == "unexpected_color_or_overlay"


def test_hidden_observation_cannot_influence_summary(tmp_path, monkeypatch):
    screenshot = tmp_path / "frame.png"
    screenshot.write_bytes((FIXTURES / "ship.png").read_bytes())
    hidden = tmp_path / "observation.json"
    hidden.write_text(json.dumps({"resources": {"fuel": 999}, "hull_max": 999}))
    expected = reader.extract_visible_hud(screenshot)
    hidden.write_text(json.dumps({"resources": {"fuel": -1}, "hull_max": -1}))
    original_open = Path.open
    accesses = []
    def screenshot_only(path, *args, **kwargs):
        accesses.append(path)
        assert path == screenshot
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", screenshot_only)
    assert reader.extract_visible_hud(screenshot) == expected
    assert accesses == [screenshot]
    assert list(inspect.signature(reader.extract_visible_hud).parameters) == ["image_path"]


def test_lower_scene_pixels_do_not_add_or_change_hud_values(tmp_path):
    path = _mutate(tmp_path, (0, 100, 1280, 720), lambda _: (255, 255, 255))
    result = reader.extract_visible_hud(path)
    original = reader.extract_visible_hud(FIXTURES / "ship.png")
    assert result["values"] == original["values"]
    assert result["provenance"]["image_sha256"] != original["provenance"]["image_sha256"]


@pytest.mark.parametrize("kind", ["corrupt", "truncated", "dimensions", "missing"])
def test_unsupported_image_fails_closed(tmp_path, kind):
    data = bytearray((FIXTURES / "ship.png").read_bytes())
    path = tmp_path / "bad.png"
    if kind == "corrupt":
        data[100] ^= 1
    elif kind == "truncated":
        data = data[:-10]
    elif kind == "dimensions":
        data = _png([bytes(3840)] * 719, height=719)
    if kind != "missing":
        path.write_bytes(data)
    result = reader.extract_visible_hud(path)
    assert result["values"] == {}
    assert result["provenance"]["status"] == "unsupported_image"


def test_public_aliases_share_values_and_evidence():
    path = FIXTURES / "ship.png"
    result = reader.extract_visible_hud(path)
    assert reader.visible_hud(path) == result["values"]
    assert reader.read_visible_hud(path) == {"summary": result["values"], "evidence": result["provenance"]}


@pytest.mark.parametrize("tag,payload", [(b"tRNS", b"\0\0\0\0\0\0"), (b"acTL", struct.pack(">II", 2, 0))])
def test_transparent_or_animated_png_fails_closed(tmp_path, tag, payload):
    data = (FIXTURES / "ship.png").read_bytes()
    chunk = struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    path = tmp_path / "changed.png"
    path.write_bytes(data[:33] + chunk + data[33:])
    result = reader.extract_visible_hud(path)
    assert result["values"] == {}
    assert result["provenance"]["status"] == "unsupported_image"
