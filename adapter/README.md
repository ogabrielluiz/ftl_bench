# adapter

Exposes the `harness` environment to a coding agent as **MCP / function-calling tools**:

- `observe()` → current `Observation` JSON
- `legal_actions()` → valid actions in the current context
- `act(action)` → apply an intent-level action
- `end_turn()` → resume the sim until the next decision point

Translates the constrained action schema ↔ harness calls so any tool-capable LLM agent can play.
