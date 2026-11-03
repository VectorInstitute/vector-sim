from vector_sim.cluster.adapters import VectorSlurmAdapter
from vector_sim.config.models import bonecho_defaults
from vector_sim.jobs.args import expand_train_args, resolve_job_spec


def _profile():
    profile = bonecho_defaults()
    profile.remote_user = "alice"
    profile.scratch_dir = "/scratch/alice"
    VectorSlurmAdapter().derive_scratch_paths(profile)
    return profile


def test_video_cli_expansion_uses_underscore_flags() -> None:
    spec = resolve_job_spec(
        _profile(),
        task="Isaac-Cartpole-v0",
        video=True,
        video_length=200,
        video_interval=1000,
    )
    args = expand_train_args(spec)
    assert args == [
        "--task",
        "Isaac-Cartpole-v0",
        "--headless",
        "--enable_cameras",
        "--video",
        "--video_length",
        "200",
        "--video_interval",
        "1000",
    ]


def test_no_video_flags_without_video() -> None:
    args = expand_train_args(resolve_job_spec(_profile(), task="Isaac-Cartpole-v0"))
    assert "--video" not in args
    assert "--enable_cameras" not in args
    assert "--headless" not in args


def test_cli_override_precedence() -> None:
    spec = resolve_job_spec(
        _profile(),
        task="Isaac-Cartpole-v0",
        partition="a100_b1",
        gpu="a100",
        cpus=16,
        memory="64G",
        time="2h",
    )
    assert spec.partition == "a100_b1"
    assert spec.resolved_gres == "gpu:a100:1"
    assert spec.cpus == 16
    assert spec.memory == "64G"
    assert spec.resolved_time == "02:00:00"
    # defaults remain when not overridden
    default = resolve_job_spec(_profile(), task="Isaac-Cartpole-v0")
    assert default.partition == "a40_b1"
    assert default.resolved_gres == "gpu:a40:1"


def test_legacy_rsl_rl_default_follows_isaaclab3_unified_train(tmp_path) -> None:
    from vector_sim.jobs.args import (
        LEGACY_RSL_RL_TRAIN,
        UNIFIED_TRAIN,
        JobSpec,
        adapt_to_checkout,
    )

    (tmp_path / UNIFIED_TRAIN).parent.mkdir(parents=True)
    (tmp_path / UNIFIED_TRAIN).write_text("")
    spec = JobSpec(task="Isaac-Cartpole-v0")
    args = adapt_to_checkout(
        spec, ["--task", "Isaac-Cartpole", "--headless", "--enable_cameras", "--video"], tmp_path
    )
    assert spec.python_executable == UNIFIED_TRAIN
    assert args == ["--rl_library", "rsl_rl", "--task", "Isaac-Cartpole", "--video"]

    # A 2.x checkout keeps the per-library script untouched.
    (tmp_path / LEGACY_RSL_RL_TRAIN).parent.mkdir(parents=True)
    (tmp_path / LEGACY_RSL_RL_TRAIN).write_text("")
    spec = JobSpec(task="Isaac-Cartpole-v0")
    assert adapt_to_checkout(spec, ["--task", "x", "--headless"], tmp_path) == ["--task", "x", "--headless"]
    assert spec.python_executable == LEGACY_RSL_RL_TRAIN
