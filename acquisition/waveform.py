"""Waveform preamble, binary block, and four-channel record.

Scaling follows the InfiniiVision 2000 X-Series Programmer's Guide,
publication 9018-06893:

    voltage = [(data value - yreference) * yincrement] + yorigin
    time    = [(data point number - xreference) * xincrement] + xorigin

Data point numbers are 0-based. The guide's worked example uses point 3
for the fourth sample.

The guide disagrees with itself about two preamble integers. The command
summary uses format 2 for ASCii and type 3 for AVERage. The return-format
section and the example program use format 4 for ASCii and type 2 for
AVERage. Both codes are accepted. The raw integer is kept either way.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from .errors import ScopeProtocolError

# Publication 9018-06893, :WAVeform:POINts syntax for MAXimum or RAW.
LEGAL_POINT_COUNTS = (
    100,
    250,
    500,
    1000,
    2000,
    5000,
    10000,
    20000,
    50000,
    100000,
    200000,
    500000,
    1000000,
)

FORMAT_BYTE = 0
FORMAT_WORD = 1
FORMAT_ASCII_CODES = (2, 4)

TYPE_NAMES = {
    0: "NORMal",
    1: "PEAK",
    2: "AVERage",
    3: "AVERage",
    4: "HRESolution",
}

CHANNEL_IDS = ("CH1", "CH2", "CH3", "CH4")
HYDROPHONE_IDS = ("H1", "H2", "H3", "H4")

# Stated for this acquisition path. Triangle side and absolute coordinates
# are not specified here and stay out of the record's geometry block.
GEOMETRY_NOTE = {
    "array": "3+1",
    "h4_relative_to_upper_triangle_m": -0.400,
    "h4_description": "H4 is 400 mm below the upper triangle.",
    "triangle_side_m": "TBD",
    "absolute_coordinates_m": "TBD",
    "channel_to_hydrophone": {
        "CH1": "H1",
        "CH2": "H2",
        "CH3": "H3",
        "CH4": "H4",
    },
    "channel_map_status": (
        "Convention only. The cable from each conditioner output to each "
        "scope channel has not been verified."
    ),
    "signal_chain": "Aquarian S1f -> PCB 482C05 -> MSOX2014A analog input",
    "volts_to_pascals": "TBD",
}


@dataclass(frozen=True)
class WaveformPreamble:
    """Ten fields from :WAVeform:PREamble?, in the example program's order."""

    format_code: int
    type_code: int
    points: int
    count: int
    x_increment: float
    x_origin: float
    x_reference: int
    y_increment: float
    y_origin: float
    y_reference: int
    raw: str
    header_stripped: bool = False

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type_code, "UNKNOWN")

    def as_dict(self) -> dict[str, Any]:
        return {
            "format_code": self.format_code,
            "type_code": self.type_code,
            "type_name": self.type_name,
            "points": self.points,
            "count": self.count,
            "x_increment_s": self.x_increment,
            "x_origin_s": self.x_origin,
            "x_reference": self.x_reference,
            "y_increment_V": self.y_increment,
            "y_origin_V": self.y_origin,
            "y_reference": self.y_reference,
            "header_stripped": self.header_stripped,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class FourChannelRecord:
    """One simultaneous four-channel acquisition, in volts.

    ``samples`` has shape ``(4, N)`` in CH1..CH4 order. ``time_s`` has
    shape ``(N,)`` and is the trigger-relative time of every channel.
    """

    samples: np.ndarray
    time_s: np.ndarray
    sample_interval_s: float
    channel_ids: tuple[str, str, str, str]
    hydrophone_ids: tuple[str, str, str, str]
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if self.samples.shape != (4, self.time_s.shape[0]):
            raise ScopeProtocolError(
                f"samples shape {self.samples.shape} does not match time length {self.time_s.shape[0]}"
            )
        if self.channel_ids != CHANNEL_IDS or self.hydrophone_ids != HYDROPHONE_IDS:
            raise ScopeProtocolError("channel and hydrophone ids must be CH1..CH4 and H1..H4")


def parse_preamble(text: str) -> WaveformPreamble:
    """Parse the ten comma-separated preamble fields."""
    raw = text.strip()
    body = raw
    header_stripped = False
    if not body:
        raise ScopeProtocolError("empty :WAVeform:PREamble? response")
    first = body.split(",", 1)[0].strip()
    if _leading_number(first) is None:
        parts = body.split(None, 1)
        if len(parts) != 2:
            raise ScopeProtocolError(f"preamble does not start with a number: {raw!r}")
        body = parts[1].strip()
        header_stripped = True
    fields = [item.strip() for item in body.split(",")]
    if len(fields) != 10:
        raise ScopeProtocolError(f"preamble has {len(fields)} fields, expected 10: {raw!r}")
    try:
        preamble = WaveformPreamble(
            format_code=int(float(fields[0])),
            type_code=int(float(fields[1])),
            points=int(float(fields[2])),
            count=int(float(fields[3])),
            x_increment=float(fields[4]),
            x_origin=float(fields[5]),
            x_reference=int(float(fields[6])),
            y_increment=float(fields[7]),
            y_origin=float(fields[8]),
            y_reference=int(float(fields[9])),
            raw=raw,
            header_stripped=header_stripped,
        )
    except ValueError as exc:
        raise ScopeProtocolError(f"preamble field is not numeric: {raw!r}") from exc
    if preamble.x_increment <= 0:
        raise ScopeProtocolError(f"xincrement must be positive, got {preamble.x_increment}")
    if preamble.points < 1:
        raise ScopeProtocolError(f"preamble points must be positive, got {preamble.points}")
    return preamble


def encode_definite_block(body: bytes) -> bytes:
    """IEEE 488.2 definite-length block using the guide's 8-digit length form."""
    return b"#8" + f"{len(body):08d}".encode("ascii") + body


def parse_definite_block(payload: bytes) -> bytes:
    """Return the payload of a definite-length block.

    The guide's example is ``#8`` followed by eight length digits. The same
    chapter says the transfer uses the IEEE 488.2 arbitrary-block format, so
    any digit count from 1 to 9 is accepted. Bytes after the declared body,
    such as a newline, are ignored.
    """
    data = payload.lstrip(b" \t\r\n")
    if len(data) < 3 or data[0:1] != b"#":
        raise ScopeProtocolError("waveform block does not start with '#'")
    n_digits = data[1] - ord("0")
    if not 1 <= n_digits <= 9:
        raise ScopeProtocolError(f"invalid block length-digit count {data[1]!r}")
    if len(data) < 2 + n_digits:
        raise ScopeProtocolError("waveform block ended during the length field")
    try:
        length = int(data[2 : 2 + n_digits].decode("ascii"))
    except ValueError as exc:
        raise ScopeProtocolError("block length field is not an integer") from exc
    start = 2 + n_digits
    body = data[start : start + length]
    if len(body) != length:
        raise ScopeProtocolError(f"block declared {length} bytes but contained {len(body)}")
    return body


def decode_waveform(
    payload: bytes,
    preamble: WaveformPreamble,
    *,
    unsigned: bool,
    byte_order: str,
) -> np.ndarray:
    """Convert one :WAVeform:DATA? response to volts.

    PEAK acquisitions are rejected. Their time axis is min/max pairs, which
    is a different formula, and this module asks for NORMal.
    """
    if preamble.type_code == 1:
        raise ScopeProtocolError(
            "PEAK preamble is not converted. Set :ACQuire:TYPE NORMal and acquire again."
        )
    if preamble.format_code in FORMAT_ASCII_CODES:
        body = _ascii_body(payload)
        values = _parse_ascii_volts(body, preamble.points)
        return values
    if preamble.format_code == FORMAT_BYTE:
        body = parse_definite_block(payload)
        if len(body) != preamble.points:
            raise ScopeProtocolError(
                f"BYTE block has {len(body)} bytes, preamble points is {preamble.points}"
            )
        codes = np.frombuffer(body, dtype=np.dtype(np.uint8 if unsigned else np.int8))
    elif preamble.format_code == FORMAT_WORD:
        body = parse_definite_block(payload)
        if len(body) != preamble.points * 2:
            raise ScopeProtocolError(
                f"WORD block has {len(body)} bytes for {preamble.points} points"
            )
        if byte_order == "LSBFirst":
            endian = "<"
        elif byte_order == "MSBFirst":
            endian = ">"
        else:
            raise ScopeProtocolError(f"unknown byte order {byte_order!r}")
        kind = "u2" if unsigned else "i2"
        codes = np.frombuffer(body, dtype=np.dtype(endian + kind))
    else:
        raise ScopeProtocolError(f"unsupported waveform format code {preamble.format_code}")
    return scale_codes(codes.astype(np.float64, copy=False), preamble)


def scale_codes(codes: np.ndarray, preamble: WaveformPreamble) -> np.ndarray:
    """Apply the guide's voltage formula. ``codes`` are already signed correctly."""
    return (codes - float(preamble.y_reference)) * float(preamble.y_increment) + float(preamble.y_origin)


def sample_times(preamble: WaveformPreamble) -> np.ndarray:
    """Trigger-relative time of each point, in seconds."""
    index = np.arange(preamble.points, dtype=np.float64)
    return (index - float(preamble.x_reference)) * float(preamble.x_increment) + float(preamble.x_origin)


def assemble_record(
    traces: list[tuple[str, np.ndarray, WaveformPreamble]],
    metadata: dict[str, Any],
) -> FourChannelRecord:
    """Stack four traces that must share one time base."""
    if len(traces) != 4:
        raise ScopeProtocolError(f"expected 4 channels, got {len(traces)}")
    ids = tuple(item[0] for item in traces)
    if ids != CHANNEL_IDS:
        raise ScopeProtocolError(f"channels are {ids}, expected {CHANNEL_IDS}")
    reference = traces[0][2]
    time_s = sample_times(reference)
    rows = []
    preambles = []
    for channel_id, samples, preamble in traces:
        if samples.shape != (reference.points,):
            raise ScopeProtocolError(
                f"{channel_id} has {samples.size} samples, CH1 preamble points is {reference.points}"
            )
        if not _same_timebase(reference, preamble):
            raise ScopeProtocolError(
                f"{channel_id} time base does not match CH1 "
                f"(xincrement {preamble.x_increment} vs {reference.x_increment}, "
                f"xorigin {preamble.x_origin} vs {reference.x_origin}, "
                f"xreference {preamble.x_reference} vs {reference.x_reference})"
            )
        rows.append(np.asarray(samples, dtype=np.float64))
        preambles.append(preamble.as_dict())
    metadata = dict(metadata)
    metadata["preambles"] = preambles
    metadata["single_acquisition"] = True
    metadata["sample_time_note"] = (
        "time_s is trigger-relative and shared. It is not a gap-free stream "
        "and it is not a segmented-memory time tag."
    )
    return FourChannelRecord(
        samples=np.vstack(rows),
        time_s=time_s,
        sample_interval_s=float(reference.x_increment),
        channel_ids=CHANNEL_IDS,
        hydrophone_ids=HYDROPHONE_IDS,
        metadata=metadata,
    )


def save_npz(path: str, record: FourChannelRecord) -> None:
    np.savez_compressed(
        path,
        samples=record.samples,
        time_s=record.time_s,
        sample_interval_s=np.array(record.sample_interval_s, dtype=np.float64),
        channel_ids=np.array(record.channel_ids),
        hydrophone_ids=np.array(record.hydrophone_ids),
        metadata_json=np.array(json.dumps(record.metadata, sort_keys=True)),
    )


def load_npz(path: str) -> FourChannelRecord:
    with np.load(path, allow_pickle=False) as archive:
        required = ("samples", "time_s", "sample_interval_s", "channel_ids", "hydrophone_ids", "metadata_json")
        missing = [name for name in required if name not in archive]
        if missing:
            raise ScopeProtocolError(f"NPZ is missing {missing}")
        metadata = json.loads(archive["metadata_json"].item())
        return FourChannelRecord(
            samples=np.asarray(archive["samples"], dtype=np.float64),
            time_s=np.asarray(archive["time_s"], dtype=np.float64),
            sample_interval_s=float(archive["sample_interval_s"]),
            channel_ids=tuple(str(item) for item in archive["channel_ids"]),
            hydrophone_ids=tuple(str(item) for item in archive["hydrophone_ids"]),
            metadata=metadata,
        )


def save_csv(path: str, record: FourChannelRecord) -> None:
    """Write trigger time and four voltage columns. Metadata is not in the CSV."""
    header = "time_s," + ",".join(f"{channel}_V" for channel in record.channel_ids)
    table = np.column_stack([record.time_s, record.samples.T])
    np.savetxt(path, table, delimiter=",", header=header, comments="")


def _same_timebase(left: WaveformPreamble, right: WaveformPreamble) -> bool:
    return (
        left.points == right.points
        and left.x_reference == right.x_reference
        and _close(left.x_increment, right.x_increment)
        and _close(left.x_origin, right.x_origin, abs_tol=max(1e-15, abs(left.x_increment) * 1e-9))
    )


def _close(left: float, right: float, abs_tol: float = 0.0) -> bool:
    return abs(left - right) <= max(abs_tol, 1e-9 * max(abs(left), abs(right), 1e-30))


def _ascii_body(payload: bytes) -> str:
    data = payload.lstrip(b" \t\r\n")
    if data.startswith(b"#"):
        return parse_definite_block(payload).decode("ascii")
    # Bare comma-separated ASCII is not the form in publication 9018-06893.
    # The guide says ASCii records use the IEEE block. This branch only
    # exists so a malformed capture fails with the numeric parser if the
    # caller already stripped the block.
    raise ScopeProtocolError("ASCii waveform is missing its IEEE 488.2 block header")


def _parse_ascii_volts(body: str, points: int) -> np.ndarray:
    tokens = [item.strip() for item in body.split(",") if item.strip()]
    if len(tokens) != points:
        raise ScopeProtocolError(f"ASCii waveform has {len(tokens)} values, preamble points is {points}")
    try:
        values = np.array([float(item) for item in tokens], dtype=np.float64)
    except ValueError as exc:
        raise ScopeProtocolError("ASCii waveform contains a non-numeric value") from exc
    # Guide: holes in ASCii are 9.9e37.
    values[values >= 9.9e37] = np.nan
    return values


def _leading_number(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None
