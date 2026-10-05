"""Summaries, directional tables, and height rankings.

Localization statistics use successful solves only. A rejected solve is not
given zero error. A trial is catastrophic when the solver rejects it or the
accepted position error is above 20 m. Success rate and catastrophic rate
are therefore not complements: a huge accepted range counts as both.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from simulations.h4_height_study.directions import INSUFFICIENT, MIN_SOURCES, is_sufficient

CATASTROPHIC_ERROR_M = 20.0


def success(row: dict[str, Any]) -> bool:
    value = row["success"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def noise_free(row: dict[str, Any]) -> bool:
    value = row["noise_free"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def finite(row: dict[str, Any], key: str) -> float:
    value = row.get(key, "")
    if value is None or value == "":
        return float("nan")
    return float(value)


def is_catastrophic(row: dict[str, Any]) -> bool:
    if not success(row):
        return True
    error = finite(row, "localization_error_m")
    return (not np.isfinite(error)) or error > CATASTROPHIC_ERROR_M


def _position_errors(rows: list[dict[str, Any]]) -> np.ndarray:
    values = [finite(row, "localization_error_m") for row in rows if success(row)]
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def _angular_errors(rows: list[dict[str, Any]]) -> np.ndarray:
    values = [finite(row, "angular_error_deg") for row in rows if success(row)]
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def _tdoa_errors(rows: list[dict[str, Any]]) -> np.ndarray:
    values: list[float] = []
    for row in rows:
        for key in ("tdoa_err_h1_us", "tdoa_err_h2_us", "tdoa_err_h3_us"):
            if key not in row:
                continue
            value = finite(row, key)
            if np.isfinite(value):
                values.append(abs(value))
    return np.asarray(values, dtype=float)


def _stat(values: np.ndarray, kind: str) -> float:
    if values.size == 0:
        return float("nan")
    if kind == "mean":
        return float(np.mean(values))
    if kind == "median":
        return float(np.median(values))
    if kind == "std":
        if values.size < 2:
            return float("nan")
        return float(np.std(values, ddof=1))
    if kind == "rmse":
        return float(np.sqrt(np.mean(np.square(values))))
    if kind == "p95":
        return float(np.percentile(values, 95))
    if kind == "max":
        return float(np.max(values))
    raise KeyError(kind)


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, float]:
    position = _position_errors(rows)
    angular = _angular_errors(rows)
    tdoa = _tdoa_errors(rows)
    n_trials = len(rows)
    n_successful = sum(1 for row in rows if success(row))
    n_catastrophic = sum(1 for row in rows if is_catastrophic(row))
    return {
        "n_trials": n_trials,
        "n_successful": n_successful,
        "mean_localization_error_m": _stat(position, "mean"),
        "median_localization_error_m": _stat(position, "median"),
        "rmse_localization_error_m": _stat(position, "rmse"),
        "std_localization_error_m": _stat(position, "std"),
        "p95_localization_error_m": _stat(position, "p95"),
        "max_localization_error_m": _stat(position, "max"),
        "mean_angular_error_deg": _stat(angular, "mean"),
        "median_angular_error_deg": _stat(angular, "median"),
        "success_rate": (n_successful / n_trials) if n_trials else float("nan"),
        "catastrophic_failure_rate": (n_catastrophic / n_trials) if n_trials else float("nan"),
        "mean_abs_tdoa_error_us": _stat(tdoa, "mean"),
        "median_abs_tdoa_error_us": _stat(tdoa, "median"),
    }


def snr_label(row: dict[str, Any]) -> str:
    if noise_free(row):
        return "noise-free"
    return f"{float(row['snr_db']):.0f} dB"


def height_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per H4 height and SNR, in first-seen order."""
    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["h4_name"]), snr_label(row))
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(row)
    summary = []
    for key in order:
        selected = grouped[key]
        record = {
            "h4_name": selected[0]["h4_name"],
            "h4_height_m": float(selected[0]["h4_height_m"]),
            "h4_z_m": float(selected[0]["h4_z_m"]),
            "snr_label": key[1],
            "noise_free": "true" if noise_free(selected[0]) else "false",
            "snr_db": float("nan") if noise_free(selected[0]) else float(selected[0]["snr_db"]),
        }
        record.update(summarize_group(selected))
        summary.append(record)
    return summary


def source_key(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        round(float(row["source_x_m"]), 6),
        round(float(row["source_y_m"]), 6),
        round(float(row["source_z_m"]), 6),
    )


def directional_table(rows: list[dict[str, Any]], study: str) -> list[dict[str, Any]]:
    """Every height and every direction that appears. Small bins stay, flagged."""
    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["h4_name"]), str(row["direction"]))
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(row)
    table = []
    for key in order:
        selected = grouped[key]
        stats = summarize_group(selected)
        n_sources = len({source_key(row) for row in selected})
        flag = "" if is_sufficient(n_sources) else INSUFFICIENT
        table.append(
            {
                "study": study,
                "h4_name": selected[0]["h4_name"],
                "h4_height_m": float(selected[0]["h4_height_m"]),
                "direction": key[1],
                "n_sources": n_sources,
                "flag": flag,
                **stats,
            }
        )
    return table


def source_direction_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unique sources per direction. The draw does not depend on H4 height."""
    first_height = str(rows[0]["h4_name"])
    selected = [row for row in rows if str(row["h4_name"]) == first_height and noise_free(row)]
    if not selected:
        selected = [row for row in rows if str(row["h4_name"]) == first_height]
        seen_trial = set()
        unique_rows = []
        for row in selected:
            if row["trial"] in seen_trial:
                continue
            seen_trial.add(row["trial"])
            unique_rows.append(row)
        selected = unique_rows
    counts: dict[str, int] = {}
    for row in selected:
        counts[str(row["direction"])] = counts.get(str(row["direction"]), 0) + 1
    return [
        {
            "direction": direction,
            "n_sources": count,
            "flag": "" if is_sufficient(count) else INSUFFICIENT,
        }
        for direction, count in counts.items()
    ]


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


def ranking_rows(
    pooled: list[dict[str, Any]],
    *,
    study: str,
    scope: str,
    include_tdoa: bool,
) -> list[dict[str, Any]]:
    """Rank heights within one scope. Lowest rank_sum is best."""
    metrics = [
        ("median_localization_error_m", False, "rank_median"),
        ("p95_localization_error_m", False, "rank_p95"),
        ("median_angular_error_deg", False, "rank_angular"),
        ("success_rate", True, "rank_success"),
        ("catastrophic_failure_rate", False, "rank_catastrophic"),
        ("directional_std_m", False, "rank_consistency"),
    ]
    if include_tdoa:
        metrics.append(("median_abs_tdoa_error_us", False, "rank_tdoa"))
    rank_columns: dict[str, list[int]] = {}
    for key, higher, rank_name in metrics:
        rank_columns[rank_name] = _rank([float(row.get(key, float("nan"))) for row in pooled], higher)
    ranked = []
    for index, row in enumerate(pooled):
        record = dict(row)
        record["study"] = study
        record["scope"] = scope
        total = 0
        for _, _, rank_name in metrics:
            record[rank_name] = rank_columns[rank_name][index]
            total += rank_columns[rank_name][index]
        if not include_tdoa:
            record["rank_tdoa"] = ""
            record["median_abs_tdoa_error_us"] = row.get("median_abs_tdoa_error_us", float("nan"))
        record["rank_sum"] = total
        ranked.append(record)
    order = sorted(range(len(ranked)), key=lambda index: (ranked[index]["rank_sum"], ranked[index]["h4_height_m"]))
    for place, index in enumerate(order, start=1):
        ranked[index]["rank_overall"] = place
    return ranked


def best_direction_rows(directional: list[dict[str, Any]], study: str) -> list[dict[str, Any]]:
    """Lowest median error per direction. Small bins are kept and not awarded a winner."""
    directions = list(dict.fromkeys(row["direction"] for row in directional if row["study"] == study))
    chosen = []
    for direction in directions:
        group = [row for row in directional if row["study"] == study and row["direction"] == direction]
        n_sources = int(group[0]["n_sources"])
        record: dict[str, Any] = {
            "study": study,
            "direction": direction,
            "n_sources": n_sources,
            "n_trials": int(group[0]["n_trials"]),
            "flag": "" if is_sufficient(n_sources) else INSUFFICIENT,
            "best_h4_name": "",
            "best_h4_height_m": float("nan"),
            "median_localization_error_m": float("nan"),
            "success_rate": float("nan"),
            "median_angular_error_deg": float("nan"),
            "note": "",
        }
        if not is_sufficient(n_sources):
            chosen.append(record)
            continue
        eligible = [row for row in group if np.isfinite(float(row["median_localization_error_m"]))]
        if not eligible:
            record["flag"] = INSUFFICIENT
            record["note"] = "no successful localizations"
            chosen.append(record)
            continue
        eligible.sort(key=lambda row: (float(row["median_localization_error_m"]), -float(row["success_rate"])))
        best = eligible[0]
        record.update(
            {
                "best_h4_name": best["h4_name"],
                "best_h4_height_m": float(best["h4_height_m"]),
                "median_localization_error_m": float(best["median_localization_error_m"]),
                "success_rate": float(best["success_rate"]),
                "median_angular_error_deg": float(best["median_angular_error_deg"]),
            }
        )
        if len(eligible) > 1:
            second = float(eligible[1]["median_localization_error_m"])
            first = float(best["median_localization_error_m"])
            if first > 0.0 and abs(second - first) / first < 0.10:
                record["note"] = f"within 10% of {eligible[1]['h4_name']}"
        chosen.append(record)
    return chosen


def positive_negative_rows(pooled: list[dict[str, Any]], study: str) -> list[dict[str, Any]]:
    """Equal-magnitude pairs. Difference is positive-height minus negative-height."""
    by_height = {round(float(row["h4_height_m"]), 5): row for row in pooled}
    magnitudes = (0.05, 0.10, 0.15, 0.20, 0.30)
    rows = []
    for magnitude in magnitudes:
        negative = by_height[round(-magnitude, 5)]
        positive = by_height[round(magnitude, 5)]
        rows.append(
            {
                "study": study,
                "magnitude_m": magnitude,
                "neg_name": negative["h4_name"],
                "pos_name": positive["h4_name"],
                "neg_median_m": float(negative["median_localization_error_m"]),
                "pos_median_m": float(positive["median_localization_error_m"]),
                "median_difference_pos_minus_neg_m": (
                    float(positive["median_localization_error_m"]) - float(negative["median_localization_error_m"])
                ),
                "neg_success_rate": float(negative["success_rate"]),
                "pos_success_rate": float(positive["success_rate"]),
                "neg_p95_m": float(negative["p95_localization_error_m"]),
                "pos_p95_m": float(positive["p95_localization_error_m"]),
                "neg_catastrophic_failure_rate": float(negative["catastrophic_failure_rate"]),
                "pos_catastrophic_failure_rate": float(positive["catastrophic_failure_rate"]),
                "neg_median_angular_deg": float(negative["median_angular_error_deg"]),
                "pos_median_angular_deg": float(positive["median_angular_error_deg"]),
                "neg_median_tdoa_us": float(negative.get("median_abs_tdoa_error_us", float("nan"))),
                "pos_median_tdoa_us": float(positive.get("median_abs_tdoa_error_us", float("nan"))),
            }
        )
    return rows


def pooled_height_record(
    rows: list[dict[str, Any]],
    directional: list[dict[str, Any]],
    directions: tuple[str, ...] | None,
) -> dict[str, Any]:
    """One height, optionally restricted to a direction set."""
    if directions is not None:
        allowed = set(directions)
        rows = [row for row in rows if str(row["direction"]) in allowed]
    stats = summarize_group(rows)
    height_name = str(rows[0]["h4_name"]) if rows else ""
    relevant = [
        row
        for row in directional
        if row["h4_name"] == height_name
        and row["flag"] != INSUFFICIENT
        and (directions is None or row["direction"] in set(directions or ()))
        and np.isfinite(float(row["median_localization_error_m"]))
    ]
    medians = np.asarray([float(row["median_localization_error_m"]) for row in relevant], dtype=float)
    stats["directional_std_m"] = float(np.std(medians, ddof=1)) if medians.size >= 2 else float("nan")
    if rows:
        stats["h4_name"] = rows[0]["h4_name"]
        stats["h4_height_m"] = float(rows[0]["h4_height_m"])
    return stats


MIN_SOURCES_FOR_DIRECTION = MIN_SOURCES
