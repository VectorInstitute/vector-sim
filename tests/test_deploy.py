"""vector-sim deploy: pull the official NGC Isaac Lab image on the cluster with Apptainer."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes.runner import FakeExecute
from vector_sim.cluster.adapters import VectorSlurmAdapter
from vector_sim.commands.deploy import DeployCommand
from vector_sim.config.models import bonecho_defaults
from vector_sim.config.store import ConfigStore
from vector_sim.errors import ConfigError, VectorSimError
from vector_sim.exec import CommandRunner
from vector_sim.images.naming import docker_uri, ngc_image_ref, remote_sif_name, validate_version
from vector_sim.images.ngc import (
    ENV_PASSWORD,
    ENV_USERNAME,
    NgcCredentials,
    PullPipeline,
    credentials_from_env,
)

SIF = "/scratch/alice/isaaclab-containers/isaac-lab-3.0.0.sif"
KEY = "nvapi-super-secret-key"


def _store(tmp_path: Path) -> ConfigStore:
    store = ConfigStore(tmp_path / "cfg")
    profile = bonecho_defaults()
    profile.remote_user = "alice"
    profile.scratch_dir = "/scratch/alice"
    VectorSlurmAdapter().derive_scratch_paths(profile)
    store.save_profile(profile)
    store.set_active("bonecho")
    return store


def _creds() -> NgcCredentials:
    return NgcCredentials("$oauthtoken", KEY)


def _pull_calls(fake: FakeExecute) -> list[list[str]]:
    return [c for c in fake.calls if "pull" in c[-1]]


def test_naming_points_at_official_ngc_image() -> None:
    assert ngc_image_ref("2.3.2") == "nvcr.io/nvidia/isaac-lab:2.3.2"
    assert docker_uri("2.3.2") == "docker://nvcr.io/nvidia/isaac-lab:2.3.2"
    assert remote_sif_name("2.3.2") == "isaac-lab-2.3.2.sif"


@pytest.mark.parametrize("bad", ["", "2.3.2; rm -rf ~", "a b", "$(id)", "-x", "../x"])
def test_version_is_validated_before_reaching_a_shell(bad: str) -> None:
    with pytest.raises(ConfigError):
        validate_version(bad)


def test_credentials_from_env_defaults_username() -> None:
    assert credentials_from_env({}) is None
    assert credentials_from_env({ENV_USERNAME: "u"}) is None
    only_key = credentials_from_env({ENV_PASSWORD: KEY})
    assert only_key == NgcCredentials("$oauthtoken", KEY)
    both = credentials_from_env({ENV_USERNAME: "me", ENV_PASSWORD: KEY})
    assert both and both.username == "me"
    assert KEY not in repr(both)


def test_pull_sends_credentials_on_stdin_not_argv(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    runner = CommandRunner(execute=fake)
    code = DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=_creds())).run(cluster="bonecho")
    assert code == 0
    (call,) = _pull_calls(fake)
    joined = " ".join(call)
    assert KEY not in joined and "oauthtoken" not in joined
    assert "docker://nvcr.io/nvidia/isaac-lab:3.0.0" in joined
    assert "module load apptainer" in joined
    assert SIF in joined and f"{SIF}.partial" in joined
    assert fake.inputs[fake.calls.index(call)] == f"$oauthtoken\n{KEY}\n"
    assert store.load_profile("bonecho").image.version == "3.0.0"


def test_pull_skipped_when_sif_already_present(tmp_path: Path, capsys) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    fake.add("test -s", stdout="SIF_PRESENT\n")
    runner = CommandRunner(execute=fake)
    DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=_creds())).run(cluster="bonecho")
    assert _pull_calls(fake) == []
    assert "Pull                SKIPPED" in capsys.readouterr().out


def test_force_repulls_existing_sif(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    fake.add("test -s", stdout="SIF_PRESENT\n")
    runner = CommandRunner(execute=fake)
    DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=_creds())).run(
        cluster="bonecho", force=True
    )
    assert len(_pull_calls(fake)) == 1


def test_explicit_version_is_used_and_saved(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    runner = CommandRunner(execute=fake)
    DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=_creds())).run(
        cluster="bonecho", image_version="2.3.1"
    )
    (call,) = _pull_calls(fake)
    assert "docker://nvcr.io/nvidia/isaac-lab:2.3.1" in " ".join(call)
    assert "isaac-lab-2.3.1.sif" in " ".join(call)
    assert store.load_profile("bonecho").image.version == "2.3.1"


def test_missing_credentials_fail_before_any_pull(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    runner = CommandRunner(execute=fake)
    with pytest.raises(ConfigError) as exc:
        DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=None)).run(cluster="bonecho")
    assert ENV_PASSWORD in str(exc.value)
    assert "NGC API key" in (exc.value.suggestion or "")
    assert _pull_calls(fake) == []


def test_plan_probes_but_never_pulls(tmp_path: Path, capsys) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    runner = CommandRunner(execute=fake)
    code = DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=None)).run(
        cluster="bonecho", plan=True
    )
    out = capsys.readouterr().out
    assert code == 0
    assert _pull_calls(fake) == []
    assert "nvcr.io/nvidia/isaac-lab:3.0.0" in out
    assert "Pull                REQUIRED" in out
    assert "NGC credentials     missing" in out
    assert "plan only" in out


def test_failed_pull_redacts_key_and_hints_at_credentials(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    fake.add(
        lambda args: "pull" in args[-1],
        returncode=255,
        stderr=f"FATAL: 401 Unauthorized for user with key {KEY}\n",
    )
    runner = CommandRunner(execute=fake)
    with pytest.raises(VectorSimError) as exc:
        DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=_creds())).run(cluster="bonecho")
    report = exc.value.format_report()
    assert KEY not in report
    assert "NGC rejected the credentials" in report


def test_dry_run_does_not_pull_or_need_credentials(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fake = FakeExecute()
    runner = CommandRunner(dry_run=True, execute=fake)
    code = DeployCommand(runner, store, pipeline=PullPipeline(runner, credentials=None)).run(cluster="bonecho")
    assert code == 0
    assert _pull_calls(fake) == []
