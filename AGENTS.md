# Contributor and agent guidance

## Read first

Read `README.md` for setup, `docs/NEXT.md` for current WIP status, and
`docs/visual-experiment-protocol.md` before changing experiment behavior.
`docs/visual-iteration.md` describes the visual observation and replay contract.
Historical diagnostics are evidence with their original scope, not current acceptance.

## Repository map

- `harness/src/ftl_bench/`: CLI, sessions, protected game lifecycle, setup, installation and reporting.
- `adapter/run_visual.py`: visual runner and Codex CLI wiring; `adapter/run_benchmark.py`: separate structured runner.
- `scripts/run_visual_experiment.py`: frozen challenge matrix; `scripts/run_fullgame_experiment.py`: sector pilot and four full-game conditions.
- `mod/ftl_bench_bridge/dev/ftl_bench_dev.lua`: production external Lua bridge.
- `native/manifest.json`, `native/patches/`, `native/include/`: native contract, cumulative source patch and included implementations.
- `dashboard/`: React replay/experiment UI; `adapter/ftl_live.py`: read-only dashboard backend.
- `harness/tests/`, `dashboard/tests/`, `native/tests/`: regression checks; `scenarios/` and `prompts/`: declared task and actor contracts.

## Offline validation

Run these from the repository root; select focused checks appropriate to the change.

```sh
uv run --directory harness --extra dev --extra dashboard pytest -q
npm --prefix dashboard ci
npm --prefix dashboard test
npm --prefix dashboard run build
```

Build the dashboard before building Python distributions: the Hatch hook ships
its compiled assets and vendors sibling sources into `_bundled/`.

```sh
uv build --directory harness
uv run --directory harness python ../scripts/smoke_package.py
uv run --directory harness python ../scripts/smoke_sdist.py
```

For the standalone native test targets, use a C++ toolchain, such as WSL, from
the repository root:

```sh
cmake -S native/tests -B build/native-tests
cmake --build build/native-tests
ctest --test-dir build/native-tests --output-on-failure
```

These targets cover a subset of native checks. Other native tests use actual
Hyperspace includes and toolchain prerequisites; report skips and separately
executed checks honestly. Offline tests and package smokes do not establish live
game acceptance or model performance.

## Native and packaged artifacts

Use the cumulative patch selected and hashed by `native/manifest.json`;
do not replace it with an older partial patch and lose existing controls.
Keep the include implementations, patch and manifest consistent.
`scripts/apply_native_patch.py` checks the source boundary;
`scripts/write_native_provenance.py` records the actual build inputs and DLL.
Never relabel diagnostic provenance as accepted production evidence.

For portable source evidence, use `scripts/collect_native_source_evidence.py`
against an explicit local native repository. The proof authenticates the exact
manifest base and reconstructs every patched file; it does not attest a compiler
invocation. Runtime equality across diagnostics and build-source reconstruction
are separate checks. Keep historical evidence pinned to its original verifier
and source bytes when either implementation changes.

Portable v2 controllers additionally require original build-source evidence and
an independent review bound to the exact candidate, verifier and eight retained
negative probes. See `docs/native-acceptance.md` for the schemas. A review is an
explicit provenance attestation, not cryptographic proof; never manufacture one
from a successful baseline check. Preserve the file-only verifier's
`production_accepted: false` and its separate scoped result. Controller admission
is local and explicit. Keep all source/evidence archives immutable, reject
unreadable or extra archive content, and check the installed runtime, deployed
bridge and actual cell settings inside protected children before model calls.
Saved child admission is required for v2 result eligibility; it does not replace
native outcome or protected-cleanup verification. Comparison aggregation must
select the protocol-specific admission path: v2 uses admitted runtime plus the
saved child audit, while v1 retains its legacy receipts. Cover successful v2
aggregation without mocking the aggregator; dashboard projection tests alone
cannot verify eligibility. For v2 full-game dashboard completion, also join the
saved child admission receipt to its manifest, protocol and recorded runtime;
a saved completion flag alone is insufficient. Keep this projection read-only
and avoid live admission or installed-runtime checks. Preserve old reports when
repairing their interpretation.

Visual startup requires native protocol 5, clock 2 with fixed step 1/60, and
`fresh-start-seed-v3`; protocol 5 alone is insufficient. Preserve the structured
runner's separate contracts. Native DLLs, local acceptance receipts, `dist/`,
run outputs, compiled UI and `_bundled/` are generated/local artifacts, not
editable sources of truth. A fresh clone does not contain the locally accepted
runtime/evidence chain required by frozen controllers.

## Benchmark evidence and lifecycle

Image actors receive the exact archived PNG and permitted history. Hybrid adds
only conservative values extracted from that same PNG, omitting uncertainty.
Never expose hidden native state or evaluator assessments to the actor. Archive
the canonical first image before startup validation.

Full-game completion requires audited native victory or defeat. A pilot,
budget stop, concession or interruption is not a completed full game. Preserve
native score provenance; enemy lifecycle flags and raw kill counters alone do
not prove a combat kill. Task success must retain its declared evaluator proof.
Finite setup/trajectory equality does not prove general full-game determinism.

Modal blockers must follow native visibility during transitions. An open store
or event may be staged while warp still hides it; blocking that transition can
deadlock arrival. Check both the hidden transition and the settled visible modal,
including queued arrival-choice resolution, real rendering and bounded frame counts. See
`docs/native-store-arrival.md`; artifact integrity alone cannot detect this stall.

Check a cohort's `protocol.json` source pins before editing experiment inputs.
Do not mutate frozen sources or saved runs to make an existing cohort pass.
Changed sources, tasks or budgets require a new freeze/output directory.
Preserve failures, responses, images, terminal reasons and cleanup receipts;
do not silently retry or overwrite started cells.

Use one game/controller at a time. Paused experiments resume only on request;
static documentation work does not authorize a launch or imply live acceptance.
Use the controller's official cooperative `stop` operation from a second
terminal and let the original runner finish protected cleanup. Do not terminate
the runner or replace runtime files during a trial. Verify save restoration
from the protected lifecycle receipts, and distinguish their recorded time
from a current live audit. Credentials must remain outside Git and logs;
environment files are selected explicitly, never discovered automatically.

## Git scope

Tracked files retain their exact committed bytes through `.gitattributes`.
Do not normalize line endings in prompts, native inputs or frozen source files:
their hashes are protocol inputs, including historical mixed-ending artifacts.

Branch names must not include `codex` (the user's explicit preference).
Stage explicit task paths and inspect the staged diff. Exclude unrelated
`.claude/worktrees/` checkouts, credentials, local runs and generated artifacts;
avoid blanket staging of the workspace. State WIP and unproven scopes plainly
in documentation and commit descriptions.
