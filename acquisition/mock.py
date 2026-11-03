"""In-memory MSOX2014A that speaks the waveform queries used by the driver.

The mock does not open VISA. It answers the same command strings the live
driver sends, including one ``:DIGitize`` and IEEE 488.2 blocks. A capture
through the mock still runs preamble parsing and voltage scaling.
"""

from __future__ import annotations

import numpy as np

from .errors import ScopeError, ScopeTimeoutError
from .waveform import encode_definite_block

MOCK_IDN = "KEYSIGHT TECHNOLOGIES,MSOX2014A,MY00000000,01.10"


class ScriptedMSOX:
    """Tiny SCPI script. ``codes`` is shape ``(4, N)`` unsigned bytes."""

    backend_name = "mock"

    def __init__(
        self,
        codes: np.ndarray,
        *,
        x_increment: float = 1e-6,
        x_origin: float = 0.0,
        y_increment: float = 0.01,
        y_origin: float = 0.0,
        y_reference: int = 128,
        timeout_command: str | None = None,
        error_after_digitize: str | None = None,
        channel_points: tuple[int, int, int, int] | None = None,
        channel_x_scale: tuple[float, float, float, float] | None = None,
    ):
        self.codes = np.asarray(codes, dtype=np.uint8)
        if self.codes.ndim != 2 or self.codes.shape[0] != 4:
            raise ValueError("mock codes must have shape (4, N)")
        self.voltages = (self.codes.astype(np.float64) - float(y_reference)) * float(y_increment) + float(y_origin)
        self.x_increment = float(x_increment)
        self.x_origin = float(x_origin)
        self.y_increment = float(y_increment)
        self.y_origin = float(y_origin)
        self.y_reference = int(y_reference)
        self.timeout_command = timeout_command
        self.error_after_digitize = error_after_digitize
        self.channel_points = channel_points
        self.channel_x_scale = channel_x_scale or (1.0, 1.0, 1.0, 1.0)
        self.commands: list[str] = []
        self.closed = False
        self.digitize_count = 0
        self._source = 1
        self._unsigned = True
        self._byte_order = "LSBFirst"
        self._format = "BYTE"
        self._pending = b""
        self._error_pending = False

    def write(self, command: str) -> None:
        self._respond(command, read=False)

    def query(self, command: str) -> str:
        self._respond(command, read=True)
        text = self._pending.decode("ascii")
        self._pending = b""
        return text.strip()

    def read_binary(self, command: str) -> bytes:
        self._respond(command, read=True)
        payload = self._pending
        self._pending = b""
        return payload

    def close(self) -> None:
        self.closed = True

    def _respond(self, command: str, read: bool) -> None:
        if self.closed:
            raise ScopeError("mock session is closed")
        cmd = " ".join(command.strip().split())
        if cmd == self.timeout_command:
            raise ScopeTimeoutError(f"mock timeout during {cmd}")
        self.commands.append(cmd)
        if not read:
            self._apply(cmd)
            return
        self._pending = self._answer(cmd)

    def _apply(self, cmd: str) -> None:
        if cmd == ":WAVeform:UNSigned ON":
            self._unsigned = True
        elif cmd == ":WAVeform:UNSigned OFF":
            self._unsigned = False
        elif cmd == ":WAVeform:BYTeorder LSBFirst":
            self._byte_order = "LSBFirst"
        elif cmd == ":WAVeform:BYTeorder MSBFirst":
            self._byte_order = "MSBFirst"
        elif cmd == ":WAVeform:FORMat BYTE":
            self._format = "BYTE"
        elif cmd == ":WAVeform:FORMat WORD":
            self._format = "WORD"
        elif cmd.startswith(":WAVeform:SOURce CHANnel"):
            self._source = int(cmd.rsplit("CHANnel", 1)[1])
        elif cmd.startswith(":DIGitize"):
            self.digitize_count += 1
            self._error_pending = self.error_after_digitize is not None

    def _answer(self, cmd: str) -> bytes:
        if cmd == "*IDN?":
            return (MOCK_IDN + "\n").encode("ascii")
        if cmd == ":SYSTem:ERRor?":
            if self._error_pending and self.error_after_digitize is not None:
                self._error_pending = False
                return self.error_after_digitize.encode("ascii") + b"\n"
            return b'0,"No error"\n'
        if cmd == ":WAVeform:UNSigned?":
            return b"1\n" if self._unsigned else b"0\n"
        if cmd == ":WAVeform:BYTeorder?":
            return (self._byte_order + "\n").encode("ascii")
        if cmd == ":WAVeform:FORMat?":
            return (self._format + "\n").encode("ascii")
        if cmd == ":WAVeform:POINts? MAXimum":
            points = self.codes.shape[1]
            if self.channel_points is not None:
                points = self.channel_points[self._source - 1]
            return f"{points}\n".encode("ascii")
        if cmd.startswith(":WAVeform:SOURce"):
            self._apply(cmd)
            return b"\n"
        if cmd == ":WAVeform:PREamble?":
            return self._preamble().encode("ascii")
        if cmd == ":WAVeform:DATA?":
            return self._data_block()
        return b"\n"

    def _preamble(self) -> str:
        index = self._source - 1
        points = self.codes.shape[1]
        if self.channel_points is not None:
            points = self.channel_points[index]
        xinc = self.x_increment * self.channel_x_scale[index]
        return (
            f"0,0,{points},1,{xinc:.12E},{self.x_origin:.12E},0,"
            f"{self.y_increment:.12E},{self.y_origin:.12E},{self.y_reference}\n"
        )

    def _data_block(self) -> bytes:
        index = self._source - 1
        codes = self.codes[index]
        if self.channel_points is not None:
            codes = codes[: self.channel_points[index]]
        return encode_definite_block(np.ascontiguousarray(codes).tobytes()) + b"\n"


DEMO_CODES = np.array(
    [
        [128, 130, 140, 150, 120, 110, 160, 128],
        [128, 132, 142, 152, 118, 108, 158, 128],
        [128, 134, 144, 154, 116, 106, 156, 128],
        [128, 136, 146, 156, 114, 104, 154, 128],
    ],
    dtype=np.uint8,
)


def open_mock(**kwargs):
    """Return the real driver pointed at an in-memory scope."""
    from .scope import KeysightMSOX2014A

    session = ScriptedMSOX(DEMO_CODES, **kwargs)
    return KeysightMSOX2014A(session)
