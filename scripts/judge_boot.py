#!/usr/bin/env python3
"""Boot one image and decide the outcome with a physically sound judge.

Why this exists
---------------
`fastboot boot` itself blocks for 3.8-10.2 seconds (measured in
`work/boot_when_fastboot.log`: `Booting  OKAY [ 10.195s]`, and `[ 10.194s]`
for a 9.9 MB image).  A judge that reports "reset happened 2 s after
`fastboot boot` returned" is therefore measuring the wrong thing: it only
observed that the ABL's fastboot endpoint was still present.

A real reset has this shape:

    t0        `fastboot boot` returns rc=0
    0.5-5 s   the fastboot endpoint disappears   (ABL hands over to BootShim)
    10-30 s   the endpoint comes back            (probe waited 6 s, then PSCI
                                                  reset, then ABL restarts)
    >60 s     never comes back                   (hung; probe never fired)

A boot that never took effect looks different: the endpoint never disappears.

Usage
    judge_boot.py <boot.img> [--boot-timeout 120] [--sample 0.5]

Exit codes
    0  reset confirmed (vanished, then came back)
    1  hung (vanished, never came back)
    2  boot did not take effect (endpoint never vanished)
    3  hardware error (fastboot boot itself failed)
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

BOOT_OK_RE = re.compile(r"Booting\s+OKAY\s+\[\s+([0-9.]+)s\]")


def devices(timeout=8):
    """True when the fastboot endpoint answers."""
    try:
        out = subprocess.run(["fastboot", "devices"], capture_output=True,
                             text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return bool(out.stdout.strip())


def boot(img):
    """Run `fastboot boot`; return (returncode, boot_okay_seconds)."""
    started = time.monotonic()
    out = subprocess.run(["fastboot", "boot", str(img)],
                         capture_output=True, text=True, timeout=300)
    elapsed = time.monotonic() - started
    match = BOOT_OK_RE.search(out.stdout)
    okay = float(match.group(1)) if match else None
    print("fastboot boot rc=%d in %.1f s; Booting OKAY %s"
          % (out.returncode, elapsed,
             ("%.3f s" % okay) if okay else "(not reported)"))
    if okay is not None:
        if okay < 5:
            print("  note: Booting OKAY %.3f s is short (usually ~10.2 s); "
                  "the ABL may have refused the image." % okay)
        else:
            print("  note: Booting OKAY %.3f s looks like a normal hand-over." % okay)
    return out.returncode, okay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--boot-timeout", type=float, default=120.0,
                        help="how long to watch for the endpoint to return")
    parser.add_argument("--sample", type=float, default=0.5,
                        help="polling interval in seconds")
    args = parser.parse_args()

    img = Path(args.image)
    if not img.is_file():
        raise SystemExit("no such image: %s" % img)

    if devices():
        print("endpoint present before boot; continuing")

    rc, okay = boot(img)
    if rc != 0:
        print("RESULT: hardware error -- fastboot boot failed")
        return 3

    t0 = time.monotonic()

    # Phase 1: the endpoint must disappear soon (ABL handing over).
    vanished_at = None
    while time.monotonic() - t0 < 6.0:
        if not devices():
            vanished_at = time.monotonic() - t0
            print("endpoint vanished after %.1f s  (hand-over)" % vanished_at)
            break
        time.sleep(args.sample)
    if vanished_at is None:
        print("endpoint never vanished within 6 s")
        print("RESULT: boot did not take effect -- this round proves nothing")
        return 2

    # Phase 2: a real reset brings the endpoint back, 10-30 s after hand-over.
    came_back_at = None
    deadline = time.monotonic() + args.boot_timeout
    while time.monotonic() < deadline:
        if devices():
            came_back_at = time.monotonic() - t0
            break
        time.sleep(args.sample)

    if came_back_at is None:
        print("endpoint did not return within %.0f s" % args.boot_timeout)
        print("RESULT: hung -- the probe never fired (kernel stopped before it)")
        return 1

    gap = came_back_at - vanished_at
    print("endpoint returned after %.1f s (gap %.1f s)" % (came_back_at, gap))
    if gap < 5:
        print("RESULT: suspicious -- came back too fast to be a probe reset")
        print("        (ABL may not have detached; treat as unverified)")
        return 2
    print("RESULT: reset confirmed -- probe fired and the board restarted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
