---
title: Full-game mode
description: Canonical play through victory or loss, with explicit failure and progress bounds.
---

`--mode gameover` is the canonical full-game mode. It continues beyond the scenario's jump budget and ends on verified victory, destruction/crew-loss game over, concession, stall, error or a hard safety cap. `--mode budget` is a separate bounded probe.

```powershell
ftlbench run --agent llm --backend <backend> --model <model-id> --mode gameover --stall-limit 10
ftlbench run --agent scripted --mode budget --max-instances 1 --budget-cap 3
```

A win requires the native `victory` boolean. Game over alone is also a loss signal. A model's text or a raw boss stage counter never substitutes for that evidence.

The stall guard watches meaningful state changes: map movement, enemy damage, resources, repairs, crew health, fires/intruders and weapon/FTL/special-system charging. Waiting while a weapon charges is progress. Transport tick/sequence changes alone are not progress.

Concession is an unsolved harness outcome. Stalls, safety limits and model/transport errors have explicit terminal reasons and remain unsolved. The attempt retains its last valid state and score rather than disappearing from reports.

Full-game results require protocol-5 native victory capability and verified Kestrel A/easy setup. See [protocol](/introduction/protocol/).
