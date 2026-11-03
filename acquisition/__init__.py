"""Laptop-side acquisition for a Keysight MSOX2014A.

The live instrument path has not been run. ``open_mock`` exercises the same
parser and four-channel assembly without VISA.
"""

from .mock import open_mock
from .scope import KeysightMSOX2014A, discover_resources, open_visa, parse_idn
from .waveform import FourChannelRecord, load_npz, save_csv, save_npz

__all__ = [
    "FourChannelRecord",
    "KeysightMSOX2014A",
    "discover_resources",
    "load_npz",
    "open_mock",
    "open_visa",
    "parse_idn",
    "save_csv",
    "save_npz",
]
