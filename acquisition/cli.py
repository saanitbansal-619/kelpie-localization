"""Save one four-channel capture as NPZ, with an optional CSV copy.

Examples, from the repository root:

    python -m acquisition.cli capture --mock -o capture.npz --csv capture.csv
    python -m acquisition.cli discover
    python -m acquisition.cli identify USB0::0x2A8D::...::INSTR
    python -m acquisition.cli capture --resource USB0::0x2A8D::...::INSTR -o capture.npz
    python -m acquisition.cli replay capture.npz -o capture-copy.npz --csv capture.csv
"""

from __future__ import annotations

import argparse
import sys

from .errors import ScopeError
from .mock import open_mock
from .scope import discover_resources, open_visa
from .waveform import load_npz, save_csv, save_npz


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m acquisition.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="List VISA resources. Needs PyVISA and a VISA backend.")
    discover.set_defaults(func=_discover)

    identify = sub.add_parser("identify", help="Print *IDN? for one resource.")
    identify.add_argument("resource")
    identify.add_argument("--timeout", type=float, default=10.0, help="Seconds to wait for *IDN?.")
    identify.add_argument(
        "--allow-other-models",
        action="store_true",
        help="Accept an *IDN? model other than MSOX2014A.",
    )
    identify.set_defaults(func=_identify)

    capture = sub.add_parser("capture", help="Digitize CH1..CH4 once and save the record.")
    source = capture.add_mutually_exclusive_group(required=True)
    source.add_argument("--mock", action="store_true", help="Use the in-memory scope. No VISA.")
    source.add_argument("--resource", help="VISA resource string from discover.")
    capture.add_argument("-o", "--output", required=True, help="NPZ path.")
    capture.add_argument("--csv", help="Optional CSV path. Time and four voltage columns.")
    capture.add_argument("--timeout", type=float, default=30.0, help="Seconds. A waiting trigger uses this whole budget.")
    capture.add_argument("--points", type=int, default=None, help="Waveform points. Omit to ask the scope for the maximum.")
    capture.add_argument("--allow-other-models", action="store_true")
    capture.set_defaults(func=_capture)

    replay = sub.add_parser("replay", help="Reload an NPZ record and write it again. No instrument.")
    replay.add_argument("source")
    replay.add_argument("-o", "--output", required=True)
    replay.add_argument("--csv")
    replay.set_defaults(func=_replay)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ScopeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _discover(_args: argparse.Namespace) -> int:
    resources = discover_resources()
    if not resources:
        print("No VISA resources found.")
        return 0
    for resource in resources:
        print(resource)
    return 0


def _identify(args: argparse.Namespace) -> int:
    with open_visa(args.resource, timeout_s=args.timeout, allow_other_models=args.allow_other_models) as scope:
        identity = scope.identify()
    print(identity["raw"])
    return 0


def _capture(args: argparse.Namespace) -> int:
    if args.mock:
        scope = open_mock()
    else:
        scope = open_visa(
            args.resource,
            timeout_s=args.timeout,
            allow_other_models=args.allow_other_models,
        )
    with scope:
        record = scope.capture(points=args.points)
    _write_outputs(record, args.output, args.csv)
    print(
        f"saved {args.output} backend={record.metadata['backend']} "
        f"points={record.samples.shape[1]} instrument_verified={record.metadata['instrument_verified']}"
    )
    return 0


def _replay(args: argparse.Namespace) -> int:
    record = load_npz(args.source)
    _write_outputs(record, args.output, args.csv)
    print(f"replayed {args.source} -> {args.output}")
    return 0


def _write_outputs(record, npz_path: str, csv_path: str | None) -> None:
    save_npz(npz_path, record)
    if csv_path:
        save_csv(csv_path, record)
