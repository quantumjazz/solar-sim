"""sim-engine — a scenario-driven business simulation engine.

Public surface:

    from sim_engine import load_scenario_pack, run_period
    from sim_engine.decisions import TeamDecision
    from sim_engine.state import PeriodState

See README.md for the v0.1 MVP scope. See ../../docs/spec/ for the full
mechanics specification.
"""

from sim_engine.engine import run_period
from sim_engine.scenario import load_scenario_pack
from sim_engine.state import PeriodState

__version__ = "0.1.0"
__all__ = ["run_period", "load_scenario_pack", "PeriodState"]
