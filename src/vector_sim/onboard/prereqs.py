"""Local prerequisite inspection. Never runs sudo."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from vector_sim.images.ngc import ENV_PASSWORD, ENV_USERNAME, NGC_KEY_HELP, credentials_from_env

STATUS_INSTALLED = "INSTALLED"
STATUS_REQUIRED = "REQUIRED"
STATUS_USER_ACTION = "USER ACTION REQUIRED"
STATUS_UNSUPPORTED = "UNSUPPORTED"

UBUNTU_HINT = (
    "v1 bootstrap supports Ubuntu-like Linux. Other platforms: install git, ssh, "
    "and rsync yourself, then re-run vector-sim bootstrap."
)


@dataclass
class Prereq:
    name: str
    status: str
    detail: str = ""
    install_command: str | None = None
    required: bool = True

    @property
    def ok(self) -> bool:
        return self.status == STATUS_INSTALLED


@dataclass
class PlatformInfo:
    system: str
    like: str  # ubuntu | linux | other
    pretty: str
    supported_bootstrap: bool
    detail: str = ""


@dataclass
class PrereqReport:
    platform: PlatformInfo
    items: list[Prereq] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(item.ok or not item.required for item in self.items)


def read_os_release(path: Path | None = None) -> dict[str, str]:
    target = path or Path("/etc/os-release")
    data: dict[str, str] = {}
    if not target.is_file():
        return data
    for line in target.read_text(errors="replace").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def inspect_platform(*, os_release: dict[str, str] | None = None, system: str | None = None) -> PlatformInfo:
    sysname = (system or os.uname().sysname).lower()
    release = os_release if os_release is not None else read_os_release()
    ident = (release.get("ID") or "").lower()
    like = (release.get("ID_LIKE") or "").lower()
    pretty = release.get("PRETTY_NAME") or sysname
    ubuntu_like = ident == "ubuntu" or "ubuntu" in like or ident == "debian" or "debian" in like
    if sysname != "linux":
        return PlatformInfo(sysname, "other", pretty, False, "vector-sim v1 targets Linux.")
    if ubuntu_like:
        return PlatformInfo(sysname, "ubuntu", pretty, True, "Ubuntu-like Linux; apt install commands apply.")
    return PlatformInfo(sysname, "linux", pretty, False, UBUNTU_HINT)


def inspect_prereqs() -> PrereqReport:
    platform = inspect_platform()
    items: list[Prereq] = []
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_ok = sys.version_info >= (3, 10)
    items.append(
        Prereq(
            "Python",
            STATUS_INSTALLED if py_ok else STATUS_REQUIRED,
            f"{sys.version.split()[0]} (need >= 3.10)",
            required=True,
        )
    )

    apt = {
        "git": "sudo apt-get update && sudo apt-get install -y git",
        "ssh": "sudo apt-get update && sudo apt-get install -y openssh-client",
        "rsync": "sudo apt-get update && sudo apt-get install -y rsync",
    }
    for tool, cmd in apt.items():
        path = shutil.which(tool)
        items.append(
            Prereq(
                tool,
                STATUS_INSTALLED if path else STATUS_USER_ACTION if platform.supported_bootstrap else STATUS_REQUIRED,
                path or f"{tool} not found on PATH",
                install_command=None if path else cmd,
                required=True,
            )
        )

    creds = credentials_from_env()
    items.append(
        Prereq(
            "NGC credentials",
            STATUS_INSTALLED if creds else STATUS_USER_ACTION,
            f"{ENV_USERNAME}/{ENV_PASSWORD} set" if creds else f"{ENV_PASSWORD} not set (needed for deploy)",
            install_command=None if creds else NGC_KEY_HELP,
            required=False,
        )
    )

    if not platform.supported_bootstrap:
        items.append(
            Prereq(
                "platform",
                STATUS_UNSUPPORTED,
                platform.detail,
                required=False,
            )
        )
    else:
        items.append(Prereq("platform", STATUS_INSTALLED, platform.pretty, required=False))

    return PrereqReport(platform=platform, items=items)


def format_prereq_report(report: PrereqReport) -> str:
    lines = [
        f"Platform            {report.platform.pretty}",
        f"Bootstrap support   {'Ubuntu-like Linux' if report.platform.supported_bootstrap else 'not auto-installed (v1)'}",
        "",
    ]
    for item in report.items:
        lines.append(f"{item.name:<20} {item.status:<22} {item.detail}")
        if item.install_command and item.status != STATUS_INSTALLED:
            lines.append(f"{'':<20} command: {item.install_command}")
    lines.append("")
    lines.append("vector-sim never runs sudo unless you copy-paste a command yourself.")
    lines.append("Docker is not needed: the Isaac Lab image is pulled on the cluster with Apptainer.")
    return "\n".join(lines)
