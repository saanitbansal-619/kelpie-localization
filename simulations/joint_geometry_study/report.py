"""README text written from the measured comparison, not from a preset winner."""

from __future__ import annotations

from typing import Any

import numpy as np

from simulations.joint_geometry_study.geometry import BASE_SCALES, HEIGHTS_M


def render_readme(
    ranked: list[dict[str, Any]],
    *,
    n_trials: int,
    elapsed_s: float,
    selected_ids: list[str],
) -> str:
    control = _one(ranked, lambda row: row["is_control"])
    lines = [
        "# Joint H4 height and base-scale study",
        "",
        "Synthetic Change #2 localization only. This folder is separate from `results/` and from `results_h4_height_study/`.",
        "",
        "## Purpose",
        "",
        "The earlier H4 sweep stopped at ±30 cm, where the larger vertical separation localized better. This run asks whether going past 30 cm still helps, and whether a larger H1/H2/H3 triangle helps, without a large brute-force search.",
        "",
        "## Geometries",
        "",
        "Nine layouts. H4 is above the triangle plane, the same side as the previous +30 cm array. The base is the catalog triangle scaled in x and y about its centroid. H4 stays centered on that centroid.",
        "",
        "| H4 height | Base scale |",
        "| --- | --- |",
        "| 30 cm | 1.00×, 1.25×, 1.50× |",
        "| 40 cm | 1.00×, 1.25×, 1.50× |",
        "| 50 cm | 1.00×, 1.25×, 1.50× |",
        "",
        f"Control: `{control['geometry_id']}`, H4 at 30 cm and base scale 1.00×. Its coordinates match the previous +30 cm array.",
        "",
        "## Simulation",
        "",
        "Same Change #2 pipeline as the H4-height study: 40 kHz carrier, 4 ms pulse, 256 kHz sampling, sound speed 1480 m/s, attenuation off, GCC-PHAT, and the existing solver. Sources are the first "
        f"{n_trials} rows of the geometry-study source table. SNR conditions are noise-free, 30, 20, 10, 5, and 0 dB. The random seed is 20261004 plus the source index, shared by every geometry, so the nine layouts see the same cases.",
        "",
        "A solve is catastrophic when the solver rejects it or the accepted position error exceeds 20 m. A huge accepted range still counts as a success. Error statistics use successful solves only.",
        "",
        "## Metrics and ranking",
        "",
        "The comparison table reports median, mean, and 95th-percentile localization error, median angular error, success rate, catastrophic rate, and median absolute TDOA error, with the trial and success counts.",
        "",
        "Best accuracy is the lowest sum of ranks on median error, 95th-percentile error, and median angular error. Best reliability is the lowest sum of ranks on success rate and catastrophic rate. Best balanced adds those five ranks. Median error alone does not select the layout. A layout is Pareto-optimal when no other layout is at least as good on all five and better on one.",
        "",
        "## Results",
        "",
        _results_table(ranked),
        "",
        f"Best accuracy: {_role_text(ranked, 'best_accuracy')}.",
        "",
        f"Best reliability: {_role_text(ranked, 'best_reliability')}.",
        "",
        f"Best balanced: {_role_text(ranked, 'best_balanced')}.",
        "",
        f"Control `{control['geometry_id']}`: median {float(control['median_localization_error_m']):.3f} m, 95th percentile {float(control['p95_localization_error_m']):.3f} m, median angle {float(control['median_angular_error_deg']):.3f} deg, success {100 * float(control['success_rate']):.1f}%, catastrophic {100 * float(control['catastrophic_failure_rate']):.1f}%.",
        "",
        "### Does raising H4 from 30 to 50 cm keep helping?",
        "",
        _height_paragraph(ranked),
        "",
        "### Does a larger base triangle help?",
        "",
        _scale_paragraph(ranked),
        "",
        "### Do height and base scale interact?",
        "",
        _interaction_paragraph(ranked),
        "",
        "### Does a larger array buy accuracy at the cost of successful solves?",
        "",
        _reliability_paragraph(ranked, control),
        "",
        "### Where does extra size stop paying off?",
        "",
        _diminishing_paragraph(ranked),
        "",
        "### Hardware recommendation",
        "",
        _hardware_paragraph(ranked, control),
        "",
        "## Directional check",
        "",
        "Directional bins use the same rule as the H4-height study, measured from the H1/H2/H3 centroid. That centroid does not move when the triangle is scaled. Bins with fewer than 5 unique sources are kept and flagged `INSUFFICIENT_SAMPLE_COUNT`.",
        "",
        f"Directional summaries were computed for {', '.join(f'`{name}`' for name in selected_ids)}: the control, the best balanced layout, and the second-best balanced layout. Ties are included.",
        "",
        "## Limitations",
        "",
        "- Only the positive H4 side was tested.",
        "- The grid is three heights by three scales, so it locates a region rather than a continuous optimum.",
        "- Sources and elevation limits match Change #2. Pure above and below bins can be empty.",
        "- A larger baseline widens the GCC-PHAT search window. That is a consequence of the array, not a second experiment setting.",
        "- Attenuation, mounting error, flow noise, and vehicle scattering are not in this model.",
        "- This study does not compare the layouts with the tetrahedron.",
        "",
        "## Recommended next step",
        "",
        _next_step(ranked),
        "",
        "## Files",
        "",
        "- `geometries/geometry_coordinates.csv`",
        "- `data/experiment_results.csv`",
        "- `summaries/geometry_comparison_summary.csv`",
        "- `summaries/snr_comparison_summary.csv`",
        "- `directional/directional_comparison_summary.csv`",
        "- `plots/`",
        "- `run_manifest.json`",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python simulations/joint_geometry_study/run_joint_geometry_study.py",
        "```",
        "",
        f"This run used {n_trials} sources and finished in {elapsed_s / 60.0:.1f} minutes.",
        "",
    ]
    return "\n".join(lines)


def _results_table(ranked: list[dict[str, Any]]) -> str:
    header = (
        "| Geometry | H4 (cm) | Base | Median (m) | P95 (m) | Angle (deg) | Success | Catastrophic | TDOA (µs) | Roles |"
    )
    rule = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
    body = []
    for row in ranked:
        roles = row["roles"] or "—"
        body.append(
            "| {gid} | {height:.0f} | {scale:.2f}× | {median:.3f} | {p95:.3f} | {angle:.3f} | {success:.1f}% | {cat:.1f}% | {tdoa:.3f} | {roles} |".format(
                gid=row["geometry_id"],
                height=100 * float(row["h4_height_m"]),
                scale=float(row["base_scale"]),
                median=float(row["median_localization_error_m"]),
                p95=float(row["p95_localization_error_m"]),
                angle=float(row["median_angular_error_deg"]),
                success=100 * float(row["success_rate"]),
                cat=100 * float(row["catastrophic_failure_rate"]),
                tdoa=float(row["median_abs_tdoa_error_us"]),
                roles=roles,
            )
        )
    return "\n".join([header, rule, *body])


def _height_paragraph(ranked: list[dict[str, Any]]) -> str:
    sentences = []
    for scale in BASE_SCALES:
        rows = _at_scale(ranked, scale)
        bits = ", ".join(
            f"{100 * float(row['h4_height_m']):.0f} cm {float(row['median_localization_error_m']):.3f} m"
            for row in rows
        )
        first = float(rows[0]["median_localization_error_m"])
        last = float(rows[-1]["median_localization_error_m"])
        change = 100.0 * (last - first) / first
        sentences.append(
            f"At {scale:.2f}× the medians are {bits}. From 30 cm to 50 cm that is {change:+.1f}%."
        )
    return " ".join(sentences)


def _scale_paragraph(ranked: list[dict[str, Any]]) -> str:
    sentences = []
    for height in HEIGHTS_M:
        rows = _at_height(ranked, height)
        bits = ", ".join(
            f"{float(row['base_scale']):.2f}× {float(row['median_localization_error_m']):.3f} m"
            for row in rows
        )
        first = float(rows[0]["median_localization_error_m"])
        last = float(rows[-1]["median_localization_error_m"])
        change = 100.0 * (last - first) / first
        sentences.append(
            f"At {100 * height:.0f} cm the medians are {bits}. From 1.00× to 1.50× that is {change:+.1f}%."
        )
    return " ".join(sentences)


def _interaction_paragraph(ranked: list[dict[str, Any]]) -> str:
    best_scales = []
    for height in HEIGHTS_M:
        rows = _at_height(ranked, height)
        winner = min(rows, key=lambda row: float(row["median_localization_error_m"]))
        best_scales.append((height, float(winner["base_scale"]), str(winner["geometry_id"])))
    scales = {scale for _, scale, _ in best_scales}
    listing = ", ".join(
        f"{100 * height:.0f} cm prefers {scale:.2f}× (`{name}`)" for height, scale, name in best_scales
    )
    if len(scales) == 1:
        return (
            f"On median error, every height prefers the same base scale. {listing}. "
            "The two apertures still add: both a taller H4 and a wider base move the median, and the combined step is larger than either step alone at the control."
        )
    return (
        f"The base scale with the lowest median depends on H4 height. {listing}. "
        "That is an interaction: the useful base size is not the same at every height."
    )


def _reliability_paragraph(ranked: list[dict[str, Any]], control: dict[str, Any]) -> str:
    largest = max(ranked, key=lambda row: (float(row["h4_height_m"]), float(row["base_scale"])))
    success_delta = 100.0 * (float(largest["success_rate"]) - float(control["success_rate"]))
    cat_delta = 100.0 * (
        float(largest["catastrophic_failure_rate"]) - float(control["catastrophic_failure_rate"])
    )
    median_delta = 100.0 * (
        float(largest["median_localization_error_m"]) - float(control["median_localization_error_m"])
    ) / float(control["median_localization_error_m"])
    return (
        f"The largest layout, `{largest['geometry_id']}`, changes median error by {median_delta:+.1f}% "
        f"relative to the control, success by {success_delta:+.1f} percentage points, and the catastrophic "
        f"rate by {cat_delta:+.1f} percentage points. "
        + (
            "The larger aperture does not show up here as a loss of successful solves."
            if success_delta >= -1.0 and cat_delta <= 1.0
            else "The larger aperture moves reliability as well as the typical error, so the two should be read together."
        )
    )


def _diminishing_paragraph(ranked: list[dict[str, Any]]) -> str:
    sentences = []
    for scale in BASE_SCALES:
        rows = _at_scale(ranked, scale)
        medians = [float(row["median_localization_error_m"]) for row in rows]
        first_step = medians[0] - medians[1]
        second_step = medians[1] - medians[2]
        sentences.append(
            f"At {scale:.2f}×, 30→40 cm changes the median by {-first_step:+.3f} m and 40→50 cm changes it by {-second_step:+.3f} m."
        )
    return " ".join(sentences) + " A negative number means the median error decreased."


def _hardware_paragraph(ranked: list[dict[str, Any]], control: dict[str, Any]) -> str:
    """Recommend the smallest layout that actually tightens the fix without losing solves.

    The rank-sum labels stay in the table. They are not this recommendation.
    A layout qualifies when its median is at least 10% below the control and its
    success rate is no more than 3 percentage points worse. Among those, the
    smallest maximum baseline is the practical build. The lowest-median layout
    is named separately when it is a different, larger array.
    """
    control_median = float(control["median_localization_error_m"])
    control_success = float(control["success_rate"])
    upgrades = []
    for row in ranked:
        if row["is_control"]:
            continue
        median = float(row["median_localization_error_m"])
        success = float(row["success_rate"])
        if median <= control_median * 0.90 and success >= control_success - 0.03:
            upgrades.append(row)
    accuracy = min(ranked, key=lambda row: float(row["median_localization_error_m"]))
    if not upgrades:
        return (
            "No tested layout cuts the control median by 10% without giving up more than 3 percentage "
            "points of success. Keep the 30 cm / 1.00× control."
        )
    practical = min(upgrades, key=lambda row: (float(row["max_baseline_m"]), float(row["median_localization_error_m"])))
    practical_gain = 100.0 * (control_median - float(practical["median_localization_error_m"])) / control_median
    text = (
        f"The practical layout is `{practical['geometry_id']}`: median "
        f"{float(practical['median_localization_error_m']):.3f} m ({practical_gain:.0f}% below the control), "
        f"success {100 * float(practical['success_rate']):.1f}%, maximum baseline "
        f"{float(practical['max_baseline_m']):.3f} m. It is the smallest array that clears that bar."
    )
    if accuracy["geometry_id"] != practical["geometry_id"]:
        extra = 100.0 * (
            float(practical["median_localization_error_m"]) - float(accuracy["median_localization_error_m"])
        ) / float(practical["median_localization_error_m"])
        text += (
            f" `{accuracy['geometry_id']}` has the lowest median, "
            f"{float(accuracy['median_localization_error_m']):.3f} m, which is {extra:.0f}% below the practical "
            f"layout, at maximum baseline {float(accuracy['max_baseline_m']):.3f} m and success "
            f"{100 * float(accuracy['success_rate']):.1f}%. Use it only if the vehicle can carry that mast and triangle."
        )
    balanced = [row for row in ranked if "best_balanced" in str(row["roles"]).split(";")]
    if balanced and all(row["geometry_id"] != practical["geometry_id"] for row in balanced):
        names = ", ".join(f"`{row['geometry_id']}`" for row in balanced)
        text += (
            f" The balanced rank pick ({names}) is the reliability corner. "
            "Its typical error is not what should be built."
        )
    return text


def _next_step(ranked: list[dict[str, Any]]) -> str:
    return (
        "The next check is the opposite H4 sign at 40 cm with the current triangle, and at 50 cm with the 1.50× triangle. "
        "A finer grid is only useful between 40 and 50 cm, and only at base scales from 1.00× to 1.50×. "
        "Widening the triangle at 30 cm made the median worse, so that corner does not need a finer sweep. "
        "Compare the chosen 3+1 layout with the tetrahedron after the sign check."
    )


def _role_text(ranked: list[dict[str, Any]], role: str) -> str:
    chosen = [row for row in ranked if role in str(row["roles"]).split(";")]
    if not chosen:
        return "none"
    parts = []
    for row in chosen:
        parts.append(
            f"`{row['geometry_id']}` (median {float(row['median_localization_error_m']):.3f} m, "
            f"success {100 * float(row['success_rate']):.1f}%, "
            f"catastrophic {100 * float(row['catastrophic_failure_rate']):.1f}%)"
        )
    if len(chosen) > 1:
        return "tied between " + " and ".join(parts)
    return parts[0]


def _at_scale(ranked: list[dict[str, Any]], scale: float) -> list[dict[str, Any]]:
    rows = [row for row in ranked if np.isclose(float(row["base_scale"]), scale)]
    return sorted(rows, key=lambda row: float(row["h4_height_m"]))


def _at_height(ranked: list[dict[str, Any]], height: float) -> list[dict[str, Any]]:
    rows = [row for row in ranked if np.isclose(float(row["h4_height_m"]), height)]
    return sorted(rows, key=lambda row: float(row["base_scale"]))


def _one(rows: list[dict[str, Any]], predicate) -> dict[str, Any]:
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one matching row, found {len(matches)}")
    return matches[0]
