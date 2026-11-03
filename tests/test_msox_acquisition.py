"""Laptop tests for MSOX2014A parsing, scaling, and one-record alignment.

Nothing here talks to a scope. Instrument behavior stays unverified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquisition.cli import main
from acquisition.errors import ScopeIdentityError, ScopeInstrumentError, ScopeProtocolError, ScopeTimeoutError
from acquisition.mock import DEMO_CODES, open_mock
from acquisition.scope import parse_idn
from acquisition.waveform import (
    WaveformPreamble,
    decode_waveform,
    encode_definite_block,
    load_npz,
    parse_definite_block,
    parse_preamble,
    scale_codes,
)


def _preamble(**overrides) -> WaveformPreamble:
    fields = dict(
        format_code=0,
        type_code=0,
        points=4,
        count=1,
        x_increment=1e-6,
        x_origin=-4e-6,
        x_reference=0,
        y_increment=0.01,
        y_origin=0.0,
        y_reference=128,
        raw="test",
    )
    fields.update(overrides)
    return WaveformPreamble(**fields)


def test_scale_codes_matches_programmers_guide_formula() -> None:
    preamble = _preamble()
    codes = np.array([128, 130, 108], dtype=np.float64)
    volts = scale_codes(codes, preamble)
    expected = (codes - 128.0) * 0.01
    assert np.allclose(volts, expected)


def test_word_byte_order_and_unsigned() -> None:
    preamble = _preamble(format_code=1, points=1, y_increment=1.0, y_reference=0)
    little = decode_waveform(encode_definite_block(b"\x02\x01"), preamble, unsigned=True, byte_order="LSBFirst")
    big = decode_waveform(encode_definite_block(b"\x01\x02"), preamble, unsigned=True, byte_order="MSBFirst")
    assert little == pytest.approx(0x0102)
    assert big == pytest.approx(0x0102)
    signed = decode_waveform(encode_definite_block(b"\xff"), _preamble(points=1), unsigned=False, byte_order="LSBFirst")
    assert signed == pytest.approx((np.int8(-1) - 128) * 0.01)


def test_preamble_field_order_and_ascii_format_codes() -> None:
    text = "0,0,8,1,1.0E-6,-4.0E-6,0,1.0E-2,0.0,128"
    preamble = parse_preamble(text)
    assert preamble.format_code == 0
    assert preamble.type_code == 0
    assert preamble.points == 8
    assert preamble.count == 1
    assert preamble.x_increment == pytest.approx(1e-6)
    assert preamble.x_origin == pytest.approx(-4e-6)
    assert preamble.x_reference == 0
    assert preamble.y_increment == pytest.approx(0.01)
    assert preamble.y_origin == pytest.approx(0.0)
    assert preamble.y_reference == 128
    for code in (2, 4):
        ascii_preamble = parse_preamble(f"{code},2,2,1,1e-6,0,0,1,0,0")
        payload = encode_definite_block(b"1.5,9.9e37")
        values = decode_waveform(payload, ascii_preamble, unsigned=True, byte_order="LSBFirst")
        assert values[0] == pytest.approx(1.5)
        assert np.isnan(values[1])


def test_preamble_strips_unverified_header_and_rejects_short_blocks() -> None:
    parsed = parse_preamble(":WAV:PRE 0,1,4,1,1e-6,0,0,1,0,0")
    assert parsed.header_stripped
    assert parsed.type_name == "PEAK"
    with pytest.raises(ScopeProtocolError):
        decode_waveform(encode_definite_block(b"\x00\x00"), parsed, unsigned=True, byte_order="LSBFirst")
    with pytest.raises(ScopeProtocolError):
        parse_definite_block(b"#800000004\x00\x00")
    assert parse_definite_block(b"#14\x01\x02\x03\x04\n") == b"\x01\x02\x03\x04"


def test_mock_capture_is_one_record_and_preserves_metadata() -> None:
    with open_mock() as scope:
        record = scope.capture()
    assert scope.session.closed
    assert scope.session.digitize_count == 1
    digitize = [cmd for cmd in record.metadata["scpi_commands"] if cmd.startswith(":DIGitize")]
    assert digitize == [":DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4"]
    data_at = [i for i, cmd in enumerate(record.metadata["scpi_commands"]) if cmd == ":WAVeform:DATA?"]
    digitize_at = record.metadata["scpi_commands"].index(digitize[0])
    assert len(data_at) == 4
    assert digitize_at < data_at[0]
    expected = (DEMO_CODES.astype(np.float64) - 128.0) * 0.01
    assert record.samples.shape == (4, 8)
    assert np.allclose(record.samples, expected)
    assert np.allclose(record.time_s, np.arange(8) * 1e-6)
    assert record.sample_interval_s == pytest.approx(1e-6)
    assert record.channel_ids == ("CH1", "CH2", "CH3", "CH4")
    assert record.hydrophone_ids == ("H1", "H2", "H3", "H4")
    assert not np.allclose(record.samples[0], record.samples[1])
    assert record.metadata["backend"] == "mock"
    assert record.metadata["instrument_verified"] is False
    assert record.metadata["streaming"] == "not implemented"
    assert record.metadata["segmented_memory"] == "not used"
    assert record.metadata["geometry"]["h4_relative_to_upper_triangle_m"] == -0.400
    assert record.metadata["geometry"]["volts_to_pascals"] == "TBD"
    assert record.metadata["idn"]["model"] == "MSOX2014A"
    assert record.metadata["acquisition_id"]


def test_channel_length_and_timebase_must_match() -> None:
    with pytest.raises(ScopeProtocolError):
        with open_mock(channel_points=(8, 4, 8, 8)) as scope:
            scope.capture()
    with pytest.raises(ScopeProtocolError):
        with open_mock(channel_x_scale=(1.0, 2.0, 1.0, 1.0)) as scope:
            scope.capture()


def test_timeout_and_instrument_error_close_the_session() -> None:
    scope = open_mock(timeout_command="*IDN?")
    with pytest.raises(ScopeTimeoutError):
        with scope:
            scope.capture()
    assert scope.session.closed

    scope = open_mock(error_after_digitize='-113,"Undefined header"')
    with pytest.raises(ScopeInstrumentError):
        with scope:
            scope.capture()
    assert scope.session.closed


def test_identity_rejects_other_models() -> None:
    with pytest.raises(ScopeIdentityError):
        parse_idn("KEYSIGHT TECHNOLOGIES,DSOX1102G,SN1,01.00")
    identity = parse_idn("AGILENT TECHNOLOGIES,MSOX2014A,SN1,02.00")
    assert identity["serial"] == "SN1"


def test_npz_and_csv_round_trip(tmp_path: Path) -> None:
    with open_mock() as scope:
        record = scope.capture()
    npz = tmp_path / "capture.npz"
    csv = tmp_path / "capture.csv"
    assert main(["capture", "--mock", "-o", str(npz), "--csv", str(csv)]) == 0
    loaded = load_npz(npz)
    assert np.allclose(loaded.samples, record.samples)
    assert np.allclose(loaded.time_s, record.time_s)
    assert loaded.metadata["geometry"]["array"] == "3+1"
    assert loaded.metadata["instrument_verified"] is False
    text = csv.read_text(encoding="utf-8").splitlines()
    assert text[0] == "time_s,CH1_V,CH2_V,CH3_V,CH4_V"
    assert len(text) == 9
    replay = tmp_path / "replay.npz"
    replay_csv = tmp_path / "replay.csv"
    assert main(["replay", str(npz), "-o", str(replay), "--csv", str(replay_csv)]) == 0
    again = load_npz(replay)
    assert again.metadata["acquisition_id"] == loaded.metadata["acquisition_id"]


def test_illegal_point_count_is_rejected_before_any_session() -> None:
    with open_mock() as scope:
        with pytest.raises(ValueError):
            scope.capture(points=7)
        assert scope.session.digitize_count == 0
