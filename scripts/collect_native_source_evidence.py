"""Archive exact manifest-base Git objects without changing or fetching a checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness/src"))
from ftl_bench.native_acceptance import Reader, read_json, relative_path
from ftl_bench.native_build_origin import CONTRACT, patch_sections, reconstruct_sources


def collect(*, repository, source_root, output, evidence_root):
    repository, source_root = Path(repository).resolve(), Path(source_root).resolve()
    output, evidence_root = Path(output).resolve(), Path(evidence_root).resolve()
    if not output.is_relative_to(evidence_root):
        raise ValueError("Output must be inside explicit evidence root")
    if output.is_relative_to(repository):
        raise ValueError("Evidence output must not modify the native repository")
    manifest = read_json((source_root / "native/manifest.json").read_bytes())
    patch = (source_root / relative_path(manifest["patch"])).read_bytes()
    if hashlib.sha256(patch).hexdigest() != manifest["patch_sha256"]:
        raise ValueError("Manifest patch hash differs")
    output.mkdir(parents=True, exist_ok=False)
    objects = {}

    def object_data(oid, kind):
        if not isinstance(oid, str) or not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise ValueError("Expected exact lowercase SHA1 Git object ID")
        if oid in objects:
            return (output / "objects" / oid).read_bytes()
        git_environment = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
        data = subprocess.check_output(["git", "--no-replace-objects", "-C", str(repository), "cat-file", kind, oid], env=git_environment)
        destination = output / "objects" / oid
        destination.parent.mkdir(exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        objects[oid] = {"type": kind, "reference": {"path": destination.relative_to(evidence_root).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest()}}
        return data

    commit = object_data(manifest["base_commit"], "commit")
    root_tree = next(line[5:].decode("ascii") for line in commit.split(b"\n\n", 1)[0].split(b"\n") if line.startswith(b"tree "))
    for name, _ in patch_sections(patch):
        tree = root_tree
        parts = name.split("/")
        for number, part in enumerate(parts):
            data = object_data(tree, "tree")
            offset, found = 0, None
            while offset < len(data):
                space, zero = data.index(b" ", offset), data.index(b"\0", offset)
                if data[space + 1:zero] == part.encode():
                    found = (data[offset:space], data[zero + 1:zero + 21].hex())
                offset = zero + 21
            if found is None:
                break
            mode, oid = found
            if number == len(parts) - 1:
                if mode not in (b"100644", b"100755"):
                    raise ValueError("Patched path is not a regular blob")
                object_data(oid, "blob")
            else:
                if mode != b"40000":
                    raise ValueError("Patched path ancestor is not a tree")
                tree = oid
    proof = {"contract": CONTRACT, "objects": objects}
    # Validate exactly what was archived before producing a usable proof.
    reconstruct_sources(manifest=manifest, patch=patch, proof=proof, reader=Reader(evidence_root))
    with (output / "source-reconstruction.json").open("x", encoding="utf-8") as stream:
        json.dump(proof, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return output / "source-reconstruction.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    print(collect(repository=args.repository, source_root=args.source_root, output=args.output, evidence_root=args.evidence_root))


if __name__ == "__main__":
    main()
