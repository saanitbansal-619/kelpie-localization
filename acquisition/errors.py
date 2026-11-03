"""Errors for the MSOX2014A acquisition module."""


class ScopeError(Exception):
    """Base error. The message names the command or record that failed."""


class ScopeTimeoutError(ScopeError):
    """The instrument did not answer before the configured timeout."""


class ScopeIOError(ScopeError):
    """VISA or transport failure other than a timeout."""


class ScopeIdentityError(ScopeError):
    """*IDN? did not identify an MSOX2014A."""


class ScopeInstrumentError(ScopeError):
    """The oscilloscope error queue returned a non-zero :SYSTem:ERRor?."""

    def __init__(self, messages: list[str]):
        self.messages = list(messages)
        text = "; ".join(self.messages) if self.messages else "instrument error"
        super().__init__(text)


class ScopeProtocolError(ScopeError):
    """A waveform block or preamble did not match the programmer's guide."""
