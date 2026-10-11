# Portable native evidence verification

scripts/validate_native_acceptance.py is a file-only verifier for a **source
checkout**. Run it with the checkout's harness/src package through uv; an
installed wheel's bundled root is not an acceptance source checkout.
It never launches FTL, calls a model, installs a DLL or promotes a runtime.

Native build identity and prospective bridge behavior are separate. A staged
DLL/provenance pair can retain its original build identity while a changed Lua
bridge requires new startup and timing evidence. Copying an old acceptance
receipt or changing its labels does not establish acceptance for new sources.

The protected producers are scripts/validate_visual_startup.py and
scripts/validate_visual_timing.py. They launch FTL when explicitly run. Use
one game/controller at a time, with the intended native runtime installed and
no active trial. Keep a new output directory for every attempt, including
failures. For a prospective collection, use the same explicit evidence root
for both producers. From the repository root (uv executes from harness/):

    uv run --directory harness python ../scripts/validate_visual_startup.py --seed 1 --evidence-root .. --output runs/acceptance/startup
    uv run --directory harness python ../scripts/validate_visual_timing.py --challenge all --evidence-root .. --output runs/acceptance/timing

Archive the exact native inputs inside the collection so later builds preserve
its references. In PowerShell, from the repository root:

```powershell
New-Item -ItemType Directory -Path harness/runs/acceptance/native-artifacts -ErrorAction Stop
Copy-Item -LiteralPath dist/Hyperspace.visual-v1.dll -Destination harness/runs/acceptance/native-artifacts/Hyperspace.visual-v1.dll -ErrorAction Stop
Copy-Item -LiteralPath dist/native-build.visual-v1.json -Destination harness/runs/acceptance/native-artifacts/native-build.visual-v1.json -ErrorAction Stop
Copy-Item -LiteralPath mod/ftl_bench_bridge/dev/ftl_bench_dev.lua -Destination harness/runs/acceptance/native-artifacts/production-bridge.lua -ErrorAction Stop
```

To verify every patched native source file against the exact manifest base,
archive its Git objects from an explicit local native repository. The collector
reads committed objects, so it does not require a clean working tree or change
the native checkout. It performs no fetch, build, installation or game launch:

    uv run --directory harness python ../scripts/collect_native_source_evidence.py --repository <native-repository> --source-root .. --evidence-root .. --output runs/acceptance/native-source

The repository must already contain the manifest's base commit and required
objects. Add `--source-evidence runs/acceptance/native-source/source-reconstruction.json`
to the assembly command below to include this proof. Collection creates a new
directory exclusively; preserve partial output from a failed attempt.

The proof retains raw commit, tree and blob objects with portable SHA-256
references. Verification authenticates their Git object identities back to the
exact base commit, proves which added files were absent, applies the cumulative
patch in memory with exact context and line endings, and compares every resulting
file hash with build provenance. It supports ordinary additions and modifications;
unsupported rename, deletion, binary or mode-change patches are rejected.
This proves source reconstruction, not that a compiler produced a particular DLL.
Omitting this optional proof leaves `native_identity.source_reconstruction` null.

Use a fresh archive directory; preserve partial attempts if copying fails.
After both producers finish, assemble a candidate from the explicit copies. All
selected files and their nested references must stay under --evidence-root.
No directory search substitutes for a recorded reference:

    uv run --directory harness python ../scripts/validate_native_acceptance.py --assemble-spec --source-root .. --evidence-root .. --startup-evidence runs/acceptance/startup/startup-evidence.json --timing-evidence runs/acceptance/timing/timing-evidence.json --dll runs/acceptance/native-artifacts/Hyperspace.visual-v1.dll --provenance runs/acceptance/native-artifacts/native-build.visual-v1.json --bridge runs/acceptance/native-artifacts/production-bridge.lua --output runs/acceptance/candidate.json
    uv run --directory harness python ../scripts/validate_native_acceptance.py --source-root .. --evidence-root .. --spec runs/acceptance/candidate.json --output runs/acceptance/verification.json

Both assembly and verification create new files exclusively; existing outputs
are refused. Moving an evidence tree is supported when its relative references
retain the same root layout and bytes. The native pair and current bridge must
also be available under that root. Absolute paths inside raw inventory documents
are recorded labels; the verifier does not access those live paths.

The spec contract is portable-visual-native-acceptance-v1. Its required keys are
source_snapshot, native (dll, provenance), bridge, startup and probes. Every
file reference is exactly {path, sha256}, with a relative POSIX path and
lowercase SHA-256. Startup references trajectory, session, admission, runtime,
cleanup and images (SHA-keyed references). Each of the nine probes adds
challenge, repetition, delay_seconds and timing_script; setup_store_close is
required only for the ordinary store close prerequisite. Assembly also pins
the two producer descriptors.

The verifier also derives `runtime_files` from the joined raw cleanup inventories
of startup and all nine timing trials. All ten must agree on `FTLGame.exe`,
`ftl.dat`, `Hyperspace.dll`, `xinput1_4.dll`, `lua-5.3.dll` and
`ftlbench-native.json`. A missing inventory leaves the check pending; a changed
asset makes it invalid. This is the recorded diagnostic baseline, not a current
inspection of the installed game.

Verification derives checks from canonical native observations, dispatched
packet archives and PNG bytes. It joins the current source map to archived
source bytes and the prelaunch map digest recorded in each trajectory. It
checks the patched-file provenance inventory, DLL hash/size, capability
contract, exact fixture-free first capture, zero actor decisions, fixed
updates and fresh idle captures, localized progression and equality of the
three trajectories per challenge under delays 0, 0.35 and 1.2 seconds.
Cleanup joins original backup bytes and the exact save inventory (including
an empty profile), runtime/production hashes and timestamped before/after
inventory records.

The result is pending (exit 2), invalid (exit 1), or validated_scoped (exit 0).
Missing raw references or source/cleanup fields produce actionable pending
requirements; contradictory bytes or observations are invalid. Historical
summary passed flags cannot replace those fields.

validated_scoped still records production_accepted=false and
controller_admission=false. It establishes the listed file joins and finite
measured paths only. It does not reexecute a compiler, independently resample
the live save/process state, prove every RNG stream, establish full-game
determinism or complete a model comparison. Cleanup is a saved point-in-time
attestation. Controller promotion and any broader native acceptance checks
remain separate; historical frozen protocols are unchanged.

## Prospective portable controller admission

The implemented controller workflow is **WIP with offline validation**. No
completed live v2 controller admission is claimed. A prospective cohort requires
fresh main-checkout startup and all nine timing probes after executable sources
settle and the active controller completes protected cleanup. Collect them in a
new exclusive `harness/runs/validation/visual-v1/main-admission-<UTC>` directory,
then have an independent reviewer examine that exact source/evidence collection
and execute meaningful negative probes before freezing a new cohort. Executable
source changes require fresh diagnostics and review; do not modify existing
frozen sources or evidence to make an old cohort pass.

`ftl_bench.controller_admission.require_admission` recomputes the positive raw
evidence baseline. It requires `validated_scoped`, both startup/timing producer
descriptors, complete native source reconstruction and the common six-file
runtime. It also verifies the original build origin and independent review
bindings described below. Missing or contradictory gates raise
`AdmissionError`, a `ValueError` subclass, before a controller launches a child.
Its deterministic result separately derives `controller_admission: true` while
retaining `production_accepted: false`. The scoped native report itself keeps
both admission fields false. This grants only the documented local controller
scope, with no general full-game determinism or build-execution attestation.

### Admission and build-origin schemas

Every reference below is exactly `{"path": relative_POSIX_path, "sha256":
lowercase_SHA256}`. The spec itself and all nested referenced files must reside
under the explicit evidence root. Links, absolute reference paths and traversal
are rejected. Preserve the original bytes, including line endings.

The controller spec has exactly four keys:

| Key | Required value |
| --- | --- |
| `contract` | `portable-visual-controller-admission-v1` |
| `candidate` | Reference to the portable native acceptance candidate |
| `build_origin` | Reference to the build-origin document |
| `review` | Reference to the independent review document |

The build-origin document uses `contract: portable-native-build-origin-v1`,
`kind: fresh` or `historical`, `record` as a reference to the **original** build
record, and `build_sources` as a map from every native patched filename to its
explicit hashed source-file reference. Its keys must equal the complete
reconstructed patched-file inventory. The bytes behind every reference must
match reconstruction and current provenance; a declared hash map alone is
insufficient.

For `fresh`, `record` is the original output of
`scripts/write_native_provenance.py`, with `source_commit`, a complete
`source_files_sha256` map and matching `patch_sha256`. A
`production_reuse_of_tested_build` record cannot be presented as a fresh build.
For `historical`, `record` is the original diagnostic build manifest, with
`base_commit` and a nonempty `candidate_source_sha256` subset whose entries all
match the complete map. Historical origins additionally require `integration`
as a hashed reference to the original integration document. That document must
contain:

| Key | Required value |
| --- | --- |
| `contract` | `native-production-integration-plan-v1` |
| `candidate_dll_sha256` | Admitted DLL hash |
| `staged_complete_patch_sha256` | Admitted cumulative patch hash |
| `complete_patch_paths` | Exact complete patched-file inventory |
| `staged_sha256` | Complete matching `native-source/<filename>` hash entries |

Backslashes in historical integration labels are normalized for comparison;
they are not paths to read from the machine. Historical diagnostic scope stays
historical. For either kind, the original timezone-aware `built_at`, DLL
hash/size, native base, platform, game version and every required native
capability must match current provenance. `toolchain.image_id` must be nonempty
and match. The recorded `build_command` (or `command`) must match after decoding
JSON-list strings when present. Compiler identities must be present on both
sides or absent on both; recorded labels compare ignoring case and whitespace.
Missing compiler evidence is never manufactured.

### Independent review and mutation receipts

The review document contains `contract: portable-native-admission-review-v1`,
`reviewer`, `bindings` and `mutations`. `reviewer` must identify a nonempty `id`
and explicitly declare `independent_of_producer: true`. The required baseline
bindings are:

| Binding | Required value |
| --- | --- |
| `candidate_sha256` | `spec.candidate.sha256` |
| `build_origin_sha256` | `spec.build_origin.sha256` |
| `source_sha256` | `native_acceptance.source_digest(report.source_files)` |
| `verification_sha256` | `native_acceptance.source_digest(report)` |
| `verifier_sources` | Exact source-map entries for the three verifier files below |

The three verifier paths are
`harness/src/ftl_bench/native_acceptance.py`,
`harness/src/ftl_bench/native_build_origin.py` and
`harness/src/ftl_bench/controller_admission.py`. Here `report` means the
recomputed positive native report for the referenced candidate and exact source
checkout. Use the implementation's `source_digest` for both bindings, including
the whole report; do not substitute the SHA of a pretty-printed JSON file.

`mutations` must contain exactly eight rows, each with exactly `id` and
`evidence` keys. `evidence` is a hashed reference to the reviewer's saved
negative-probe receipt. The unique IDs are `source`, `bridge`,
`native_artifact`, `build_origin`, `runtime_baseline`, `trial_inventory`,
`capture_actions` and `cleanup`. Each referenced receipt must contain:

| Key | Required value |
| --- | --- |
| `case` | The row's same mutation ID |
| `candidate_sha256` | The review's candidate binding |
| `build_origin_sha256` | The review's build-origin binding |
| `verifier_sources` | The review's exact verifier source map |
| `rejected` | `true`, recording an actually rejected negative probe |
| `error` | Nonempty observed rejection error |
| `method` | Nonempty description of the executed negative probe |

The reviewer must actually execute meaningful negative probes and retain their
methods and observed errors. These hash-bound receipts are independent-review
attestations: admission recomputes the positive baseline and checks their
bindings, but does not replay the reviewer's mutation procedure. Do not generate
passing review receipts automatically from a positive validator result.

Original build records and the reviewer identity/independence declaration are
**explicit provenance trust anchors**. Their hashes bind the recorded bytes;
they are not cryptographic proof that a compiler ran or that the reviewer is
independent. An empty reviewer name, an acceptance boolean or rewritten build
labels cannot replace the original records and declarations.

### Offline verification and prospective freeze commands

Run from a source checkout with its `harness/src` package, not an installed
wheel's bundled source root. This file-only command prints derived admission
without game/model operations or writing a review receipt. Replace the evidence
root and spec filename with the reviewed collection's real paths; uv runs from
`harness/`:

```powershell
@'
import json
from pathlib import Path
from ftl_bench.controller_admission import require_admission
root = Path("..").resolve()
evidence = root / "harness/runs/validation/visual-v1/main-admission-<UTC>"
result = require_admission(evidence / "controller-admission-spec.json",
                           source_root=root, evidence_root=evidence)
print(json.dumps(result, indent=2))
'@ | uv run --directory harness python -
```

After independent review accepts that exact collection, use a new output
directory and both freeze-only options. These are command templates, not a
claim that such a reviewed collection currently exists:

```powershell
uv run --directory harness python ../scripts/run_visual_experiment.py freeze --output runs/visual/portable-matrix-<UTC> --native-evidence runs/validation/visual-v1/main-admission-<UTC>/controller-admission-spec.json --evidence-root runs/validation/visual-v1/main-admission-<UTC>
uv run --directory harness python ../scripts/run_fullgame_experiment.py freeze --output runs/visual/portable-fullgame-<UTC> --native-evidence runs/validation/visual-v1/main-admission-<UTC>/controller-admission-spec.json --evidence-root runs/validation/visual-v1/main-admission-<UTC>
```

The paired options select exactly `ftl-visual-challenge-matrix-v2` and
`ftl-fullgame-experiment-v2`, respectively. Supplying only one option, or either
portable option for `run`, `report` or `stop`, is rejected. Omitting both retains
the existing v1 admission path and conditions.

The controller creates the cohort exclusively. `freeze_admission` exclusively
creates `native-evidence/` containing every consumed evidence file, preserving
evidence-relative paths, and `frozen-source/` containing separately pinned
executable source bytes. It recomputes admission from the copied evidence.
There is no separate manifest: `protocol.json` stores `admission_selector`
with exactly `contract`, `spec`, `evidence_files`, `source_files` and `admission`;
`spec` is a relative hashed reference. Protocol source pins remain separate
from evidence pins. Keep failed partial archives and use a new directory.

Verification requires exact archived inventories, identical recomputed
admission and matching current/archived source bytes. Extra, missing, changed,
unsafe or linked files reject. Relocation preserves the evidence layout and
bytes but still requires the matching executable source checkout. Portable
failure never falls back to legacy admission.

Before each new cell, the controller checks the frozen admission and installed
six-file runtime. Inside protected children, after deployment and before the
first model request, a second gate checks the frozen protocol, actual cell
configuration, six installed hashes/native provenance and deployed Lua.
Fullgames require production Lua; challenges require its exactly regenerated
fixture derivative. Existing per-decision guards remain active.
`trial/controller-admission.json` is written exclusively, retaining acceptance
or rejection, protocol/spec hashes, configuration, derived admission, installed
runtime and deployed bridge hash. `run.json` pins that receipt's hash. Rejection
records a technical failure with zero model calls and normal protected cleanup.
Saved report audits join the receipt to cohort protocol bytes, run manifest and
runtime fingerprint; a failed join excludes a challenge trial or prevents a
verified fullgame completion. Dashboard provenance remains a saved audit, not a
new live runtime/save inspection. Budgets, ordering, cooperative stop, no-retry
rules and native-ending completion requirements remain unchanged.

The optional `test_portable_admission_flow.py` exercises raw validation through
admission and relocated archives with synthetic build/review fixtures. It needs
authenticated native base objects: select a local repository explicitly with
`FTL_NATIVE_SOURCE_TEST_REPOSITORY`, or a collected proof JSON under the checkout
with `FTL_NATIVE_SOURCE_TEST_PROOF`. Without either input the test reports a skip;
it never fetches Git objects. Its test-only reviewer records are not independent
review evidence and cannot establish live admission.

## Measured main-checkout example

The 2026-10-11 collection `main-native-20261011-0330` used the producer source
recorded in `b862afd`, the unchanged native DLL beginning `a33b9984`, and the prospective
merged bridge beginning `d9a1ed59`. Startup and all nine probes passed; the
file-only receipt reports `validated_scoped` across 516 pinned evidence files
and 73 source files. Independent cleanup at 03:39:23 UTC matched seven saves,
15 baseline paths and the shared runtime assets with no FTL process remaining.
The [current validation record](NEXT.md) gives the local evidence path and full
receipt hash. Raw evidence and native binaries remain local. This example does
not grant controller admission or certify another machine's runtime.

The later `candidate-archived-inputs.json` preserves exact native input copies
under that collection, leaving the first candidate untouched. All 516 referenced
files were then copied to a separate evidence root and validated again at
03:46:20 UTC, without game or live-save access. The archived-input verification
receipt SHA-256 is
`d5ba97cb7af7db703d4fc783b83ec948e55f81b7b3c67e96199c8395136e5007`;
`relocation-receipt.json` records the portability check.
