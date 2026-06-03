# harness

External **environment server** (Python). Wraps the in-game bridge in a gym-like API:

```python
env.reset(seed=..., scenario=...) -> Observation
env.observe() -> Observation
env.step(action) -> (Observation, reward, done, info)
```

Owns episode lifecycle, seed management, termination, scoring, and **full trajectory logging**. Exchanges observation/action with `mod/ftl_bench_bridge` over the transport.
