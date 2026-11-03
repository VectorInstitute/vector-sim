"""CLI / profile job argument resolution and Isaac Lab train.py flag expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vector_sim.cluster.slurm import gres_request, slurm_time
from vector_sim.config.models import ClusterProfile, DefaultJob
from vector_sim.images.naming import DEFAULT_ISAACLAB_VERSION, image_stem, validate_version

# Isaac Lab 2.x ships one train.py per RL library; 3.x replaces them with a single
# dispatcher that selects the library through --rl_library.
LEGACY_RSL_RL_TRAIN = "scripts/reinforcement_learning/rsl_rl/train.py"
UNIFIED_TRAIN = "scripts/reinforcement_learning/train.py"


@dataclass
class JobSpec:
    task: str
    image_version: str = DEFAULT_ISAACLAB_VERSION
    partition: str | None = None
    gpu_type: str | None = None
    gpu_count: int = 1
    gres: str | None = None
    cpus: int = 8
    memory: str = "32G"
    time: str = "1h"
    python_executable: str = LEGACY_RSL_RL_TRAIN
    video: bool = False
    video_length: int = 200
    video_interval: int = 1000
    headless: bool | None = None
    extra_args: list[str] = field(default_factory=list)

    @property
    def container_name(self) -> str:
        return image_stem(self.image_version)

    @property
    def resolved_gres(self) -> str | None:
        if self.gres:
            return self.gres
        return gres_request(
            DefaultJob(gpu_type=self.gpu_type, gpu_count=self.gpu_count)
        )

    @property
    def resolved_time(self) -> str:
        return slurm_time(self.time)


def resolve_job_spec(profile: ClusterProfile, **overrides) -> JobSpec:
    """Resolve JobSpec: cluster profile defaults, then CLI overrides."""
    defaults = profile.default_job
    task = overrides.get("task")
    if not task:
        raise ValueError("--task is required")
    image_version = validate_version(
        overrides.get("image_version") or profile.image.version or DEFAULT_ISAACLAB_VERSION
    )
    video = bool(overrides.get("video", False))
    headless = bool(overrides.get("headless")) or video
    return JobSpec(
        task=str(task),
        image_version=image_version,
        partition=overrides.get("partition") or defaults.partition,
        gpu_type=overrides.get("gpu") or overrides.get("gpu_type") or defaults.gpu_type,
        gpu_count=int(overrides.get("gpus") or overrides.get("gpu_count") or defaults.gpu_count or 1),
        gres=overrides.get("gres"),
        cpus=int(overrides.get("cpus") or defaults.cpus or 8),
        memory=str(overrides.get("memory") or defaults.memory or "32G"),
        time=str(overrides.get("time") or defaults.time or "1h"),
        python_executable=str(
            overrides.get("python_executable") or profile.python_executable
        ),
        video=video,
        video_length=int(overrides.get("video_length") or 200),
        video_interval=int(overrides.get("video_interval") or 1000),
        headless=headless,
        extra_args=list(overrides.get("extra_args") or []),
    )


def expand_train_args(spec: JobSpec) -> list[str]:
    """Build Isaac Lab train.py argv using underscore flag names."""
    args = ["--task", spec.task]
    if spec.headless:
        args.append("--headless")
    if spec.video:
        args.extend(
            [
                "--enable_cameras",
                "--video",
                "--video_length",
                str(spec.video_length),
                "--video_interval",
                str(spec.video_interval),
            ]
        )
    args.extend(spec.extra_args)
    return args


def is_isaaclab3_checkout(repo: Path) -> bool:
    repo = Path(repo)
    return (repo / UNIFIED_TRAIN).is_file() and not (repo / LEGACY_RSL_RL_TRAIN).is_file()


# Isaac Lab 3.x runs headless unless --visualizer is given, and --video enables
# cameras itself; passing either flag is an argparse error there.
ISAACLAB3_REMOVED_FLAGS = ("--headless", "--enable_cameras")


def adapt_to_checkout(spec: JobSpec, train_args: list[str], repo: Path) -> list[str]:
    """Adapt 2.x-style train args to an Isaac Lab 3.x checkout.

    Points the legacy rsl_rl default at the unified train.py (selecting rsl_rl) and
    drops launcher flags 3.x removed. Returns the train args to submit; updates
    spec.python_executable in place. 2.x checkouts are returned unchanged.
    """
    if not is_isaaclab3_checkout(repo):
        return train_args
    args = [a for a in train_args if a not in ISAACLAB3_REMOVED_FLAGS]
    if spec.python_executable == LEGACY_RSL_RL_TRAIN:
        spec.python_executable = UNIFIED_TRAIN
        if "--rl_library" not in args:
            args = ["--rl_library", "rsl_rl", *args]
    return args
