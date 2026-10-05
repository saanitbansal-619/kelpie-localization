"""Aggregate metrics and the accuracy / reliability ranking.

Localization statistics use successful solves only. A rejected solve is not
given zero error. Catastrophic means a rejected solve or an accepted error
above 20 m, the same rule as the H4-height study.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from simulations.h4_height_study.directions import INSUFFICIENT, is_sufficient
from simulations.h4_height_study.metrics import snr_label, source_key, summarize_group

ACCURACY_KEYS = (
    ("median_localization_error_m", False),
    ("p95_localization_error_m", False),
    ("median_angular_error_deg", False),
)
RELIABILITY_KEYS = (
    ("success_rate", True),
    ("catastrophic_failure_rate", False),
)


def pooled_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per geometry, all SNR conditions pooled, in first-seen order."""
    return _grouped(rows, key_of=lambda row: str(row["geometry_id"]))


def snr_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per geometry and SNR."""
    return _grouped(
        rows,
        key_of=lambda row: (str(row["geometry_id"]), snr_label(row)),
        include_snr=True,
    )


def directional_summaries(rows: list[dict[str, Any]], selected_ids: set[str]) -> list[dict[str, Any]]:
    """Direction bins for the selected geometries. Small bins stay, flagged."""
    chosen = [row for row in rows if str(row["geometry_id"]) in selected_ids]
    table = _grouped(
        chosen,
        key_of=lambda row: (str(row["geometry_id"]), str(row["direction"])),
        include_direction=True,
    )
    for record in table:
        n_sources = int(record["n_sources"])
        record["flag"] = "" if is_sufficient(n_sources) else INSUFFICIENT
    return table


def rank_layouts(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add accuracy, reliability, and balanced ranks. 1 is best.

    Accuracy is the sum of competition ranks on median error, 95th percentile
    error, and median angular error. Reliability is the sum of ranks on
    success rate and catastrophic rate. Balanced is the sum of those five
    ranks. Median error alone does not pick the winner.
    """
    ranked = [dict(row) for row in summary]
    accuracy_parts = []
    reliability_parts = []
    for key, higher in ACCURACY_KEYS:
        part = _rank([float(row[key]) for row in ranked], higher)
        accuracy_parts.append(part)
        ranked_name = {
            "median_localization_error_m": "rank_median",
            "p95_localization_error_m": "rank_p95",
            "median_angular_error_deg": "rank_angular",
        }[key]
        for index, value in enumerate(part):
            ranked[index][ranked_name] = value
    for key, higher in RELIABILITY_KEYS:
        part = _rank([float(row[key]) for row in ranked], higher)
        reliability_parts.append(part)
        ranked_name = "rank_success" if key == "success_rate" else "rank_catastrophic"
        for index, value in enumerate(part):
            ranked[index][ranked_name] = value
    accuracy = [sum(parts) for parts in zip(*accuracy_parts)]
    reliability = [sum(parts) for parts in zip(*reliability_parts)]
    accuracy_rank = _rank([float(value) for value in accuracy], higher_better=False)
    reliability_rank = _rank([float(value) for value in reliability], higher_better=False)
    balanced = [left + right for left, right in zip(accuracy, reliability)]
    balanced_rank = _rank([float(value) for value in balanced], higher_better=False)
    for index, row in enumerate(ranked):
        row["accuracy_rank_sum"] = accuracy[index]
        row["reliability_rank_sum"] = reliability[index]
        row["balanced_rank_sum"] = balanced[index]
        row["rank_accuracy"] = accuracy_rank[index]
        row["rank_reliability"] = reliability_rank[index]
        row["rank_balanced"] = balanced_rank[index]
        row["pareto"] = _is_pareto(index, ranked)
    _assign_roles(ranked)
    return ranked


def selected_geometry_ids(ranked: list[dict[str, Any]]) -> list[str]:
    """Control, best balanced, and second-best balanced. Ties stay in the set."""
    best = _min_rank(ranked, "rank_balanced")
    second_values = [int(row["rank_balanced"]) for row in ranked if int(row["rank_balanced"]) > best]
    second = min(second_values) if second_values else best
    chosen = []
    for row in ranked:
        if row["is_control"] or int(row["rank_balanced"]) in {best, second}:
            if row["geometry_id"] not in chosen:
                chosen.append(str(row["geometry_id"]))
    return chosen


def _grouped(
    rows: list[dict[str, Any]],
    key_of,
    *,
    include_snr: bool = False,
    include_direction: bool = False,
) -> list[dict[str, Any]]:
    order = []
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        key = key_of(row)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(row)
    table = []
    for key in order:
        selected = grouped[key]
        first = selected[0]
        record = {
            "geometry_id": str(first["geometry_id"]),
            "h4_height_m": float(first["h4_height_m"]),
            "base_scale": float(first["base_scale"]),
            "is_control": bool(first["is_control"]),
            "triangle_side_m": float(first["triangle_side_m"]),
            "max_baseline_m": float(first["max_baseline_m"]),
        }
        if include_direction:
            record["direction"] = str(first["direction"])
            record["n_sources"] = len({source_key(row) for row in selected})
        if include_snr:
            label = snr_label(first)
            record["snr_label"] = label
            record["noise_free"] = "true" if label == "noise-free" else "false"
            record["snr_db"] = float("nan") if label == "noise-free" else float(first["snr_db"])
        record.update(summarize_group(selected))
        table.append(record)
    return table


def _assign_roles(ranked: list[dict[str, Any]]) -> None:
    for row in ranked:
        roles = []
        if row["is_control"]:
            roles.append("control")
        if int(row["rank_accuracy"]) == 1:
            roles.append("best_accuracy")
        if int(row["rank_reliability"]) == 1:
            roles.append("best_reliability")
        if int(row["rank_balanced"]) == 1:
            roles.append("best_balanced")
        row["roles"] = ";".join(roles)


def _is_pareto(index: int, rows: list[dict[str, Any]]) -> bool:
    for other, candidate in enumerate(rows):
        if other == index:
            continue
        if _dominates(candidate, rows[index]):
            return False
    return True


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """True when left is at least as good on every listed metric and better on one."""
    comparisons = []
    for key, higher in ACCURACY_KEYS + RELIABILITY_KEYS:
        left_value = float(left[key])
        right_value = float(right[key])
        if not np.isfinite(left_value) or not np.isfinite(right_value):
            return False
        better = left_value > right_value if higher else left_value < right_value
        worse = left_value < right_value if higher else left_value > right_value
        if worse and not np.isclose(left_value, right_value, rtol=0.0, atol=1e-12):
            return False
        comparisons.append(better and not np.isclose(left_value, right_value, rtol=0.0, atol=1e-12))
    return any(comparisons)


def _min_rank(rows: list[dict[str, Any]], key: str) -> int:
    return min(int(row[key]) for row in rows)


def _rank(values: list[float], higher_better: bool) -> list[int]:
    """Competition ranks. NaNs rank last. 1 is best."""
    indexed = list(enumerate(values))

    def sort_key(item: tuple[int, float]) -> tuple[int, float]:
        value = item[1]
        if not np.isfinite(value):
            return (1, 0.0)
        return (0, -value if higher_better else value)

    ordered = sorted(indexed, key=sort_key)
    ranks = [0] * len(values)
    position = 1
    for offset, (index, value) in enumerate(ordered):
        if offset > 0 and _same(value, ordered[offset - 1][1]):
            ranks[index] = ranks[ordered[offset - 1][0]]
        else:
            ranks[index] = position
        position += 1
    return ranks


def _same(left: float, right: float) -> bool:
    if not np.isfinite(left) and not np.isfinite(right):
        return True
    return bool(np.isclose(left, right, rtol=0.0, atol=1e-12))
