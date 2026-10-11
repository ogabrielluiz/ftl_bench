"""Conservative resource transcription from the exact captured PNG, without telemetry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import zlib

CONTRACT = "ftl-visible-hud-pixels-v1"
METHOD = "exact-raster-glyphs-1280x720"
# Manually transcribed raster glyphs, with blank side bearings removed. Every
# logical pixel is rendered as a 2x2 block. This is an exact-match dictionary,
# not an OCR model and not a probability/confidence estimate.
_DIGITS = {
    "0": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "1": (".#", "##", ".#", ".#", ".#", ".#", ".#"),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": (".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#...#", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "....#", "...#.", "...#.", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "#...#", ".###."),
}
_FIELDS = {
    "hull_current": {"crop": (333, 47, 359, 63), "anchor": (9, 10, 60, 27),
                     "anchor_sha256": "0ffb66f8b188387b6237dc25b0d8b3364e3619bf4920f4f89ff79f87c68132c8", "color": (255, 255, 255), "max_digits": 2, "min_digits": 2, "left_bearing": 2},
    "fuel": {"crop": (157, 55, 188, 71), "anchor": (132, 53, 154, 73),
             "anchor_sha256": "60379395793bb467c3b48a93731e19d42c76929ac1cbcd33ef979b9fa7600a0a", "color": (243, 255, 230), "max_digits": 3, "center_twice": 31},
    "scrap": {"crop": (425, 20, 497, 36), "anchor": (387, 16, 413, 41),
              "anchor_sha256": "bb92ac4529a3a34c740e62b73a953d8f877219c6b7c7a5b9f9fcfde3dfd1a6f9", "color": (243, 255, 230), "max_digits": 4, "center_twice": 69},
    "missiles": {"crop": (226, 55, 256, 71), "anchor": (201, 57, 225, 69),
                 "anchor_sha256": "2415f8406250b1c77c9217cf83c5a4ba0ec04e62991398f526b267ec51ff87cc", "color": (243, 255, 230), "max_digits": 3, "center_twice": 27},
    "drone_parts": {"crop": (291, 55, 322, 71), "anchor": (270, 53, 289, 72),
                    "anchor_sha256": "f3c8ca3d0b5558283ae80241f86a4bc1782f2320c50e0b1a03515e1643a826c2", "color": (243, 255, 230), "max_digits": 3, "center_twice": 31},
}
_CONFIG = {"contract": CONTRACT, "method": METHOD, "dimensions": [1280, 720],
           "digits": _DIGITS, "fields": _FIELDS, "background_channel_max": 150,
           "anchor_brightness_min": 181, "glyph_scale": 2, "glyph_gap": 2}
CONFIG_SHA256 = hashlib.sha256(json.dumps(_CONFIG, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
TEMPLATE_SHA256 = hashlib.sha256(json.dumps({"digits": _DIGITS, "fields": _FIELDS}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def extractor_identity() -> dict:
    return {"contract": CONTRACT, "method": METHOD, "config_sha256": CONFIG_SHA256,
            "template_sha256": TEMPLATE_SHA256, "input_source": "exact_png_pixels"}


def _decode_png(data: bytes) -> tuple[int, int, list[bytes]]:
    """Decode the supported 8-bit RGB(A), noninterlaced capture format."""
    if len(data) > 16 * 1024 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature or size")
    offset, header, compressed, ended = 8, None, bytearray(), False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + length + 12
        if end > len(data):
            raise ValueError("truncated PNG")
        tag, payload = data[offset + 4:offset + 8], data[offset + 8:end - 4]
        if zlib.crc32(tag + payload) & 0xFFFFFFFF != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("PNG CRC mismatch")
        if header is None:
            if tag != b"IHDR" or len(payload) != 13:
                raise ValueError("missing PNG header")
            header = struct.unpack(">IIBBBBB", payload)
        elif tag == b"IHDR":
            raise ValueError("duplicate PNG header")
        elif tag == b"IDAT":
            compressed.extend(payload)
        elif tag == b"IEND":
            if payload or end != len(data):
                raise ValueError("PNG trailing data")
            ended = True
            break
        elif tag in (b"tRNS", b"acTL", b"fcTL", b"fdAT"):
            raise ValueError("transparent or animated PNG is unsupported")
        elif tag[:1].isupper() and tag not in (b"PLTE",):
            raise ValueError("unsupported critical PNG chunk")
        offset = end
    if not header or not ended or not compressed:
        raise ValueError("incomplete PNG")
    width, height, depth, color, compression, filtering, interlace = header
    if (width, height) != (1280, 720):
        raise ValueError("unsupported dimensions")
    if depth != 8 or color not in (2, 6) or compression or filtering or interlace:
        raise ValueError("unsupported PNG encoding")
    channels = 3 if color == 2 else 4
    stride = width * channels
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, (stride + 1) * height + 1)
    if len(raw) != (stride + 1) * height or not decoder.eof or decoder.unused_data:
        raise ValueError("invalid PNG pixel data")
    rows, previous = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filter_type = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        if filter_type not in range(5):
            raise ValueError("unsupported PNG row filter")
        if filter_type:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up, corner = previous[i], previous[i - channels] if i >= channels else 0
                if filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = up
                elif filter_type == 3:
                    predictor = (left + up) // 2
                else:
                    p = left + up - corner
                    distances = (abs(p - left), abs(p - up), abs(p - corner))
                    predictor = (left, up, corner)[distances.index(min(distances))]
                row[i] = (row[i] + predictor) & 255
        if channels == 4:
            if any(row[i] != 255 for i in range(3, stride, 4)):
                raise ValueError("nonopaque PNG")
            rows.append(bytes(v for i, v in enumerate(row) if i % 4 != 3))
        else:
            rows.append(bytes(row))
        previous = row
    return width, height, rows


def _crop(rows: list[bytes], box: tuple[int, int, int, int]) -> bytes:
    x0, y0, x1, y1 = box
    return b"".join(row[x0 * 3:x1 * 3] for row in rows[y0:y1])


def _read_number(pixels: bytes, config: dict) -> int:
    width = config["crop"][2] - config["crop"][0]
    color, max_digits = config["color"], config["max_digits"]
    mask = []
    for i in range(0, len(pixels), 3):
        pixel = tuple(pixels[i:i + 3])
        if pixel == color:
            mask.append(True)
        elif max(pixel) <= 150:
            mask.append(False)
        else:
            raise ValueError("unexpected_color_or_overlay")
    lines = [mask[i:i + width] for i in range(0, len(mask), width)]
    if len(lines) != 16 or any(lines[0]) or any(lines[-1]):
        raise ValueError("clipped_or_shifted_numerals")
    lines = lines[1:-1]
    columns = [any(line[x] for line in lines) for x in range(width)]
    spans, start = [], None
    for x, occupied in enumerate(columns + [False]):
        if occupied and start is None:
            start = x
        elif not occupied and start is not None:
            spans.append((start, x))
            start = None
    if not spans or len(spans) > max_digits or spans[0][0] == 0 or spans[-1][1] == width:
        raise ValueError("missing_or_clipped_numerals")
    if "center_twice" in config and spans[0][0] + spans[-1][1] - 1 != config["center_twice"]:
        raise ValueError("unrecognized_text_alignment")
    # Hull is left-aligned. Accepting a one-digit hull could mistake a fully
    # erased trailing digit for a valid smaller hull, so v1 omits those values.
    if len(spans) < config.get("min_digits", 1) or ("left_bearing" in config and spans[0][0] != config["left_bearing"]):
        raise ValueError("unrecognized_text_alignment")
    text = ""
    for n, (left, right) in enumerate(spans):
        if n and left - spans[n - 1][1] != 2:
            raise ValueError("unrecognized_digit_spacing")
        candidate = tuple("".join("#" if pixel else "." for pixel in line[left:right]) for line in lines)
        matches = [digit for digit, glyph in _DIGITS.items()
                   if candidate == tuple("".join(pixel * 2 for pixel in row) for row in glyph for _ in range(2))]
        if len(matches) != 1:
            raise ValueError("unrecognized_glyph")
        text += matches[0]
    if len(text) > 1 and text.startswith("0"):
        raise ValueError("unexpected_leading_zero")
    return int(text)


def extract_visible_hud(image_path: str | Path) -> dict:
    """Return only exactly recognized pixels; provenance is evaluator evidence.

    No observation, remembered value, font asset, game process, or native fallback
    is consulted. Read the image once and bind all returned evidence to its bytes.
    Unsupported images fail closed with empty values, never guessed resources.
    """
    evidence = {**extractor_identity(), "image_sha256": None, "fields": {}}
    try:
        with Path(image_path).open("rb") as image:
            data = image.read(16 * 1024 * 1024 + 1)
        evidence["image_sha256"] = hashlib.sha256(data).hexdigest()
        _, _, rows = _decode_png(data)
    except (OSError, ValueError, zlib.error) as error:
        evidence["status"] = "unsupported_image"
        evidence["reason"] = str(error)
        return {"values": {}, "provenance": evidence}
    evidence["dimensions"] = [1280, 720]
    values = {}
    for name, config in _FIELDS.items():
        pixels = _crop(rows, config["crop"])
        anchor = _crop(rows, config["anchor"])
        anchor_mask = bytes(min(anchor[i:i + 3]) > 180 for i in range(0, len(anchor), 3))
        item = {"crop": list(config["crop"]), "anchor_crop": list(config["anchor"]),
                "crop_sha256": hashlib.sha256(pixels).hexdigest(),
                "anchor_mask_sha256": hashlib.sha256(anchor_mask).hexdigest()}
        try:
            if item["anchor_mask_sha256"] != config["anchor_sha256"]:
                raise ValueError("unrecognized_or_occluded_hud_anchor")
            value = _read_number(pixels, config)
            values[name] = value
            item.update(status="recognized", match="exact_glyph_and_anchor", value=value)
        except ValueError as error:
            item.update(status="omitted", reason=str(error))
        evidence["fields"][name] = item
    evidence["status"] = "recognized" if len(values) == len(_FIELDS) else "partial" if values else "omitted"
    return {"values": values, "provenance": evidence}


def visible_hud(image_path: str | Path) -> dict:
    return extract_visible_hud(image_path)["values"]


def read_visible_hud(image_path: str | Path) -> dict:
    """Equivalent interface for callers using summary/evidence terminology."""
    result = extract_visible_hud(image_path)
    return {"summary": result["values"], "evidence": result["provenance"]}
