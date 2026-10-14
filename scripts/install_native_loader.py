"""Install a pinned loader and applicable BPS downgrade; no game launch or save writes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import zlib
from pathlib import Path

def safe(path):
    p = Path(path).absolute()
    for q in (p, *p.parents):
        try:
            s = q.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 1024:
            raise ValueError('Linked installation path')
    return p.resolve()

def identity(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'crc32': zlib.crc32(data) & 4294967295}

def bps_identity(path):
    data = path.read_bytes()
    if data[:4] != b'BPS1' or len(data) < 16:
        raise ValueError('Invalid BPS header')
    if zlib.crc32(data[:-4]) & 4294967295 != struct.unpack('<I', data[-4:])[0]:
        raise ValueError('Invalid BPS checksum')
    pos = 4

    def number():
        nonlocal pos
        value = 0
        shift = 1
        while True:
            if pos >= len(data) - 12:
                raise ValueError('Truncated BPS size')
            x = data[pos]
            pos += 1
            value += (x & 127) * shift
            if x & 128:
                return value
            shift <<= 7
            value += shift
    source, target, metadata = (number(), number(), number())
    if pos + metadata > len(data) - 12:
        raise ValueError('Truncated BPS metadata')
    return {'source_bytes': source, 'target_bytes': target, 'source_crc32': struct.unpack('<I', data[-12:-8])[0], 'target_crc32': struct.unpack('<I', data[-8:-4])[0]}

def closed(save):
    marker = safe(save / 'ftl_bench_pending_launch.json')
    if marker.exists():
        raise RuntimeError('Pending protected launch')
    if os.name != 'nt':
        raise RuntimeError('Native Windows installer required')
    x = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference='Stop'; $p=@(Get-Process | Where-Object {$_.ProcessName -eq 'FTLGame'} | Select-Object Id); ConvertTo-Json -InputObject $p -Compress"], capture_output=True, text=True, timeout=30)
    if x.returncode or json.loads(x.stdout) != []:
        raise RuntimeError('FTL process inspection failed or FTL active')

def install(game, release, save, output, *, expected_inputs, check=closed, run=subprocess.run):
    game, release, save, output = map(safe, (game, release, save, output))
    for root in (game, release, save):
        if output == root or output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError('Evidence and installation roots must not overlap')
    exe = safe(game / 'FTLGame.exe')
    flips = safe(release / 'patch/flips.exe')
    inputs = {p.relative_to(release).as_posix(): identity(safe(p)) for p in [flips, release / 'xinput1_4.dll', release / 'lua-5.3.dll']}
    source = identity(exe)
    patches = []
    for p in sorted((release / 'patch').glob('*.bps')):
        info = bps_identity(safe(p))
        patches.append((p, info))
        inputs[p.relative_to(release).as_posix()] = identity(p)
    expected_path = safe(expected_inputs)
    expected_identity = identity(expected_path)
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    if (not isinstance(expected, dict) or expected.get('contract') != 'native-loader-inputs-v1'
            or not isinstance(expected.get('source_commit'), str)
            or len(expected['source_commit']) != 40
            or any(char not in '0123456789abcdef' for char in expected['source_commit'])
            or not isinstance(expected.get('inputs'), dict)):
        raise ValueError('Invalid expected loader input manifest')
    for value in expected['inputs'].values():
        if (not isinstance(value, dict) or set(value) != {'bytes', 'sha256'}
                or type(value['bytes']) is not int or value['bytes'] < 0
                or not isinstance(value['sha256'], str) or len(value['sha256']) != 64
                or any(char not in '0123456789abcdef' for char in value['sha256'])):
            raise ValueError('Invalid expected loader input identity')
    actual_inputs = {name: {key: value[key] for key in ('bytes', 'sha256')} for name, value in inputs.items()}
    if expected['inputs'] != actual_inputs:
        raise ValueError('Loader inputs differ from authenticated native source manifest')
    applicable = [(p, i) for p, i in patches if (i['source_bytes'], i['source_crc32']) == (source['bytes'], source['crc32'])]
    target_known = any(((i['target_bytes'], i['target_crc32']) == (source['bytes'], source['crc32']) for p, i in patches))
    if not applicable and (not target_known):
        raise ValueError('Executable matches no BPS source or target identity')
    if applicable and len({(i['target_bytes'], i['target_crc32']) for p, i in applicable}) != 1:
        raise ValueError('Ambiguous BPS targets')
    check(save)
    output.mkdir(parents=True, exist_ok=False)
    backup = output / 'backup'
    backup.mkdir()
    originals = {}
    for name in ['FTLGame.exe', 'xinput1_4.dll', 'lua-5.3.dll']:
        dest = safe(game / name)
        originals[name] = identity(dest) if dest.exists() else None
        if dest.exists():
            shutil.copy2(dest, backup / name)
            if identity(backup / name) != originals[name]:
                raise RuntimeError('Backup verification failed')
    receipt = {'expected_source_commit': expected['source_commit'], 'expected_manifest': {'path': str(expected_path), **expected_identity}, 'inputs': inputs, 'originals': originals, 'game': str(game), 'status': 'incomplete'}
    (output / 'preparation.json').write_text(json.dumps(receipt, indent=2))
    try:
        check(save)
        if identity(expected_path) != expected_identity:
            raise RuntimeError('Expected loader manifest changed')
        if identity(exe) != source:
            raise RuntimeError('Executable changed after backup')
        for name, expected in inputs.items():
            if identity(safe(release / name)) != expected:
                raise RuntimeError('Pinned installer input changed')
        if applicable:
            patch, info = applicable[0]
            candidate = output / 'FTLGame.patched.exe'
            result = run([str(flips), '-a', str(patch), str(exe), str(candidate)], capture_output=True, text=True)
            (output / 'flips.stdout.txt').write_text(result.stdout)
            (output / 'flips.stderr.txt').write_text(result.stderr)
            if result.returncode:
                raise RuntimeError('BPS patch command failed')
            got = identity(candidate)
            if (got['bytes'], got['crc32']) != (info['target_bytes'], info['target_crc32']):
                raise RuntimeError('BPS target identity mismatch')
            expected_exe = got
            check(save)
            shutil.copy2(candidate, exe)
            if identity(exe) != expected_exe:
                raise RuntimeError('Installed executable verification failed')
            receipt['patch'] = str(patch)
        else:
            expected_exe = source
            receipt['patch'] = 'already_verified_bps_target'
        for name in ['xinput1_4.dll', 'lua-5.3.dll']:
            shutil.copy2(release / name, game / name)
            if identity(game / name) != inputs[name]:
                raise RuntimeError('Loader verification failed')
        check(save)
        if identity(exe) != expected_exe:
            raise RuntimeError('Final executable verification failed')
        for name in ['xinput1_4.dll', 'lua-5.3.dll']:
            if identity(game / name) != inputs[name]:
                raise RuntimeError('Final loader verification failed')
        receipt.update(status='installed', installed={name: identity(game / name) for name in originals})
    except BaseException as original_error:
        errors = {}
        receipt['original_error'] = {'type': type(original_error).__name__, 'message': str(original_error)}
        try:
            check(save)
        except BaseException as error:
            receipt['status'] = 'rollback_blocked'
            receipt['rollback_errors'] = {'process_or_launch_guard': str(error)}
            raise RuntimeError(f'Rollback blocked; retained evidence: {output}') from original_error
        for name, old in originals.items():
            try:
                check(save)
                destination = safe(game / name)
                if old is None:
                    destination.unlink(missing_ok=True)
                else:
                    source_backup = safe(backup / name)
                    if identity(source_backup) != old:
                        raise RuntimeError('Rollback backup changed')
                    shutil.copy2(source_backup, destination)
                if (identity(destination) if destination.exists() else None) != old:
                    raise RuntimeError('Rollback verification failed')
            except BaseException as error:
                errors[name] = {'type': type(error).__name__, 'message': str(error)}
        receipt['rollback_errors'] = errors
        receipt['status'] = 'rollback_failed' if errors else 'rolled_back'
        if errors:
            raise RuntimeError(f'Rollback failed for {", ".join(errors)}; retained evidence: {output}') from original_error
        raise
    finally:
        (output / 'result.json').write_text(json.dumps(receipt, indent=2))
    return receipt

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['game', 'release', 'save', 'output', 'expected-inputs']:
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(install(a.game, a.release, a.save, a.output, expected_inputs=a.expected_inputs)))
if __name__ == '__main__':
    main()
