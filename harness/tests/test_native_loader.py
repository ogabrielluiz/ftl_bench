"""Inert loader downgrade fixtures; no real installer/game/process execution."""
import importlib.util
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
import pytest
from ftl_bench.cli import _bench_root
ROOT = _bench_root()
spec = importlib.util.spec_from_file_location('native_loader', ROOT / 'scripts/install_native_loader.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)

def num(n):
    out = bytearray()
    while True:
        x = n & 127
        n >>= 7
        if not n:
            out.append(x | 128)
            return bytes(out)
        out.append(x)
        n -= 1

@pytest.fixture
def inputs(tmp_path):
    game = tmp_path / 'game'
    game.mkdir()
    release = tmp_path / 'release'
    (release / 'patch').mkdir(parents=True)
    save = tmp_path / 'unused-profile'
    save.mkdir()
    old = b'original exe'
    new = b'patched exe'
    (game / 'FTLGame.exe').write_bytes(old)
    for name in ['xinput1_4.dll', 'lua-5.3.dll']:
        (release / name).write_bytes(('new ' + name).encode())
        (game / name).write_bytes(('old ' + name).encode())
    (release / 'patch/flips.exe').write_bytes(b'inert flips')
    raw = b'BPS1' + num(len(old)) + num(len(new)) + num(0) + struct.pack('<II', zlib.crc32(old), zlib.crc32(new))
    raw += struct.pack('<I', zlib.crc32(raw))
    (release / 'patch/applicable.bps').write_bytes(raw)
    expected_manifest(release)
    return (game, release, save, tmp_path / 'evidence', new)


def expected_manifest(release):
    path = release.parent / "expected-inputs.json"
    if not path.exists():
        files = [release / "xinput1_4.dll", release / "lua-5.3.dll", release / "patch/flips.exe", *sorted((release / "patch").glob("*.bps"))]
        identities = {p.relative_to(release).as_posix(): {k: loader.identity(p)[k] for k in ("bytes", "sha256")} for p in files}
        path.write_text(loader.json.dumps({"contract": "native-loader-inputs-v1", "source_commit": "d" * 40, "inputs": identities}))
    return path

def fake(new, code=0):

    def run(argv, **kwargs):
        Path(argv[-1]).write_bytes(new)
        return SimpleNamespace(returncode=code, stdout='fixture', stderr='')
    return run

def test_applicable_patch_and_loaders_verified_and_originals_preserved(inputs):
    game, rel, save, out, new = inputs
    (game / 'FTLGame_orig.exe').write_bytes(b'unrelated sentinel')
    result = loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None, run=fake(new))
    assert result['status'] == 'installed' and (game / 'FTLGame.exe').read_bytes() == new
    assert (out / 'backup/FTLGame.exe').read_bytes() == b'original exe'
    assert not list(save.iterdir())
    assert (game / 'FTLGame_orig.exe').read_bytes() == b'unrelated sentinel'

def test_verified_target_skips_flips(inputs):
    game, rel, save, out, new = inputs
    (game / 'FTLGame.exe').write_bytes(new)
    result = loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None, run=lambda *a, **k: pytest.fail('already target'))
    assert result['patch'] == 'already_verified_bps_target'

@pytest.mark.parametrize('bytes_,code', [(b'wrong', 0), (b'patched exe', 1)])
def test_failure_rolls_back_exact_exe_and_loaders(inputs, bytes_, code):
    game, rel, save, out, new = inputs
    before = {p.name: p.read_bytes() for p in game.iterdir()}
    with pytest.raises(RuntimeError):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None, run=fake(bytes_, code))
    assert {p.name: p.read_bytes() for p in game.iterdir()} == before
    assert (out / 'result.json').exists()

def test_corrupt_patch_and_unsupported_source_fail_before_evidence(inputs):
    game, rel, save, out, new = inputs
    (game / 'FTLGame.exe').write_bytes(b'unsupported')
    with pytest.raises(ValueError):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None)
    assert not out.exists()

def test_active_or_pending_guard_fails_before_backup(inputs):
    game, rel, save, out, new = inputs

    def blocked(p):
        raise RuntimeError('pending')
    with pytest.raises(RuntimeError):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=blocked)
    assert not out.exists()

def test_existing_output_not_reused(inputs):
    game, rel, save, out, new = inputs
    out.mkdir()
    with pytest.raises(FileExistsError):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None)

def test_bps_checksum_validation(inputs):
    game, rel, save, out, new = inputs
    p = rel / 'patch/applicable.bps'
    p.write_bytes(p.read_bytes()[:-1] + b'X')
    with pytest.raises(ValueError, match='checksum'):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None)
    assert not out.exists()

def test_corrupted_installed_executable_copy_rolls_back(inputs, monkeypatch):
    game, rel, save, out, new = inputs
    before = {p.name: p.read_bytes() for p in game.iterdir()}
    copy = loader.shutil.copy2

    def corrupt(source, destination, *args, **kwargs):
        result = copy(source, destination, *args, **kwargs)
        if Path(source).name == 'FTLGame.patched.exe':
            Path(destination).write_bytes(b'silent corruption')
        return result
    monkeypatch.setattr(loader.shutil, 'copy2', corrupt)
    with pytest.raises(RuntimeError, match='executable verification'):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None, run=fake(new))
    assert {p.name: p.read_bytes() for p in game.iterdir()} == before

def test_corrupted_backup_fails_explicitly(inputs, monkeypatch):
    game, rel, save, out, new = inputs
    original = (game / 'FTLGame.exe').read_bytes()
    copy = loader.shutil.copy2

    def corrupt(source, destination, *args, **kwargs):
        result = copy(source, destination, *args, **kwargs)
        if Path(destination).parent.name == 'backup':
            Path(destination).write_bytes(b'corrupt backup')
        return result
    monkeypatch.setattr(loader.shutil, 'copy2', corrupt)
    with pytest.raises(RuntimeError, match='Backup verification'):
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=lambda p: None, run=fake(new))
    assert (game / 'FTLGame.exe').read_bytes() == original

@pytest.mark.parametrize('root_name', ['game', 'release', 'save'])
@pytest.mark.parametrize('direction', ['inside', 'ancestor'])
def test_evidence_overlap_rejected_before_writes(inputs, root_name, direction):
    game, rel, save, out, new = inputs
    roots = {'game': game, 'release': rel, 'save': save}
    output = roots[root_name] / 'evidence' if direction == 'inside' else roots[root_name].parent
    with pytest.raises(ValueError, match='overlap'):
        loader.install(game, rel, save, output, expected_inputs=expected_manifest(rel), check=lambda p: None, run=fake(new))


def test_setup_preflights_cli_import_before_loader_mutations():
    source = (ROOT / "scripts/setup_pc.sh").read_text()
    install = source.split("if want install; then", 1)[1].split("# STAGE patch", 1)[0]
    assert install.index("import ftl_bench.installation, ftl_bench.cli") < install.index("mktemp -d")
    assert 'python3 -B -m ftl_bench.cli install-native' in install
    assert "FTLB_LOADER_SCRIPT:FTLB_LOADER_GAME" in install


def test_rollback_attempts_remaining_files_after_one_restore_fails(inputs, monkeypatch):
    game, rel, save, out, new = inputs
    originals = {p.name: p.read_bytes() for p in game.iterdir()}
    copy = loader.shutil.copy2
    restored = []
    def fail_first_restore(source, destination, *args, **kwargs):
        source = Path(source)
        if source.parent.name == "backup":
            restored.append(source.name)
            if source.name == "FTLGame.exe":
                raise OSError("inert restore failure")
        return copy(source, destination, *args, **kwargs)
    monkeypatch.setattr(loader.shutil, "copy2", fail_first_restore)
    checks = 0
    def guard(path):
        nonlocal checks
        checks += 1
        if checks == 4:
            raise RuntimeError("inert failure after loaders copied")
    with pytest.raises(RuntimeError, match="Rollback failed") as caught:
        loader.install(game, rel, save, out, expected_inputs=expected_manifest(rel), check=guard, run=fake(new))
    assert restored == ["FTLGame.exe", "xinput1_4.dll", "lua-5.3.dll"]
    assert (game / "xinput1_4.dll").read_bytes() == originals["xinput1_4.dll"]
    assert (game / "lua-5.3.dll").read_bytes() == originals["lua-5.3.dll"]
    assert caught.value.__cause__ is not None
    receipt = loader.json.loads((out / "result.json").read_text())
    assert receipt["status"] == "rollback_failed"
    assert list(receipt["rollback_errors"]) == ["FTLGame.exe"]


@pytest.mark.parametrize("elevation", ["0", "1"])
def test_powershell_missing_python_fails_without_start_or_elevation(tmp_path, elevation):
    if loader.os.name != "nt":
        pytest.skip("Native PowerShell transport requires Windows")
    text = (ROOT / "scripts/setup_pc.sh").read_text()
    command = text.split("powershell.exe -NoProfile -NonInteractive -Command '", 1)[1].split("' \\", 1)[0]
    env = {**loader.os.environ, "FTLB_LOADER_PYTHON": str(tmp_path / "missing interpreter.exe"),
           "FTLB_LOADER_ELEVATE": elevation}
    result = loader.subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "missing interpreter" in result.stderr


@pytest.mark.parametrize("change", ["flips", "loader", "missing", "extra"])
def test_native_input_manifest_binding_rejects_before_backup(inputs, change):
    game, rel, save, out, new = inputs
    expected = expected_manifest(rel)
    if change == "flips":
        (rel / "patch/flips.exe").write_bytes(b"changed executable")
    elif change == "loader":
        (rel / "xinput1_4.dll").write_bytes(b"changed loader")
    else:
        doc = loader.json.loads(expected.read_text())
        if change == "missing":
            del doc["inputs"]["patch/flips.exe"]
        else:
            doc["inputs"]["unexpected"] = {"bytes": 1, "sha256": "f" * 64}
        expected.write_text(loader.json.dumps(doc))
    with pytest.raises(ValueError, match="authenticated"):
        loader.install(game, rel, save, out, expected_inputs=expected, check=lambda p: None, run=fake(new))
    assert not out.exists()
