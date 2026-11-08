"""Validate the QcomXnuUsbDebug darwin23 patches against the real build series.

Reproduces what `unixnu build kernel` does to the XNU tree for this board
(collab/CHANNEL.md #640 step 2):

  1. worktree at the revision the OS profile pins (d8b8029 = xnu-10063.141.1)
  2. arch series  (UniXNU/profiles/arch/arm64/patches/xnu/series)
  3. soc series   (UniXNU-sm8650-common/patches/xnu/series, empty today)
  4. os series    (MINUS zzz-boot-progress, which kernel.yml sed removes)
  5. device series (UniXNU-tb321fu/patches/xnu/series, empty today)
  6. dry-run the two darwin23 patches we want to append

Applies with plain 'git apply', exactly like the real build's patches.prepare().
The tree lives in /tmp because the sandbox refuses git apply on the D: workspace.

Usage:  python validate-usbdbg-patches.py [--apply]
"""
import functools
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:/WorkBuddy AI/Y700-UNIXNU/work")
XNU = ROOT / "xnu-full"
TREE = Path(os.environ.get("XNU_VALIDATE_TREE", "/tmp/xnu-validate"))
UNIXNU = ROOT / "UniXNU"
USBDBG = ROOT / "usbdbg"

PROFILE_ROOTS = {
    "arch": UNIXNU / "profiles/arch/arm64",
    "soc": ROOT / "UniXNU-sm8650-common",
    "os": UNIXNU / "profiles/os/ipados-17.7.11-21H461",
    "device": ROOT / "UniXNU-tb321fu",
}

print = functools.partial(print, flush=True)


def git(*args, check=True, cwd=XNU):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit("git " + " ".join(args) + " failed: " + result.stdout + result.stderr)
    return result


def prepare_tree():
    """A pristine detached worktree at the pinned revision.

    The main clone must never be patched: it is the object store every later
    run shares.  git worktree gives a clean checkout without downloading
    anything, and without git clean (which the sandbox refuses).

    A previous run can leave the directory behind without its registration
    (Windows file locking makes 'worktree remove' fail that way), so the path
    is cleared by hand before the add.  rm -rf on this one scratch directory
    is approved; it is never a personal directory.
    """
    git("worktree", "remove", "--force", str(TREE), check=False)
    git("worktree", "prune")
    if TREE.exists():
        subprocess.run(["rm", "-rf", str(TREE)], check=False)
    if TREE.exists():
        raise SystemExit("worktree path still present: " + str(TREE))
    git("worktree", "add", "--quiet", "--detach", str(TREE), "HEAD")
    git("config", "core.autocrlf", "false", cwd=TREE)
    return TREE


def series_patches(series_path, base):
    """Parse a UniXNU series file the way scripts/unixnu/patches.py does."""
    out = []
    for number, line in enumerate(series_path.read_text().splitlines(), 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("component:"):
            path = UNIXNU / "kits" / entry[len("component:"):]
        else:
            prefix, separator, relative = entry.partition(":")
            if separator and prefix in PROFILE_ROOTS:
                path = (PROFILE_ROOTS[prefix] / relative).resolve()
            else:
                path = (base / entry).resolve()
        if not path.is_file():
            raise SystemExit(str(series_path) + ":" + str(number) + ": missing " + str(path))
        out.append(path)
    return out


REPO_OF = {
    "XnuPrelink": UNIXNU / "kits/XnuPrelink",   # a submodule: its own index
    "UniXNU": UNIXNU,
    "usbdbg": USBDBG,
    "UniXNU-sm8650-common": ROOT / "UniXNU-sm8650-common",
    "UniXNU-tb321fu": ROOT / "UniXNU-tb321fu",
}


def lf_copy(patch):
    """The repo-stored (LF) bytes of a patch, materialised outside any worktree.

    The D: workspace is cloned with core.autocrlf=true, which rewrites every
    checked-out file to CRLF - the patches included.  git ls-files --eol shows
    i/lf w/crlf: the blobs are LF, the working copies are not.  CI checks out
    on macOS with autocrlf unset, so it applies the LF blobs.  Reading the
    blob instead of the working file is what makes this validation faithful;
    using the working copy makes every patch fail with a CR the source tree
    does not have.
    """
    for name, repo in REPO_OF.items():
        try:
            relative = patch.resolve().relative_to(repo.resolve())
        except ValueError:
            continue
        blob = subprocess.run(["git", "-C", str(repo), "show", ":" + str(relative).replace("\\", "/")],
                              capture_output=True)
        if blob.returncode == 0 and blob.stdout:
            target = Path(os.environ.get("XNU_VALIDATE_TREE", "/tmp/xnu-validate")) .parent / "lfpatches" / relative.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob.stdout)
            return target
    return patch


def apply_patch(patch, tree, dry):
    """git apply, byte-identical to what scripts/unixnu/patches.py:prepare() runs.

    GNU patch -p1 was tried first and is NOT equivalent: it needs fuzz 1 on
    offline-component-load-probes.patch where git apply applies the hunk at
    its stated line, and its temp-file rename is refused on osfmk/arm64/start.s
    under the D: workspace.  git apply only runs outside the workspace (the
    sandbox refuses it on D:), hence the /tmp worktree.
    """
    args = ["git", "apply"]
    if dry:
        args.append("--check")
    result = subprocess.run(args + [str(lf_copy(patch))], cwd=tree, capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main():
    apply_mode = "--apply" in sys.argv
    tree = prepare_tree()

    arch_series = PROFILE_ROOTS["arch"] / "patches/xnu/series"
    os_series = PROFILE_ROOTS["os"] / "patches/xnu/series"
    soc_series = PROFILE_ROOTS["soc"] / "patches/xnu/series"
    device_series = PROFILE_ROOTS["device"] / "patches/xnu/series"

    arch_list = series_patches(arch_series, arch_series.parent)
    soc_list = series_patches(soc_series, soc_series.parent)
    os_list = [p for p in series_patches(os_series, os_series.parent)
               if "zzz-boot-progress" not in p.name]
    device_list = series_patches(device_series, device_series.parent)
    plan = arch_list + soc_list + os_list + device_list

    print("series: %d patches (arch %d, soc %d, os %d, device %d)"
          % (len(plan), len(arch_list), len(soc_list), len(os_list), len(device_list)))

    failures = []
    for index, patch in enumerate(plan, 1):
        ok, output = apply_patch(patch, tree, dry=False)
        if not ok:
            failures.append((index, patch.name, output.strip()))
            print("  [%02d] FAIL %s" % (index, patch.name))
        else:
            print("  [%02d] ok   %s" % (index, patch.name))
    if failures:
        print("")
        print("=== series failures ===")
        for index, name, message in failures:
            print("[%02d] %s" % (index, name))
            print("    " + message.replace(chr(10), chr(10) + "    ")[:1500])
        raise SystemExit("%d of %d series patches failed" % (len(failures), len(plan)))

    ours = sorted(USBDBG.glob("patches/darwin23/*.patch"))
    print("")
    print("=== QcomXnuUsbDebug darwin23 (%d) ===" % len(ours))
    bad = 0
    for patch in ours:
        ok, output = apply_patch(patch, tree, dry=not apply_mode)
        print("  %s: %s" % ("APPLIES" if ok else "FAILS", patch.name))
        if not ok:
            bad += 1
            print("    " + output.strip().replace(chr(10), chr(10) + "    ")[:2500])
        elif apply_mode:
            print("    applied")

    print("")
    print("=== targets after the series ===")
    for relative in ("pexpert/arm/pe_kprintf.c", "osfmk/kern/debug.c", "osfmk/kern/printf.c",
                     "osfmk/console/serial_console.c", "osfmk/console/serial_general.c",
                     "bsd/kern/bsd_init.c"):
        path = tree / relative
        print("  %s: %d bytes" % (relative, path.stat().st_size if path.is_file() else -1))
    if bad:
        raise SystemExit("%d of %d darwin23 patches failed" % (bad, len(ours)))


if __name__ == "__main__":
    main()
