"""Pull the official NVIDIA Isaac Lab image onto the cluster with Apptainer.

Docker is not available on the clusters, so the image is pulled straight from
NGC (``nvcr.io``) into a SIF under the profile's containers directory. NGC
credentials come from ``APPTAINER_DOCKER_USERNAME`` / ``APPTAINER_DOCKER_PASSWORD``
(for NGC the username is the literal ``$oauthtoken`` and the password is an NGC
API key). They are sent to the cluster over SSH stdin, never in a command line.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field

from vector_sim.config.models import ClusterProfile
from vector_sim.errors import ConfigError, VectorSimError
from vector_sim.exec import CommandRunner
from vector_sim.images.naming import (
    NGC_CATALOG_URL,
    NGC_REGISTRY,
    docker_uri,
    ngc_image_ref,
    remote_sif_name,
)
from vector_sim.ssh.session import SshSession

ENV_USERNAME = "APPTAINER_DOCKER_USERNAME"
ENV_PASSWORD = "APPTAINER_DOCKER_PASSWORD"
NGC_OAUTH_USERNAME = "$oauthtoken"

NGC_KEY_HELP = (
    "Create a free NVIDIA NGC account, generate an API key at https://org.ngc.nvidia.com/setup/api-keys, "
    f"then: export {ENV_USERNAME}='{NGC_OAUTH_USERNAME}' {ENV_PASSWORD}='<your NGC API key>'"
)


@dataclass(frozen=True)
class NgcCredentials:
    username: str
    password: str = field(repr=False)


def credentials_from_env(env: Mapping[str, str] | None = None) -> NgcCredentials | None:
    """Read NGC credentials; the username defaults to ``$oauthtoken`` when only a key is set."""
    source = os.environ if env is None else env
    password = source.get(ENV_PASSWORD, "")
    if not password:
        return None
    return NgcCredentials(source.get(ENV_USERNAME) or NGC_OAUTH_USERNAME, password)


def remote_sif_path(containers_dir: str, version: str) -> str:
    return f"{containers_dir.rstrip('/')}/{remote_sif_name(version)}"


@dataclass
class PullOutcome:
    version: str
    ngc_image: str
    remote_path: str
    pull_action: str  # SKIPPED | REQUIRED | PULLED
    credentials: str  # set | missing
    notes: list[str] = field(default_factory=list)


class PullPipeline:
    def __init__(
        self,
        runner: CommandRunner,
        *,
        credentials: NgcCredentials | None | str = "env",
    ) -> None:
        self.runner = runner
        self._credentials = credentials_from_env() if credentials == "env" else credentials

    def _session(self, profile: ClusterProfile) -> SshSession:
        return SshSession(
            profile.ssh_alias,
            self.runner,
            login_shell=profile.scheduler.remote_shell == "login",
        )

    def _containers_dir(self, profile: ClusterProfile) -> str:
        if not profile.paths.containers:
            raise ConfigError(
                "profile is missing paths.containers",
                suggestion=f"Run: vector-sim onboard {profile.name}, then vector-sim deploy",
            )
        return profile.paths.containers

    def _probe(self, session: SshSession, remote_path: str) -> bool | None:
        """True/False if the SIF is present, None if the cluster could not be reached or in dry-run."""
        result = session.exec(
            f"test -s {shlex.quote(remote_path)} && echo SIF_PRESENT",
            category="ssh-preflight",
            check=False,
            dry_run_skip=False,
        )
        if result.skipped:
            return None
        if "SIF_PRESENT" in result.stdout:
            return True
        if result.returncode not in (0, 1):
            return None
        return False

    def preview(self, *, profile: ClusterProfile, version: str, force: bool = False) -> PullOutcome:
        """Read-only plan: probes whether the SIF already exists, never pulls."""
        remote = remote_sif_path(self._containers_dir(profile), version)
        present = self._probe(self._session(profile), remote)
        notes: list[str] = []
        if present is None:
            action = "REQUIRED"
            notes.append("could not check the cluster; run vector-sim auth if the session expired")
        elif present and not force:
            action = "SKIPPED"
        else:
            action = "REQUIRED"
        if action == "REQUIRED" and self._credentials is None:
            notes.append(f"{ENV_PASSWORD} is not set. {NGC_KEY_HELP}")
        return self._outcome(version, remote, action, notes)

    def run(self, *, profile: ClusterProfile, version: str, force: bool = False) -> PullOutcome:
        containers = self._containers_dir(profile)
        remote = remote_sif_path(containers, version)
        session = self._session(profile)

        present = self._probe(session, remote)
        if present and not force:
            return self._outcome(version, remote, "SKIPPED", ["SIF already on the cluster; use --force to re-pull"])

        creds = self._credentials
        if creds is None and not self.runner.dry_run:
            raise ConfigError(
                f"{ENV_PASSWORD} is not set; cannot pull {ngc_image_ref(version)} from NGC",
                suggestion=NGC_KEY_HELP,
            )

        self.runner.emit(f"Pulling {ngc_image_ref(version)} on {profile.ssh_alias} (about 20 GiB; this takes a while)...")
        args = session.ssh_prefix()
        # Keep the connection alive through the long, quiet layer download.
        args[1:1] = ["-o", "ServerAliveInterval=30"]
        payload = f"{creds.username}\n{creds.password}\n" if creds else None
        script = self._pull_script(profile, containers, version, remote)
        remote_cmd = script if not session.login_shell else "bash -l -c " + shlex.quote(script)
        result = self.runner.run(
            args + [remote_cmd],
            category="apptainer-pull",
            check=False,
            input_text=payload,
        )
        if result.skipped:
            return self._outcome(version, remote, "REQUIRED", ["dry-run; nothing pulled"])
        if result.returncode != 0:
            raise VectorSimError(
                f"apptainer pull of {ngc_image_ref(version)} failed with exit status {result.returncode}",
                category="apptainer-pull",
                exit_status=result.returncode,
                stderr=_redact(result.stderr, creds),
                suggestion=_pull_failure_hint(result.stderr, version),
            )
        return self._outcome(version, remote, "PULLED", [])

    def _outcome(self, version: str, remote: str, action: str, notes: list[str]) -> PullOutcome:
        return PullOutcome(
            version=version,
            ngc_image=ngc_image_ref(version),
            remote_path=remote,
            pull_action=action,
            credentials="set" if self._credentials else "missing",
            notes=notes,
        )

    @staticmethod
    def _pull_script(profile: ClusterProfile, containers: str, version: str, remote: str) -> str:
        command = profile.apptainer.command or "singularity"
        partial = f"{remote}.partial"
        work = f"{containers.rstrip('/')}/.apptainer"
        module = f"module load {shlex.quote(profile.apptainer.module)}\n" if profile.apptainer.module else ""
        # Credentials arrive on stdin (two lines) so they never appear in argv or `ps`.
        # Both prefixes are exported so apptainer and older singularity both see them.
        return f"""set -e
IFS= read -r _vs_user
IFS= read -r _vs_pass
export APPTAINER_DOCKER_USERNAME="$_vs_user" APPTAINER_DOCKER_PASSWORD="$_vs_pass"
export SINGULARITY_DOCKER_USERNAME="$_vs_user" SINGULARITY_DOCKER_PASSWORD="$_vs_pass"
unset _vs_user _vs_pass
{module}mkdir -p {shlex.quote(containers)} {shlex.quote(work)}/cache {shlex.quote(work)}/tmp
export APPTAINER_CACHEDIR={shlex.quote(work)}/cache APPTAINER_TMPDIR={shlex.quote(work)}/tmp
export SINGULARITY_CACHEDIR=$APPTAINER_CACHEDIR SINGULARITY_TMPDIR=$APPTAINER_TMPDIR
trap 'rm -f {shlex.quote(partial)}' EXIT
{command} pull --force {shlex.quote(partial)} {shlex.quote(docker_uri(version))}
mv -f {shlex.quote(partial)} {shlex.quote(remote)}
trap - EXIT
"""


def _redact(text: str, creds: NgcCredentials | None) -> str:
    if creds and creds.password:
        return text.replace(creds.password, "***")
    return text


def _pull_failure_hint(stderr: str, version: str) -> str:
    low = stderr.lower()
    if "401" in low or "unauthorized" in low or "denied" in low or "authentication" in low:
        return f"NGC rejected the credentials. {NGC_KEY_HELP}"
    if "not found" in low or "manifest unknown" in low or "404" in low:
        return f"Tag {version!r} not found; see available tags at {NGC_CATALOG_URL}/tags"
    if "no space" in low or "quota" in low:
        return "Out of disk space on the cluster; the pull needs roughly 40 GiB free under the containers directory."
    return f"Retry vector-sim deploy; check {NGC_REGISTRY} reachability from the cluster login node."


def format_pull_report(outcome: PullOutcome) -> str:
    lines = [
        f"Isaac Lab version   {outcome.version}",
        f"NGC image           {outcome.ngc_image}",
        f"Remote SIF          {outcome.remote_path}",
        f"NGC credentials     {outcome.credentials} ({ENV_USERNAME}/{ENV_PASSWORD})",
        f"Pull                {outcome.pull_action}",
    ]
    lines.extend(f"note                {note}" for note in outcome.notes)
    return "\n".join(lines)
