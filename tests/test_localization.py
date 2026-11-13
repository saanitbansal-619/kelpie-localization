"""Tests for TDOA localization, degeneracy handling, and angular error."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geometry import get_geometry, list_geometries, true_tdoas_s
from src.localization import (
    angular_error_deg,
    classify_array,
    localize_from_tdoa,
)

# Design target used by the scope-validation pipeline. Not a surveyed array.
_STATED_HYDROPHONES_M = np.array(
    [
        [0.1443376, 0.0, 0.0],
        [-0.0721688, 0.125, 0.0],
        [-0.0721688, -0.125, 0.0],
        [0.0, 0.0, -0.400],
    ]
)


def test_geometry_classes_match_the_five_arrays() -> None:
    for array in list_geometries():
        assert classify_array(array.coordinates_m) == array.expected_class


def test_angular_error_known_cases() -> None:
    assert angular_error_deg([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(0.0, abs=1e-12)
    assert angular_error_deg([1.0, 0.0, 0.0], [2.0, 0.0, 0.0]) == pytest.approx(0.0, abs=1e-12)
    assert angular_error_deg([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(90.0, abs=1e-9)
    assert angular_error_deg([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]) == pytest.approx(180.0, abs=1e-9)
    assert angular_error_deg([1.0, 0.0, 0.0], [1.0, 1.0, 0.0]) == pytest.approx(45.0, abs=1e-9)


def test_angular_error_rejects_zero_vectors() -> None:
    with pytest.raises(ValueError):
        angular_error_deg([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])


def _assert_unique_recovery(hydrophones_m: np.ndarray, source: np.ndarray) -> None:
    result = localize_from_tdoa(hydrophones_m, true_tdoas_s(source, hydrophones_m))
    assert result.success, result.failure_reason
    assert result.failure_reason == ""
    assert np.all(np.isfinite(result.position_m))
    np.testing.assert_allclose(result.position_m, source, atol=1e-3)
    assert result.residual_rms_s == pytest.approx(0.0, abs=1e-8)


def _assert_ambiguous(hydrophones_m: np.ndarray, source: np.ndarray) -> None:
    result = localize_from_tdoa(hydrophones_m, true_tdoas_s(source, hydrophones_m))
    assert result.success is False
    assert result.failure_reason == "ambiguous_local_minima"
    assert not np.any(np.isfinite(result.position_m))
    assert not np.isfinite(result.residual_rms_s)


def test_volumetric_arrays_recover_a_known_source_from_true_tdoas() -> None:
    source = np.array([3.0, -1.2, 2.0])
    for array in list_geometries():
        if array.expected_class != "volumetric":
            continue
        if array.key == "three_plus_one":
            # This source has two exact positions on the catalog array.
            # Accepting either one would hide the other.
            _assert_ambiguous(array.coordinates_m, source)
            continue
        _assert_unique_recovery(array.coordinates_m, source)


def test_catalog_three_plus_one_exact_pair_is_ambiguous() -> None:
    source = np.array([3.0, -1.2, 2.0])
    other = np.array([2.00063723, -0.80861824, 1.32867305])
    phones = get_geometry("three_plus_one").coordinates_m
    source_tdoas = true_tdoas_s(source, phones)
    other_tdoas = true_tdoas_s(other, phones)
    assert np.max(np.abs(source_tdoas - other_tdoas)) < 1e-12
    assert float(np.linalg.norm(source - other)) > 1.0
    _assert_ambiguous(phones, source)
    _assert_ambiguous(phones, other)


def test_catalog_three_plus_one_unique_source_is_recovered() -> None:
    _assert_unique_recovery(get_geometry("three_plus_one").coordinates_m, np.array([2.0, 1.0, 1.5]))


def test_tetrahedron_recovers_an_unambiguous_source() -> None:
    _assert_unique_recovery(get_geometry("tetrahedral").coordinates_m, np.array([3.0, -1.2, 2.0]))


def test_tetrahedron_representative_source_has_a_second_exact_position() -> None:
    source = np.array([2.0, 1.0, 1.5])
    other = np.array([0.147737, 0.048324, 0.10067])
    phones = get_geometry("tetrahedral").coordinates_m
    assert np.max(np.abs(true_tdoas_s(source, phones) - true_tdoas_s(other, phones))) < 1e-9
    _assert_ambiguous(phones, source)


def test_stated_hardware_array_recovers_an_unambiguous_source() -> None:
    _assert_unique_recovery(_STATED_HYDROPHONES_M, np.array([0.3, -0.4, 1.2]))


def test_stated_hardware_array_reports_a_second_exact_position() -> None:
    source = np.array([3.0, -1.2, 2.0])
    other = np.array([0.13517389, -0.07829412, -0.01266544])
    source_tdoas = true_tdoas_s(source, _STATED_HYDROPHONES_M)
    other_tdoas = true_tdoas_s(other, _STATED_HYDROPHONES_M)
    assert np.max(np.abs(source_tdoas - other_tdoas)) < 1e-9
    _assert_ambiguous(_STATED_HYDROPHONES_M, source)


def test_degenerate_arrays_do_not_return_a_position() -> None:
    source = np.array([2.0, 1.0, 1.5])
    for array in list_geometries():
        if array.expected_class == "volumetric":
            continue
        tdoas = true_tdoas_s(source, array.coordinates_m)
        result = localize_from_tdoa(array.coordinates_m, tdoas)
        assert result.success is False
        assert result.failure_reason.startswith("geometric_degeneracy_")
        assert not np.any(np.isfinite(result.position_m))
        assert not np.isfinite(result.residual_rms_s)
        # A silent "success" near the true source would hide the degeneracy.
        assert result.geometry_class == array.expected_class
