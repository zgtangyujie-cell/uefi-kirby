#!/usr/bin/env python3
"""Build kernel.macho.adt from the device tree, without the UniXNU CLI.

UniXNU's own payload step (scripts/unixnu/payload.py:191-196) generates this
sidecar, but it also wants feeds, mformat, a Data seed and IPSW members.  The
ADT itself needs only two things:

  * a compiled hardware DTB (dtc over dts/<board>.dts + the SoC dtsi),
  * the board's [payload] and [payload.adt] tables.

So this script calls the same unixnu.devicetree.generate() with exactly those
inputs.  Two values in board.toml are deliberately skipped, because they are
placeholders and guessing them would put fabricated data into the ADT:

  root_match_volume_uuid = "REQUIRED_ROOT_VOLUME_UUID"  -> needs the userdata GPT
  unique_chip_id        = "required"                    -> needs the device's seed
"""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

SKIPPED = (
    ("root_match_volume_uuid", "REQUIRED_ROOT_VOLUME_UUID placeholder; needs the userdata GPT"),
    ("unique_chip_id", "no 64-bit seed collected from the device yet"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unixnu", default="/tmp/UniXNU", help="UniXNU checkout (for unixnu.devicetree)")
    parser.add_argument("--device-dir", default="devices/UniXNU-tb321fu")
    parser.add_argument("--soc-dir", default="devices/UniXNU-sm8650-common")
    parser.add_argument("--dts", default=None, help="device DTS (default: <device-dir>/dts/tb321fu.dts)")
    parser.add_argument("--output", required=True, help="path of kernel.macho.adt to write")
    args = parser.parse_args()

    device = Path(args.device_dir)
    board_path = device / "board.toml"
    dts = Path(args.dts) if args.dts else device / "dts" / "tb321fu.dts"
    output = Path(args.output)
    dtb = output.with_suffix(".dtb")
    dtb.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "dtc", "-I", "dts", "-O", "dtb",
        "-i", str(Path(args.soc_dir) / "dts"),
        "-o", str(dtb), str(dts),
    ]
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)

    sys.path.insert(0, str(Path(args.unixnu) / "scripts"))
    from unixnu.devicetree import generate

    board = tomllib.loads(board_path.read_text(encoding="utf-8"))
    spec = board.setdefault("payload", {}).setdefault("adt", {})
    for key, reason in SKIPPED:
        if key in spec:
            print(f"skipping payload.adt.{key}: {reason}", flush=True)
            spec.pop(key)

    adt = generate(dtb, board)
    output.write_bytes(adt)
    print(f"ADT: {len(adt)} bytes -> {output}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
