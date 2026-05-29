"""Internal rule modules for the engine.

Each module implements one phase or area of the period loop. The engine's
`run_period` orchestrator (see `../engine.py`) calls into these in turn.
Nothing in `rules/` is part of the public API — apps should keep importing
from `sim_engine` directly.
"""
