"""Validate the actual game bindings and dependency-free image encoder."""
import binascii
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zlib

import pytest

from ftl_bench.cli import _bench_root


ROOT = _bench_root()


def writer_test_source():
    manifest = json.loads((ROOT / "native/manifest.json").read_text())
    patch = (ROOT / manifest["patch"]).read_text()
    reconstructed = "\n".join(line[1:] for line in patch.splitlines()
                              if line.startswith(("+", " ")) and not line.startswith("+++"))
    writer = re.search(r"#ifdef _WIN32\n(        // Readers share.*?)(?=\n#else)", reconstructed, re.S)
    assert writer, "actual native publication policy must be present in the distributed patch"
    assert "temp_file.flush();" in reconstructed
    template = (ROOT / "native/tests/observation_writer_test.cpp.in").read_text()
    return template.replace("@PUBLICATION@", writer.group(1))


def test_actual_native_writer_policy_preserves_old_snapshot_and_bounds_retries(tmp_path):
    source = tmp_path / "writer.cpp"
    source.write_text(writer_test_source())
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; generated test can run in WSL")
    executable = tmp_path / "writer-test"
    subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-pedantic",
                    str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable), str(tmp_path)], check=True)


def decode_png(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed, dimensions = 8, b"", None
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        assert binascii.crc32(kind + body) & 0xffffffff == crc
        if kind == b"IHDR":
            width, height, *format_fields = struct.unpack(">IIBBBBB", body)
            assert format_fields == [8, 2, 0, 0, 0]
            dimensions = width, height
        if kind == b"IDAT":
            compressed += body
        offset += length + 12
    return dimensions, zlib.decompress(compressed)


def test_native_visual_helpers_and_png_decode(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; native/tests/visual_test.cpp can run in WSL")
    executable, image = tmp_path / "visual-test", tmp_path / "capture.png"
    subprocess.run([compiler, "-std=c++11", "-O2", "-DNDEBUG", "-Wall", "-Wextra", "-pedantic",
                    str(ROOT / "native/tests/visual_test.cpp"), "-o", str(executable)], check=True)
    subprocess.run([str(executable), str(image)], check=True)
    dimensions, pixels = decode_png(image.read_bytes())
    assert dimensions == (2, 2)
    assert pixels == bytes([0, 255, 0, 0, 0, 255, 0, 0, 0, 0, 255, 255, 255, 255])


def test_renderer_input_signatures_match_exactly_one_real_ftl_function():
    executable = Path(r"C:\Program Files (x86)\Steam\steamapps\common\FTL Faster Than Light\FTLGame.exe")
    if not executable.is_file():
        pytest.skip("local FTL1.6.9 executable unavailable")
    image = executable.read_bytes()
    source = (ROOT / "native/include/Benchmark_VisualEngine.inc").read_text()
    signatures = re.findall(r'FunctionDefinition\s+\w+\("(benchmark_\w+)".*?\n\s*"([0-9a-f?]+)"', source)
    assert len(signatures) == 6
    # PE section mapping, not hard-coded ASLR addresses.
    pe = struct.unpack_from("<I", image, 0x3c)[0]
    sections = struct.unpack_from("<H", image, pe + 6)[0]
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    section_table = pe + 24 + optional_size
    text = next(struct.unpack_from("<8sIIII", image, section_table + i * 40)
                for i in range(sections) if image[section_table + i * 40:section_table + i * 40 + 5] == b".text")
    _, _, rva, raw_size, raw_offset = text
    code = image[raw_offset:raw_offset + raw_size]
    expected = {"benchmark_graphics_read_pixels": 0x2251d0, "benchmark_graphics_width": 0x224ea0,
                "benchmark_graphics_height": 0x224eb0, "benchmark_graphics_finish_frame": 0x224f60,
                "benchmark_input_key_state": 0x22b080, "benchmark_input_mouse_position": 0x22b0e0}
    for name, signature in signatures:
        pattern = b"".join(b"." if part == "??" else re.escape(bytes.fromhex(part))
                           for part in re.findall("..", signature))
        matches = list(re.finditer(pattern, code, flags=re.S))
        assert len(matches) == 1, name
        assert matches[0].start() + rva == expected[name], name


def test_real_ftl_calls_fps_before_world_pause_and_gui_updates():
    """Check the ordering that the fixed-step hook relies on in FTL 1.6.9."""
    executable = Path(r"C:\Program Files (x86)\Steam\steamapps\common\FTL Faster Than Light\FTLGame.exe")
    if not executable.is_file():
        pytest.skip("local FTL1.6.9 executable unavailable")
    image = executable.read_bytes()
    pe = struct.unpack_from("<I", image, 0x3c)[0]
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    section_table = pe + 24 + optional_size
    sections = [struct.unpack_from("<8sIIII", image, section_table + i * 40)
                for i in range(struct.unpack_from("<H", image, pe + 6)[0])]
    def at_rva(address, length):
        _, _, rva, raw_size, offset = next(section for section in sections
            if section[2] <= address and address + length <= section[2] + section[3])
        return image[offset + address - rva:offset + address - rva + length]
    start = 0x22c0
    app = at_rva(start, 0x230)
    assert app.startswith(bytes.fromhex("578d7c240883e4f0ff77fc5589e557565389cbb9"))
    targets = {"fps": 0x19a4e0, "world": 0x1f6520, "pause": 0x1f6070, "gui": 0x1220b0}
    offsets = {name: [offset for offset in range(len(app) - 4)
        if app[offset] == 0xe8 and start + offset + 5 + struct.unpack_from("<i", app, offset + 1)[0] == target]
        for name, target in targets.items()}
    assert all(len(matches) == 1 for matches in offsets.values())
    assert all(offsets["fps"][0] < offsets[name][0] for name in ("world", "pause", "gui"))
    # Native CFPS converts wall seconds into the field's 16x time units;
    # gameplay subsequently converts back with 0.0625. Do not choose 1.f/60.f
    # as SpeedFactor, which would make the simulation sixteen times too slow.
    assert struct.unpack("<f", at_rva(0x433904, 4))[0] == 16.0
    assert struct.unpack("<f", at_rva(0x433908, 4))[0] == 0.0625


def test_shipped_visual_patch_contains_the_same_engine_and_codec_sources():
    manifest = json.loads((ROOT / "native/manifest.json").read_text())
    assert manifest["visual_io_version"] == 1
    assert manifest["visual_clock_version"] == 2
    assert manifest["fixed_step_numerator"] == 1 and manifest["fixed_step_denominator"] == 60
    patch = (ROOT / manifest["patch"]).read_text()
    for name in ("Benchmark_Visual.h", "Benchmark_VisualEngine.inc"):
        hunk = patch.split(f"+++ b/{name}\n", 1)[1].split("\n", 1)[1].split("diff --git", 1)[0]
        shipped = "\n".join(line[1:] for line in hunk.splitlines() if line.startswith("+")) + "\n"
        assert shipped == (ROOT / "native/include" / name).read_text()


def external_input_test_source():
    source = (ROOT / "native/include/Benchmark_VisualEngine.inc").read_text()
    hook = re.search(r"HOOK_METHOD\(CEvent, OnEvent, \(const InputEvent\* event\) -> void\)\n(\{.*?\n\})\n\nHOOK_GLOBAL", source, re.S)
    assert hook, "test must execute the actual shipped native event hook"
    return (ROOT / "native/tests/external_input_test.cpp.in").read_text().replace("@EVENT_HOOK@", hook.group(1))


def test_actual_native_input_boundary_preserves_events_and_detects_only_external_input(tmp_path):
    source = tmp_path / "external-input.cpp"
    source.write_text(external_input_test_source())
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; generated event-hook test can run in WSL")
    executable = tmp_path / "external-input-test"
    subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-pedantic",
                    "-I", str(ROOT / "native/include"), str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


def visual_clock_test_source():
    engine = (ROOT / "native/include/Benchmark_VisualEngine.inc").read_text()
    template = (ROOT / "native/tests/visual_clock_test.cpp.in").read_text()
    hooks = {"APP_LOOP": ("CApp", "OnLoop"), "FPS_LOOP": ("CFPS", "OnLoop"), "WORLD_LOOP": ("WorldManager", "OnLoop"),
             "PAUSE_LOOP": ("WorldManager", "PauseLoop"), "GUI_LOOP": ("CommandGui", "OnLoop"),
             "JUMP_RENDER": ("AnimationTracker", "Update")}
    for token, (kind, method) in hooks.items():
        hook = re.search(rf"HOOK_METHOD_PRIORITY\({kind}, {method}, 99999, \(\) -> void\)\n(\{{.*?\n\}})", engine, re.S)
        assert hook, f"actual shipped clock gate is missing: {kind}.{method}"
        template = template.replace(f"@{token}@", hook.group(1))
    return template


def test_actual_world_gui_and_jump_render_hooks_freeze_native_pause_commits(tmp_path):
    source = tmp_path / "clock.cpp"
    source.write_text(visual_clock_test_source())
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; generated clock-hook test can run in WSL")
    executable = tmp_path / "clock-test"
    subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-pedantic",
                    "-I", str(ROOT / "native/include"), str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


def visual_blocker_test_source():
    engine = (ROOT / "native/include/Benchmark_VisualEngine.inc").read_text()
    blocker = re.search(r"const char\* visual_blocked_reason\(CApp\* app\)\n(\{.*?\n\})", engine, re.S)
    assert blocker, "test must execute the actual native visible-modal predicate"
    function = "const char* visual_blocked_reason(CApp* app)\n" + blocker.group(1)
    return (ROOT / "native/tests/visual_blocker_test.cpp.in").read_text().replace("@BLOCKER@", function)


def test_hidden_staged_arrival_modals_allow_bounded_warp_then_block_when_visible(tmp_path):
    source = tmp_path / "blocker.cpp"
    source.write_text(visual_blocker_test_source())
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; generated visible-modal test can run in WSL")
    executable = tmp_path / "blocker-test"
    subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-pedantic",
                    "-I", str(ROOT / "native/include"), str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


def map_ui_test_source():
    """Execute the shipped helper and exported wrappers, not a copied policy."""
    engine = (ROOT / "native/include/Benchmark_VisualEngine.inc").read_text()
    helper = re.search(r"    void refresh_idle_map_ui\(CApp\* app\)\n    \{.*?\n    \}", engine, re.S)
    assert helper, "actual shipped idle-map UI refresh helper is missing"
    wrappers = []
    for name in ("mouse_move", "mouse_click", "mouse_drag", "key_press"):
        wrapper = re.search(rf"bool hs_benchmark_{name}\([^\n]*\)\n\{{.*?\n\}}", engine, re.S)
        assert wrapper, f"actual shipped input wrapper is missing: {name}"
        wrappers.append(wrapper.group(0))
    template = (ROOT / "native/tests/map_ui_test.cpp.in").read_text()
    return template.replace("@REFRESH_IDLE_MAP_UI@", helper.group(0)).replace(
        "@INPUT_WRAPPERS@", "\n".join(wrappers))


def tooltip_test_source():
    """Run actual pointer/key hover helpers and wrappers with native tooltip semantics."""
    engine = (ROOT / "native/include/Benchmark_VisualEngine.inc").read_text()
    helper = re.search(r"    void clear_pointer_tooltip\(\)\n    \{.*?\n    \}", engine, re.S)
    assert helper, "actual shipped tooltip-only clear must be present"
    hover = re.search(r"    void refresh_pointer_hover\(CApp\* app\)\n    \{.*?\n    \}", engine, re.S)
    assert hover, "actual shipped post-key native hover must be present"
    loop = re.search(r"HOOK_METHOD_PRIORITY\(CommandGui, OnLoop, 99999, \(\) -> void\)\n(\{.*?\n\})", engine, re.S)
    assert loop, "actual frozen GUI hover hook must be present"
    wrappers = []
    for name in ("mouse_move", "mouse_click", "mouse_drag", "key_press"):
        wrapper = re.search(rf"bool hs_benchmark_{name}\([^\n]*\)\n\{{.*?\n\}}", engine, re.S)
        assert wrapper, f"actual shipped input wrapper is missing: {name}"
        wrappers.append(wrapper.group(0))
    template = (ROOT / "native/tests/tooltip_test.cpp.in").read_text()
    return template.replace("@CLEAR_POINTER_TOOLTIP@", helper.group(0)).replace(
        "@REFRESH_POINTER_HOVER@", hover.group(0)).replace(
        "@GUI_HOVER_LOOP@", loop.group(1)).replace(
        "@INPUT_WRAPPERS@", "\n".join(wrappers))


def test_actual_pointer_tooltip_refresh_matches_final_hover_without_disarming_or_advancing(tmp_path):
    source = tmp_path / "tooltip.cpp"
    source.write_text(tooltip_test_source())
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; generated tooltip test can run in WSL")
    executable = tmp_path / "tooltip-test"
    subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-pedantic",
                    "-I", str(ROOT / "native/include"), str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


def test_actual_idle_map_ui_helper_refreshes_wait_without_committing_pending_world_work(tmp_path):
    source = tmp_path / "map-ui.cpp"
    source.write_text(map_ui_test_source())
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("host C++ compiler unavailable; generated map UI test can run in WSL")
    executable = tmp_path / "map-ui-test"
    subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-pedantic",
                    "-I", str(ROOT / "native/include"), str(source), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
