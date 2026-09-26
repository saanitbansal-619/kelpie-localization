"""Tests for TDOA localization, degeneracy handling, and angular error."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geometry import list_geometries, true_tdoas_s
from src.localization import (
    angular_error_deg,
    classify_array,
    localize_from_tdoa,
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


def test_volumetric_arrays_recover_a_known_source_from_true_tdoas() -> None:
    source = np.array([3.0, -1.2, 2.0])
    for array in list_geometries():
        if array.expected_class != "volumetric":
            continue
        tdoas = true_tdoas_s(source, array.coordinates_m)
        result = localize_from_tdoa(array.coordinates_m, tdoas)
        assert result.success, result.failure_reason
        assert result.failure_reason == ""
        assert np.all(np.isfinite(result.position_m))
        np.testing.assert_allclose(result.position_m, source, atol=1e-3)
        assert result.residual_rms_s == pytest.approx(0.0, abs=1e-8)


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
