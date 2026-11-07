# Native store price refresh

On November 7, 2026 UTC, a Sol/hybrid full-game run reopened a store at hull 22.
The screenshot still showed 6 scrap for Fix All, the correct quote when the
store was last open at hull 27. Fix All repaired eight points and charged 6
scrap. The operator stopped the run cooperatively. The original report retains
the interruption, and the protected runner restored all seven original saves.

## Cause and scope

FTL 1.6.9 recalculates the total in `RepairStoreBox::OnLoop`. The renderer and
purchase handler read that cached price, while the purchase repairs the current
missing hull. Ordinary paused GUI updates refresh the open store. The benchmark
suppresses the broad GUI update during zero-frame decisions, so reopening could
retain the old value through the next purchase.

The fix refreshes the active vanilla Store child on the visible buy tab, at the
idle input boundary and before frozen GUI hover. It uses the native
`Store::OnLoop` and leaves tab selection and purchase handling to the game.
Native `CommandGui::SetStore` assigns the typed Store to buy tab zero.
`TabbedWindow::OnLoop` can switch tabs, so the refresh calls the child directly.

The refresh requires benchmark clock ownership with the frame permit closed,
native pause, focus, and a clear interference guard. It skips jumping, pending
map travel, hidden stores, other visible modal windows, and native confirmation
ownership (`confirmBuy`). Custom stores are excluded because their update path also ticks
button animations. World updates, frame permits and native timer updates keep
their existing gates. The separate [hidden store arrival repair](native-store-arrival.md)
still permits warp and queued Continue before a settled store blocks simulation.

## Protected regression

Both no-model runs used the same driver, seed and store path. The driver made
controlled hull edits in the disposable fixture, first from 30 to 27 and then
from 27 to 22 while the store was closed. Native clicks reopened the store and
bought Fix All. The unit price was 2 scrap, and both purchases restored hull
to 30.

| Runtime | Initial quote at hull 27 | Reopened quote at hull 22 | Scrap charged | Reopen and purchase frames |
| --- | ---: | ---: | ---: | ---: |
| Prior focus-fix DLL | 6 | 6 | 6 | 0 |
| Rebuilt store-refresh DLL | 6 | 16 | 16 | 0 |

The two runs matched the twelve action steps, native frame counts and timers,
and input-guard readings. Both consumed one fuel on the native arrival, and
both admitted zero of 600 requested frames once the store was visible. The
world counter and native timer held through reopening and purchase. Protected
cleanup restored all seven original saves and the prior deployed Lua. An
independent audit rehashed 123 artifacts and 85 source pins per run.

The rebuilt Windows Release DLL came from `47db7f6` and has SHA-256
`e8cd1f3d8df3dff115f8c6bb20096b4748bc5da8aa77ff0ebffef2dcadf10923`.
Its provenance SHA-256 is
`7f0abe4c5a2372f81e685c72d95989ac01ca7fe181a38fa3558fc26b9770c2a8`.
A preliminary Debug Boost.Filesystem dependency build failed. The Release
compile and link succeeded, and installation verified the original data and
save inventory.

The local probe outputs are
`harness/runs/validation/store-refresh-47db7f6-baseline-20261107T0038Z/` and
`harness/runs/validation/store-refresh-47db7f6-fixed-20261107/` in the isolated
checkout. The independent audit is
`dist/store-ui-build/store-refresh-red-green-independent-audit-20261107.json`,
SHA-256 `67a8db8c8d5115250262f654cf012ed07be0701615574668d1216f1e6a011036`.
The prior run and exact native dispatch evidence remain in the setup checkout
under `dist/resume-20261106/`. See [current work](NEXT.md) for receipt hashes.

The probe establishes this vanilla repair path on the installed candidate.
The separate protected collection passed all eight startup checks and nine
timing probes. Independent review passed all eight rejection checks, and the
rebuilt runtime received scoped controller admission. The new challenge matrix
and full-game protocols are frozen. The preserved comparison runs retain their
original outcomes. See [current work](NEXT.md) for cohort and admission identities.
