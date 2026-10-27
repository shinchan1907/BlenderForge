"""Multi-dimensional candidate comparison and Pareto frontier analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Set
from blenderforge.experiments.models import StrategyEvaluationResult


def dominates(a: Dict[str, float], b: Dict[str, float], criteria: Dict[str, str]) -> bool:
    """
    Check if candidate a Pareto-dominates candidate b.
    criteria: mapping of dimension -> 'min' (lower is better) or 'max' (higher is better).
    """
    better_in_at_least_one = False
    for dim, direction in criteria.items():
        val_a = a.get(dim, float("inf") if direction == "min" else float("-inf"))
        val_b = b.get(dim, float("inf") if direction == "min" else float("-inf"))

        if direction == "min":
            if val_a > val_b:
                return False  # a is worse than b in this dimension
            elif val_a < val_b:
                better_in_at_least_one = True
        else:
            if val_a < val_b:
                return False
            elif val_a > val_b:
                better_in_at_least_one = True

    return better_in_at_least_one


class WorkflowComparator:
    """Evaluates and compares candidate strategies across multi-objective dimensions."""

    @staticmethod
    def identify_pareto_frontier(
        results: List[StrategyEvaluationResult],
        criteria: Dict[str, str] = None
    ) -> List[str]:
        """
        Identify Pareto-optimal candidate strategies.
        Default criteria: runtime (min), vertices (min).
        """
        if criteria is None:
            criteria = {
                "runtime_sec": "min",
                "vertex_count": "min"
            }

        successful = [r for r in results if r.success]
        if not successful:
            return []
        if len(successful) == 1:
            return [successful[0].strategy_name]

        # Extract metric vectors
        candidate_metrics: Dict[str, Dict[str, float]] = {}
        for r in successful:
            metrics = {
                "runtime_sec": r.duration_sec,
                "vertex_count": float(r.metrics.get("vertices", 0)),
                "face_count": float(r.metrics.get("faces", 0)),
                "memory_mb": float(r.metrics.get("memory_mb", 0.0)),
            }
            candidate_metrics[r.strategy_name] = metrics

        pareto_optimal: List[str] = []
        candidates = list(candidate_metrics.keys())

        for name in candidates:
            is_dominated = False
            for other_name in candidates:
                if name == other_name:
                    continue
                if dominates(candidate_metrics[other_name], candidate_metrics[name], criteria):
                    is_dominated = True
                    break
            if not is_dominated:
                pareto_optimal.append(name)

        return pareto_optimal

    @staticmethod
    def generate_comparison_summary(results: List[StrategyEvaluationResult]) -> Dict[str, Any]:
        """Produce breakdown of trade-offs between evaluated candidates."""
        summary = {}
        for r in results:
            summary[r.strategy_name] = {
                "status": "success" if r.success else "failed",
                "duration_sec": round(r.duration_sec, 4),
                "exit_code": r.exit_code,
                "metrics": r.metrics,
                "artifacts_count": len(r.artifacts),
            }
        return summary
