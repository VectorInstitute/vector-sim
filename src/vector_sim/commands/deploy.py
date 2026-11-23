"""vector-sim deploy — pull the official NGC Isaac Lab image onto the cluster with Apptainer."""

from __future__ import annotations

from vector_sim.commands.common import require_cluster_profile
from vector_sim.config.store import ConfigStore
from vector_sim.exec import CommandRunner
from vector_sim.images.naming import validate_version
from vector_sim.images.ngc import PullPipeline, format_pull_report


class DeployCommand:
    def __init__(
        self,
        runner: CommandRunner,
        store: ConfigStore,
        *,
        pipeline: PullPipeline | None = None,
    ) -> None:
        self.runner = runner
        self.store = store
        self.pipeline = pipeline or PullPipeline(runner)

    def run(
        self,
        *,
        cluster: str | None,
        image_version: str | None = None,
        plan: bool = False,
        force: bool = False,
    ) -> int:
        profile = require_cluster_profile(self.store, cluster)
        version = validate_version(image_version or profile.image.version)
        if plan or self.runner.dry_run:
            self.runner.emit("Deploy plan (apptainer pull from NGC on the cluster):")
            self.runner.emit(format_pull_report(self.pipeline.preview(profile=profile, version=version, force=force)))
            self.runner.emit("")
            self.runner.emit("plan only; nothing pulled")
            return 0
        outcome = self.pipeline.run(profile=profile, version=version, force=force)
        self.runner.emit(format_pull_report(outcome))
        if not self.runner.dry_run and outcome.pull_action in {"PULLED", "SKIPPED"}:
            profile.image.version = version
            self.store.save_profile(profile)
        return 0
