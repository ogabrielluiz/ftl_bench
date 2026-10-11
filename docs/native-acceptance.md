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
