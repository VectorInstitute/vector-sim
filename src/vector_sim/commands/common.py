"""Helpers shared by commands that need a cluster profile and an Isaac Lab checkout."""

from __future__ import annotations

from pathlib import Path

from vector_sim.config.store import ConfigStore
from vector_sim.errors import ConfigError
from vector_sim.local.repo import discover_isaac_lab


def resolve_isaaclab(profile_isaaclab: str | None, start: Path | None = None) -> Path:
    return discover_isaac_lab(configured=profile_isaaclab, start=start).root


def require_cluster_profile(store: ConfigStore, cluster: str | None):
    name = cluster or store.get_active()
    if not name:
        raise ConfigError(
            "no cluster profile",
            suggestion="Run: vector-sim onboard bonecho",
        )
    return store.load_profile(name)
