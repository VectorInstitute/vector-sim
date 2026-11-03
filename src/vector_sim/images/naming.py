"""Naming for the official NVIDIA NGC Isaac Lab container and its cluster-side SIF."""

from __future__ import annotations

import re

from vector_sim.errors import ConfigError

NGC_REGISTRY = "nvcr.io"
NGC_IMAGE = "nvcr.io/nvidia/isaac-lab"
DEFAULT_ISAACLAB_VERSION = "3.0.0"
NGC_CATALOG_URL = "https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-lab"

_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_version(version: str) -> str:
    """Return *version* if it is a safe image tag; it ends up in a remote shell command."""
    tag = (version or "").strip()
    if not _VERSION_RE.match(tag):
        raise ConfigError(
            f"invalid Isaac Lab image version {version!r}",
            suggestion=f"Use a tag listed at {NGC_CATALOG_URL}/tags, e.g. {DEFAULT_ISAACLAB_VERSION}",
        )
    return tag


def ngc_image_ref(version: str) -> str:
    return f"{NGC_IMAGE}:{validate_version(version)}"


def docker_uri(version: str) -> str:
    """Source URI handed to ``apptainer pull``."""
    return f"docker://{ngc_image_ref(version)}"


def image_stem(version: str) -> str:
    return f"isaac-lab-{validate_version(version)}"


def remote_sif_name(version: str) -> str:
    return f"{image_stem(version)}.sif"
