"""MSOX2014A capture. One :DIGitize, then four waveform reads.

Command source: Keysight InfiniiVision 2000 X-Series Oscilloscopes
Programmer's Guide, publication 9018-06893.

This is a single-record transfer. It is not gap-free streaming. Segmented
memory commands are not sent. :DIGitize stops the scope when the record is
full, and the four :WAVeform:DATA? queries read that stopped record.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from .errors import (
    ScopeError,
    ScopeIdentityError,
    ScopeInstrumentError,
    ScopeIOError,
    ScopeProtocolError,
    ScopeTimeoutError,
)
from .waveform import (
    CHANNEL_IDS,
    GEOMETRY_NOTE,
    LEGAL_POINT_COUNTS,
    FourChannelRecord,
    assemble_record,
    decode_waveform,
    parse_preamble,
)

SCPI_REFERENCE = (
    "Keysight InfiniiVision 2000 X-Series Oscilloscopes Programmer's Guide, "
    "publication 9018-06893"
)

# Commands this driver sends. Each one appears in publication 9018-06893.
VERIFIED_COMMANDS = (
    "*IDN?",
    ":SYSTem:ERRor?",
    ":TIMebase:MODE MAIN",
    ":CHANnel<n>:DISPlay ON",
    ":ACQuire:TYPE NORMal",
    ":WAVeform:FORMat BYTE",
    ":WAVeform:UNSigned ON",
    ":WAVeform:UNSigned?",
    ":WAVeform:BYTeorder LSBFirst",
    ":WAVeform:BYTeorder?",
    ":WAVeform:FORMat?",
    ":WAVeform:POINts:MODE RAW",
    ":DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4",
    ":WAVeform:SOURce CHANnel<n>",
    ":WAVeform:POINts? MAXimum",
    ":WAVeform:POINts <points>",
    ":WAVeform:PREamble?",
    ":WAVeform:DATA?",
)

UNVERIFIED = (
    "No MSOX2014A has been connected. Command text is from the guide; instrument behavior is not.",
    "Preamble ASCii format code is 2 in the command summary and 4 in the return-format section.",
    "Preamble AVERage type code is 3 in the command summary and 2 in the example program.",
    ":WAVeform:POINts says only displayed data is returned. :WAVeform:POINts:MODE RAW says the raw record is available when stopped. Both sentences are in the guide. Which record the MSOX2014A returns has not been measured.",
    "Gap-free continuous streaming is not implemented and is not claimed.",
    "Segmented memory (:ACQuire:MODE SEGMented and :WAVeform:SEGMented:*) requires the SGM license in the guide and is not used.",
    "CH1..CH4 to H1..H4 is a cable convention, not a checked wiring map.",
    "Volts are not converted to pascals. Conditioner gain and hydrophone sensitivity are TBD.",
)


class InstrumentSession(Protocol):
    commands: list[str]

    def write(self, command: str) -> None: ...

    def query(self, command: str) -> str: ...

    def read_binary(self, command: str) -> bytes: ...

    def close(self) -> None: ...


class KeysightMSOX2014A:
    """One scope session. Use it as a context manager so the resource closes."""

    def __init__(self, session: InstrumentSession, *, allow_other_models: bool = False):
        self.session = session
        self.allow_other_models = allow_other_models
        self._closed = False

    def __enter__(self) -> "KeysightMSOX2014A":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.session.close()

    def identify(self) -> dict[str, str]:
        """Query *IDN? and split the four standard fields."""
        raw = self._query("*IDN?")
        return parse_idn(raw, allow_other_models=self.allow_other_models)

    def capture(self, *, points: int | None = None) -> FourChannelRecord:
        """Digitize CH1..CH4 once and read all four traces from that record.

        ``points`` None asks the scope for ``:WAVeform:POINts? MAXimum`` after
        the digitize and requests that count for every channel. A caller-chosen
        count must be one of the values listed for ``:WAVeform:POINts``.
        """
        self._ensure_open()
        if points is not None and points not in LEGAL_POINT_COUNTS:
            raise ValueError(
                f"points must be one of {LEGAL_POINT_COUNTS} or omitted for the instrument maximum"
            )
        identity = self.identify()
        self._write(":TIMebase:MODE MAIN")
        for channel in (1, 2, 3, 4):
            self._write(f":CHANnel{channel}:DISPlay ON")
        self._write(":ACQuire:TYPE NORMal")
        self._write(":WAVeform:FORMat BYTE")
        self._write(":WAVeform:UNSigned ON")
        self._write(":WAVeform:BYTeorder LSBFirst")
        self._write(":WAVeform:POINts:MODE RAW")
        unsigned = self._query(":WAVeform:UNSigned?")
        byte_order = self._query(":WAVeform:BYTeorder?")
        data_format = self._query(":WAVeform:FORMat?")
        if unsigned not in {"0", "1"}:
            raise ScopeProtocolError(f"unexpected :WAVeform:UNSigned? response {unsigned!r}")
        if byte_order not in {"LSBFirst", "MSBFirst"}:
            raise ScopeProtocolError(f"unexpected :WAVeform:BYTeorder? response {byte_order!r}")
        if data_format not in {"BYTE", "WORD", "ASC"}:
            raise ScopeProtocolError(f"unexpected :WAVeform:FORMat? response {data_format!r}")
        digitize = ":DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4"
        self._write(digitize)
        if points is None:
            # Query maximum on channel 1, then use that same count for all four.
            self._write(":WAVeform:SOURce CHANnel1")
            reported = self._query(":WAVeform:POINts? MAXimum")
            try:
                points = int(float(reported))
            except ValueError as exc:
                raise ScopeProtocolError(f":WAVeform:POINts? MAXimum returned {reported!r}") from exc
            if points < 1:
                raise ScopeProtocolError(f"instrument reported {points} points")
        self._write(f":WAVeform:POINts {points}")
        traces = []
        for channel, channel_id in enumerate(CHANNEL_IDS, start=1):
            self._write(f":WAVeform:SOURce CHANnel{channel}")
            preamble = parse_preamble(self._query(":WAVeform:PREamble?"))
            payload = self._read_binary(":WAVeform:DATA?")
            samples = decode_waveform(
                payload,
                preamble,
                unsigned=(unsigned == "1"),
                byte_order=byte_order,
            )
            traces.append((channel_id, samples, preamble))
        errors = self._drain_errors()
        if errors:
            raise ScopeInstrumentError(errors)
        metadata = {
            "backend": getattr(self.session, "backend_name", "session"),
            "instrument_verified": False,
            "idn": identity,
            "acquisition_id": uuid.uuid4().hex,
            "laptop_clock_utc": datetime.now(timezone.utc).isoformat(),
            "laptop_clock_note": "Laptop clock at the end of the read. Not an oscilloscope timestamp.",
            "digitize_command": digitize,
            "requested_points": points,
            "waveform_format": data_format,
            "unsigned": unsigned == "1",
            "byte_order": byte_order,
            "points_mode": "RAW",
            "acquire_type_command": ":ACQuire:TYPE NORMal",
            "geometry": GEOMETRY_NOTE,
            "scpi_reference": SCPI_REFERENCE,
            "verified_commands": list(VERIFIED_COMMANDS),
            "unverified": list(UNVERIFIED),
            "scpi_commands": list(self.session.commands),
            "streaming": "not implemented",
            "segmented_memory": "not used",
        }
        return assemble_record(traces, metadata)

    def _ensure_open(self) -> None:
        if self._closed:
            raise ScopeError("scope session is closed")

    def _write(self, command: str) -> None:
        self._ensure_open()
        try:
            self.session.write(command)
        except ScopeTimeoutError:
            raise
        except ScopeError:
            raise
        except TimeoutError as exc:
            raise ScopeTimeoutError(f"timeout during {command}") from exc
        except Exception as exc:
            raise ScopeIOError(f"{type(exc).__name__} during {command}: {exc}") from exc

    def _query(self, command: str) -> str:
        self._ensure_open()
        try:
            return self.session.query(command).strip()
        except ScopeTimeoutError:
            raise
        except ScopeError:
            raise
        except TimeoutError as exc:
            raise ScopeTimeoutError(f"timeout during {command}") from exc
        except Exception as exc:
            raise ScopeIOError(f"{type(exc).__name__} during {command}: {exc}") from exc

    def _read_binary(self, command: str) -> bytes:
        self._ensure_open()
        try:
            return self.session.read_binary(command)
        except ScopeTimeoutError:
            raise
        except ScopeError:
            raise
        except TimeoutError as exc:
            raise ScopeTimeoutError(f"timeout during {command}") from exc
        except Exception as exc:
            raise ScopeIOError(f"{type(exc).__name__} during {command}: {exc}") from exc

    def _drain_errors(self) -> list[str]:
        """Read :SYSTem:ERRor? until 0. The guide says the queue is 30 deep."""
        found: list[str] = []
        for _ in range(30):
            line = self._query(":SYSTem:ERRor?")
            code_text, separator, _rest = line.partition(",")
            if not separator:
                raise ScopeProtocolError(f"unexpected :SYSTem:ERRor? response {line!r}")
            try:
                code = int(float(code_text))
            except ValueError as exc:
                raise ScopeProtocolError(f"unexpected :SYSTem:ERRor? response {line!r}") from exc
            if code == 0:
                return found
            found.append(line)
        raise ScopeInstrumentError(found + ["error queue did not return 0 within 30 reads"])


class VisaSession:
    """PyVISA transport. Importing PyVISA happens here, not in the parsers."""

    backend_name = "visa"

    def __init__(self, resource_name: str, timeout_s: float):
        try:
            import pyvisa
            from pyvisa import errors as visa_errors
        except ImportError as exc:
            raise ScopeIOError(
                "PyVISA is not installed. Install pyvisa and a VISA backend "
                "(Keysight IO Libraries or NI-VISA) before opening a scope. "
                "Mock capture does not need either."
            ) from exc
        self.commands: list[str] = []
        self._visa_errors = visa_errors
        self._rm = pyvisa.ResourceManager()
        try:
            self._inst = self._rm.open_resource(resource_name)
        except Exception:
            self._rm.close()
            raise
        self._inst.timeout = int(timeout_s * 1000)
        self._inst.write_termination = "\n"
        self._inst.read_termination = "\n"
        self._closed = False

    def write(self, command: str) -> None:
        self.commands.append(command)
        try:
            self._inst.write(command)
        except self._visa_errors.VisaIOError as exc:
            self._raise(exc, command)

    def query(self, command: str) -> str:
        self.commands.append(command)
        try:
            return str(self._inst.query(command))
        except self._visa_errors.VisaIOError as exc:
            self._raise(exc, command)

    def read_binary(self, command: str) -> bytes:
        self.commands.append(command)
        try:
            self._inst.write(command)
            return bytes(self._inst.read_raw())
        except self._visa_errors.VisaIOError as exc:
            self._raise(exc, command)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inst.close()
        self._rm.close()

    def _raise(self, exc: Exception, command: str) -> None:
        text = f"{exc} during {command}"
        abbreviation = getattr(exc, "abbreviation", "") or ""
        if "TMO" in abbreviation.upper() or "TMO" in str(exc).upper():
            raise ScopeTimeoutError(text) from exc
        raise ScopeIOError(text) from exc


def parse_idn(raw: str, *, allow_other_models: bool = False) -> dict[str, str]:
    parts = [item.strip() for item in raw.split(",")]
    if len(parts) < 4:
        raise ScopeProtocolError(f"*IDN? did not return four fields: {raw!r}")
    identity = {
        "raw": raw,
        "manufacturer": parts[0],
        "model": parts[1],
        "serial": parts[2],
        "firmware": parts[3],
    }
    if "MSOX2014A" not in identity["model"].upper() and not allow_other_models:
        raise ScopeIdentityError(
            f"expected model MSOX2014A, *IDN? returned {identity['model']!r}. "
            "Pass allow_other_models only if you accept that this driver was written from the 2000 X-Series guide."
        )
    return identity


def discover_resources() -> list[str]:
    """Return VISA resource strings. Requires PyVISA and a VISA backend."""
    try:
        import pyvisa
    except ImportError as exc:
        raise ScopeIOError(
            "PyVISA is not installed, so instruments cannot be listed. "
            "Mock capture is still available."
        ) from exc
    manager = pyvisa.ResourceManager()
    try:
        return [str(item) for item in manager.list_resources()]
    except Exception as exc:
        raise ScopeIOError(f"VISA resource listing failed: {exc}") from exc
    finally:
        manager.close()


def open_visa(resource_name: str, *, timeout_s: float = 30.0, allow_other_models: bool = False) -> KeysightMSOX2014A:
    return KeysightMSOX2014A(
        VisaSession(resource_name, timeout_s),
        allow_other_models=allow_other_models,
    )
