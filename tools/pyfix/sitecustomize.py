"""Workaround for building Mu-Silicium on a machine where reg.exe is blocked.

vcvarsall.bat locates the Windows SDK through `reg query`.  When that program is
blocked by an application-control policy, vsdevcmd clears WindowsSdkDir,
UniversalCRTSdkDir, WindowsSdkBinPath and WindowsSdkVerBinPath, and
edk2toollib.QueryVcVariables() then raises "Missing keys when querying
vcvarsall", which aborts the EDK2 pre-build step.

This module (auto-imported via PYTHONPATH) patches QueryVcVariables so that any
key that vcvarsall failed to produce is filled in from the values below, which
are the real paths of the Windows 10/11 SDK installed on this machine.
"""

import os
import subprocess
from pathlib import Path

_SDK_VERSION = "10.0.26100.0"
_SDK_ROOT = r"C:\Program Files (x86)\Windows Kits\10"

_SDK_FALLBACK = {
    "WindowsSdkDir": _SDK_ROOT + "\\",
    "UniversalCRTSdkDir": _SDK_ROOT + "\\",
    "WindowsSdkBinPath": _SDK_ROOT + r"\bin\\",
    "WindowsSdkVerBinPath": _SDK_ROOT + rf"\bin\{_SDK_VERSION}\x64",
    "WindowsSDKVersion": _SDK_VERSION + "\\",
    "UCRTVersion": _SDK_VERSION,
}

_VCVARSALL_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
]


def _find_vcvarsall():
    for candidate in _VCVARSALL_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _query_with_fallback(interesting, arch, vc_version=None):
    interesting = {str(key).upper() for key in interesting}
    vcvarsall = _find_vcvarsall()
    if vcvarsall is None:
        raise ValueError("Could not locate vcvarsall.bat")

    version_flag = f"-vcvars_ver={vc_version}" if vc_version else ""
    cmd = f'"{vcvarsall}" {arch} {version_flag} & set'
    output = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE).stdout.decode("mbcs", "replace")

    result = {}
    for line in output.split("\n"):
        if "=" not in line:
            continue
        key, value = line.strip().split("=", 1)
        if key.upper() in interesting:
            result[key] = value

    missing = interesting - {key.upper() for key in result}
    for key, value in _SDK_FALLBACK.items():
        if key.upper() in missing:
            result[key] = value
            missing.discard(key.upper())

    if missing:
        raise ValueError("Missing keys when querying vcvarsall: " + str(sorted(missing)))
    return result


def _install():
    try:
        from edk2toollib.windows import locate_tools
    except Exception:
        return

    original = locate_tools.QueryVcVariables
    if getattr(original, "_wb_sdk_fallback", False):
        return

    def QueryVcVariables(interesting, arch, vc_version=None):
        try:
            return original(interesting, arch, vc_version)
        except ValueError:
            return _query_with_fallback(interesting, arch, vc_version)

    QueryVcVariables._wb_sdk_fallback = True
    locate_tools.QueryVcVariables = QueryVcVariables


_install()
