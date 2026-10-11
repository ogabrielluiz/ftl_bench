"""Authenticate Git base objects and reconstruct a cumulative patch in memory."""
import hashlib
import re

from .native_acceptance import EvidenceError, MissingEvidence, digest, relative_path

CONTRACT = "native-source-reconstruction-v1"


def require(value, message):
    if not value:
        raise EvidenceError(message)


def object_id(kind, data):
    return hashlib.sha1(kind.encode() + b" " + str(len(data)).encode() + b"\0" + data).hexdigest()


def lf_lines(data):
    """Git line boundaries are LF; retain CR and every other byte verbatim."""
    pieces = data.split(b"\n")
    return [part + b"\n" for part in pieces[:-1]] + ([pieces[-1]] if pieces[-1] else [])


def patch_sections(patch):
    lines = lf_lines(patch)
    sections = []
    for line in lines:
        if line.startswith(b"diff --git "):
            match = re.fullmatch(rb"diff --git a/(\S+) b/\1\r?\n?", line)
            require(match, "Unsupported patch path or rename")
            name = match[1].decode("utf-8")
            relative_path(name)
            require(not any(name == old for old, _ in sections), "Duplicate patch path")
            sections.append((name, []))
        else:
            require(sections, "Patch lacks diff header")
            sections[-1][1].append(line)
    require(sections, "Empty native patch")
    return sections


def apply_section(name, lines, base):
    """Exact unified hunks; line endings and no-newline markers are byte inputs."""
    added = any(line.startswith(b"new file mode ") for line in lines)
    expected_old = b"--- /dev/null" if added else b"--- a/" + name.encode()
    require([line.rstrip(b"\r\n") for line in lines if line.startswith(b"--- ")] == [expected_old]
            and [line.rstrip(b"\r\n") for line in lines if line.startswith(b"+++ ")] == [b"+++ b/" + name.encode()],
            "Patch needs exact old/new path headers")
    require(sum(line.startswith(b"new file mode ") for line in lines) == int(added), "Duplicate new-file mode")
    require((base is None) == added, "New-file absence proof differs: " + name)
    source = [] if base is None else lf_lines(base)
    output, cursor, index, hunks = [], 0, 0, 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith(b"@@ "):
            require(line.startswith((b"index ", b"--- ", b"+++ ", b"new file mode 100644", b"new file mode 100755")), "Unsupported patch metadata")
            if line.startswith(b"new file mode "):
                require(line.rstrip(b"\r\n") in (b"new file mode 100644", b"new file mode 100755"), "Unsupported new-file mode")
            if line.startswith(b"--- "):
                require(line.rstrip(b"\r\n") == (b"--- /dev/null" if added else b"--- a/" + name.encode()), "Old patch path differs")
            if line.startswith(b"+++ "):
                require(line.rstrip(b"\r\n") == b"+++ b/" + name.encode(), "New patch path differs")
            index += 1
            continue
        match = re.match(rb"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        require(match, "Malformed hunk")
        old_start, old_count, new_start, new_count = (int(match[1]), int(match[2] or b"1"), int(match[3]), int(match[4] or b"1"))
        position = old_start if old_count == 0 else old_start - 1
        require(cursor <= position <= len(source), "Hunk offset overlaps or exceeds source")
        output.extend(source[cursor:position])
        cursor = position
        require(len(output) == (new_start if new_count == 0 else new_start - 1), "New hunk position differs")
        consumed = produced = 0
        index += 1
        while index < len(lines) and not lines[index].startswith(b"@@ "):
            current = lines[index]
            require(current[:1] in (b" ", b"+", b"-"), "Unsupported hunk line")
            prefix, data = current[:1], current[1:]
            index += 1
            if index < len(lines) and lines[index].startswith(b"\\ No newline at end of file"):
                require(lines[index].rstrip(b"\r\n") == b"\\ No newline at end of file", "Malformed no-newline marker")
                require(data.endswith(b"\n"), "Malformed no-newline marker")
                data = data[:-1]
                index += 1
            if prefix != b"+":
                require(cursor < len(source) and source[cursor] == data, "Exact patch context mismatch: " + name)
                cursor += 1
                consumed += 1
            if prefix != b"-":
                output.append(data)
                produced += 1
        require((consumed, produced) == (old_count, new_count), "Hunk line counts differ")
        hunks += 1
    require(hunks, "Patch section has no hunks")
    output.extend(source[cursor:])
    return b"".join(output)


def reconstruct_sources(*, manifest, patch, proof, reader):
    require(proof.get("contract") == CONTRACT, "Wrong native reconstruction contract")
    require(digest(patch) == manifest.get("patch_sha256"), "Native patch hash differs")
    objects = proof.get("objects")
    require(isinstance(objects, dict), "Git object references missing")

    def load(oid, kind):
        require(isinstance(oid, str) and re.fullmatch(r"[0-9a-f]{40}", oid), "Malformed Git object ID")
        record = objects.get(oid)
        if record is None:
            raise MissingEvidence("Git object missing: " + oid)
        require(isinstance(record, dict) and set(record) == {"type", "reference"} and record["type"] == kind, "Git object missing or wrong type")
        data = reader.bytes(record["reference"], "Git " + kind + " " + oid)
        require(object_id(kind, data) == oid, "Git object bytes do not authenticate")
        return data

    commit = manifest.get("base_commit")
    raw = load(commit, "commit")
    header = raw.split(b"\n\n", 1)[0].split(b"\n")
    trees = [line[5:] for line in header if line.startswith(b"tree ")]
    require(len(trees) == 1, "Commit must have one root tree")
    tree_id = trees[0].decode("ascii")

    def entries(oid):
        data = load(oid, "tree")
        result, offset = {}, 0
        while offset < len(data):
            space, zero = data.find(b" ", offset), data.find(b"\0", offset)
            require(offset < space < zero and zero + 21 <= len(data), "Malformed Git tree")
            mode = data[offset:space]
            name = data[space + 1:zero].decode("utf-8")
            require(name and name not in (".", "..") and "/" not in name and "\\" not in name and name not in result, "Unsafe or duplicate Git tree entry")
            result[name] = (mode, data[zero + 1:zero + 21].hex())
            offset = zero + 21
        return result

    reconstructed = {}
    for name, lines in patch_sections(patch):
        parts = name.split("/")
        current = tree_id
        base = None
        for number, part in enumerate(parts):
            entry = entries(current).get(part)
            if entry is None:
                break
            mode, oid = entry
            if number == len(parts) - 1:
                require(mode in (b"100644", b"100755"), "Patched base is not a regular blob")
                base = load(oid, "blob")
            else:
                require(mode == b"40000", "Patch ancestor is not a tree")
                current = oid
        reconstructed[name] = digest(apply_section(name, lines, base))
    return {"source_files_sha256": reconstructed, "base_commit": commit, "patch_sha256": digest(patch),
            "scope": "Exact authenticated Git base plus cumulative patch bytes; no compiler or DLL build execution inferred"}
