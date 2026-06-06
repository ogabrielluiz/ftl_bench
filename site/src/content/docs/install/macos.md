---
title: Install on macOS (Rosetta)
description: Set up FTL + Hyperspace on macOS. Works, but full runs are limited by the Rosetta freeze class.
---

`ftl_bench` runs on macOS, but with a caveat worth knowing up front.

:::caution[Rosetta limits full runs]
On Apple Silicon, FTL and Hyperspace run as x86 under Rosetta. The address-translation layer
corrupts a vtable that is freed during jumps and sector transitions, which can crash or freeze the
engine. Short scenarios are fine, but full-length runs are capped by this. For sustained runs,
prefer the [native x86 PC setup](/install/pc/).
:::

## What you need

- FTL installed via Steam.
- A built `Hyperspace` dylib plus the data mods staged in `dist/` (the repo's build flow).
- FTLMan for patching `ftl.dat` (it has a CLI, no GUI required).

## App-side install

`scripts/install_macos.sh` does the scriptable parts: it copies the Hyperspace dylib and the
`Hyperspace.command` launcher into `FTL.app`, patches `Info.plist` so the app launches via the
Hyperspace launcher, and prepares for codesigning.

```bash
scripts/install_macos.sh   # uses the Steam default FTL.app path, or pass a path
```

## Patch the data mods, then codesign

Patch from vanilla with FTLMan, then codesign last (patching modifies `ftl.dat`, which would
invalidate a prior signature):

```bash
ftlman patch dist/hyperspace.ftl dist/ftl_bench_bridge.ftl -d "<FTL.app>/Contents/Resources"
codesign -f -s - --timestamp=none --all-architectures --deep "<FTL.app>"
```

## Launch and point the harness

Launch the app's Hyperspace launcher directly (not via Steam), then set the user folder:

```bash
export FTL_SAVE_DIR="$HOME/Library/Application Support/FasterThanLight"
scripts/restart_ftl.sh none     # launch FTL to the menu
python3 adapter/play_cli.py obs  # should print a live observation
```

Two operating caveats on macOS:

1. **App Nap** must be off so FTL keeps ticking unfocused, which lets the harness drive it
   unattended: `defaults write com.example.FTL NSAppSleepDisabled -bool YES`.
2. The **microphone-permission dialog** reappears only after a Hyperspace C++ rebuild (the code
   signature changes); it persists across plain relaunches of the same build.

Then continue with the [Quickstart](/evaluate/quickstart/).
