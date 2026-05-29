"""Mutable per-period scratch dataclass shared across rule modules.

`_PeriodScratch` is the engine's internal accumulator within one period:
the pre-market phase fills its produce-side fields, the settlement phase
records sales, and the post-market phase reads aggregates to build the
P&L, balance sheet, and cash flow. It is never persisted — it lives only
during one `run_period` call.

Lives in its own module so engine.py and every rule module can import it
without creating an import cycle through the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class _PeriodScratch:
    """Mutable workspace within one period — not part of the public state."""

    # Per-product computed values
    units_produced: Dict[str, float]
    cgm_per_unit: Dict[str, float]                  # cost of goods manufactured
    units_sold: Dict[str, Dict[str, int]]            # product_id -> market_id -> units
    revenue: Dict[str, Dict[str, float]]
    material_units_consumed: Dict[str, float]
    material_cost_consumed: Dict[str, float]
    factory_material_cost: Dict[str, float]
    transport_cost: Dict[str, Dict[str, float]]

    # Aggregates
    total_revenue: float = 0
    total_cogs: float = 0
    total_other_expenses: float = 0
    total_other_income: float = 0
    total_extraordinary_income: float = 0
    total_extraordinary_expense: float = 0
    total_wages: float = 0
    total_non_salary: float = 0
    total_pension_contribution: float = 0
    total_hiring_costs: float = 0
    total_dismissal_costs: float = 0
    total_training: float = 0
    total_depreciation: float = 0
    total_overhead_other: float = 0  # CI, advertising, market research, R&D consulting, env. compliance, rework, maintenance, etc.

    # Production-line capital movements (investing cash flows)
    line_purchases: float = 0
    disinvestment_proceeds: float = 0

    # Inventory changes
    change_in_finished_inventory: float = 0
