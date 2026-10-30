# vector-sim

Vector Sim deploys reproducible Isaac Lab workloads to SLURM clusters over SSH
and Apptainer. It supports both **Bonecho** and **Killarney**. Cluster behavior
and paths are discovered during onboarding.

The tool uses NVIDIA's **official Isaac Lab container** from NGC. There is
nothing to build locally and no Docker is needed anywhere: the image is pulled
directly on the cluster with Apptainer.

The tool generates its own runtime wrappers; do **not** edit Isaac Lab's
`docker/cluster/` scripts. Ordinary changes under Isaac Lab's `source/` or
`scripts/` directories are synchronized per job and never touch the image.
Make sure rhe Isaac Lab version that you clone matches the Docker Image that you pull with `deploy`.

## Quick start: use NVIDIA's Isaac Lab image on the cluster

Docker does not work on the clusters, so the official image is pulled with
**Apptainer** instead. Vector Sim automates this end to end.

1. **Create an NVIDIA NGC account** (free) at <https://ngc.nvidia.com> and
   generate an API key at <https://org.ngc.nvidia.com/setup/api-keys>.

2. **Pick the Isaac Lab version** you want from the
   [Isaac Lab catalog page](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-lab/tags).
   Each tag is a release, for example
   `nvcr.io/nvidia/isaac-lab:2.3.2` (the default).

3. **Export your NGC credentials** on the machine where you run `vector-sim`.
   For NGC the username is the literal string `$oauthtoken` (keep the single
   quotes) and the password is your API key:

   ```bash
   export APPTAINER_DOCKER_USERNAME='$oauthtoken'
   export APPTAINER_DOCKER_PASSWORD='<your NGC API key>'
   ```

   If you only set `APPTAINER_DOCKER_PASSWORD`, the username defaults to
   `$oauthtoken`. The key is sent to the cluster over SSH stdin for the pull;
   it is never put on a command line, in a file, or in the profile. You can also save your credentials in `~/.bashrc`.

4. **Choose your Isaac Lab Version to Match the Docker Image**
   Before everything, decide what version you want to install and work with. Clone the correct version manually at a selected path. We suggest that you clone it in the same parent directory as `vector-sim`.
   The lates version as of October 2026 is v3.0.0.
   ```bash
   cd ..
   git clone --branch v3.0.0 https://github.com/isaac-sim/IsaacLab.git IsaacLab
   ```
   Then pass that path to onboard.

5. **Pull the image and run Isaac Lab:**
   Before pulling the image, make sure to configure your SSH by modifying `~/.ssh/config` according to the guide.
   Then run :

   ```bash
   source ./activate.sh
   vector-sim --version
   vector-sim auth bonecho
   # OR
   vector-sim auth killarney
   ```
   After authentication is complete, run:
   
   ```bash
   vector-sim onboard bonecho --isaaclab /absolute/path/to/IsaacLab  # once per cluster (see section 3)
   ```

   ```bash

   # type exit in terminal to get back to the workflow
   vector-sim deploy --cluster bonecho --image-version 3.0.0    # or another release
   vector-sim run --cluster bonecho --task Isaac-Cartpole
   ```

   `deploy` runs `apptainer pull docker://nvcr.io/nvidia/isaac-lab:<version>` on
   the cluster and stores `isaac-lab-<version>.sif` under the profile's
   containers directory (about 20 GiB; plan for ~40 GiB free while it
   converts). It is skipped when the SIF is already there; `--force` re-pulls.
   `deploy --plan` shows what would happen without pulling.

   The image will be automatically pulled and saved at your `/scratch/$USER_ID$`. Before running `deploy`, you can change the default destination of the image to a directory with more available space if you want. In order to do that, change `paths.containers` in `vector-sim/.vector-sim/bonecho.yaml` and add `- paths.containers` under `user_set`.

To do the same pull by hand on a cluster login node:

```bash
module load apptainer
export APPTAINER_DOCKER_USERNAME='$oauthtoken'
export APPTAINER_DOCKER_PASSWORD='<your NGC API key>'
apptainer pull isaac-lab-2.3.2.sif docker://nvcr.io/nvidia/isaac-lab:3.0.0 
```

5. **If you have already deployed vector-sim:**
Repeat the authentication step:


Then run doctor to make sure Image also is pulled. You should see 

Overall:
  READY

This guide uses `<cluster>` where the value is either `bonecho` or
`killarney`. Operational examples always pass `--cluster` so it is clear where
the command runs.

## 1. Install the package

Clone the repository:

```bash
git clone git@github.com:VectorInstitute/vector-sim.git
cd vector-sim
```

Vector Sim does not require a virtual environment or `pip install`. Source the
repository setup script once:

```bash
source ./activate.sh
vector-sim --version
```

To make the command available in every Bash session, add the **absolute** path
to `~/.bashrc`:

```bash
echo 'source /absolute/path/to/vector-sim/activate.sh' >> ~/.bashrc
source ~/.bashrc
```

The launcher uses system `python3` and expects Python 3.10+ and PyYAML. On
Ubuntu, install PyYAML only if the launcher reports it missing:

```bash
sudo apt install python3-yaml
```

## 2. Local setup

The laptop needs:

- Python 3.10+, PyYAML, `git`, `ssh`, and `rsync`
- An NVIDIA NGC API key exported as `APPTAINER_DOCKER_PASSWORD` (see the quick start)

Docker and a local Apptainer are **not** required; the image is pulled on the
cluster.

Inspect local prerequisites. This command reports required actions but never
runs `sudo`:

```bash
vector-sim bootstrap
```

### Configure SSH aliases

Vector Sim does not modify `~/.ssh/config` or bypass MFA. Add entries for each
cluster you use:

```sshconfig
Host bonecho
    HostName bonecho.vectorinstitute.ai
    User <your-user>
    ControlMaster auto
    ControlPersist 10m
    ControlPath ~/.ssh/cm-%C

Host killarney
    HostName killarney.alliancecan.ca
    User <your-user>
    ControlMaster auto
    ControlPersist 10m
    ControlPath ~/.ssh/cm-%C
```

Authenticate to each cluster once to establish its multiplexed SSH session:

```bash
vector-sim auth bonecho
vector-sim auth killarney
```

If a later command reports BatchMode or authentication failure, rerun
`vector-sim auth <cluster>`.

## 3. One-time onboarding and deployment on each cluster

Onboarding discovers the selected cluster's login-shell requirements, scratch
path, SLURM GPU partitions, and Apptainer module. It then writes a profile and
generated wrappers under `.vector-sim/`.

If Isaac Lab is already cloned:

```bash
vector-sim onboard bonecho --isaaclab /absolute/path/to/IsaacLab
vector-sim onboard killarney --isaaclab /absolute/path/to/IsaacLab
```

Without `--isaaclab`, onboarding finds an existing checkout or offers the
pinned clone:

```bash
vector-sim onboard bonecho
vector-sim onboard killarney
```

Verify each profile:

```bash
vector-sim doctor --cluster bonecho
vector-sim doctor --cluster killarney
```

The expected result is `Overall: READY`.

Pull the official NGC container onto every cluster you will use. `--plan`
only checks the cluster and prints what would happen:

```bash
# Bonecho
vector-sim deploy --cluster bonecho --plan
vector-sim deploy --cluster bonecho

# Killarney
vector-sim deploy --cluster killarney --plan
vector-sim deploy --cluster killarney
```

The first deployment downloads `nvcr.io/nvidia/isaac-lab:<version>` (about
20 GiB) straight to the selected cluster using the `APPTAINER_DOCKER_USERNAME`
and `APPTAINER_DOCKER_PASSWORD` environment variables. Nothing is built or
uploaded from your machine. The pull goes to a `.partial` file and is renamed
only when complete, so an interrupted pull is simply rerun.

A later deployment of the same version reports:

```text
Pull                SKIPPED
```

Optionally run the acceptance workload on each cluster:

```bash
vector-sim smoke-test --cluster bonecho --video
vector-sim smoke-test --cluster killarney --video
```

## 4. Run jobs

Always pass `--cluster` to avoid submitting to the wrong active profile.

### Submit

```bash
# Bonecho
vector-sim run --cluster bonecho \
  --task Isaac-Cartpole

# Killarney
vector-sim run --cluster killarney \
  --task Isaac-Cartpole
```

Source is synchronized into a new scratch run directory on the selected
cluster. The job uses the container deployed in step 3.

### Interactive GUI

`vector-sim gui` submits an Isaac Sim GUI session and waits until it is
reachable in a browser. On the compute node the path is:

```text
Isaac Sim GUI → Xvfb → x11vnc on 127.0.0.1 → noVNC/websockify
```

Vector Sim then prints an SSH local forward and a localhost URL. It does not
open a browser or keep the tunnel process running. This does not use Isaac Sim
WebRTC or livestream.

```bash
vector-sim gui --cluster bonecho --time 3h
```

Leave the printed `ssh -N -L` command running, then open the printed
`http://127.0.0.1:<port>/vnc.html?autoconnect=1&resize=remote` URL.

The same job id works with `status`, `logs`, and `cancel`. After the session
is ready, `vector-sim status --cluster <cluster> <job-id>` prints the tunnel
again.

The first GUI run builds x11vnc and noVNC 1.5.0 once under the cluster cache
at `<cache>/gui/`. Later runs reuse that directory. The build does not use
apt or sudo and does not rebuild the Isaac image. Job cleanup does not delete
the cache.

Xvfb uses the first free display in `:90`–`:119` at `1920x1080x24`
(`--resolution` overrides the size). Raw VNC stays on localhost. Only the
noVNC port is reachable from the login node, and only through the SSH tunnel.
`--partition`, `--gpu`, `--cpus`, `--memory`, and `--time` match `run`. The
default experience is `scripts/tutorials/00_sim/create_empty.py`.

The compute node needs `Xvfb`, `xdpyinfo`, `curl`, and `websockify` on `PATH`.
The one-time login-node build also needs `cmake`, a C compiler, and X11
headers. This flow was exercised on Bonecho.

Resource settings can be overridden per job:

```bash
vector-sim run --cluster killarney \
  --task Isaac-Cartpole-v0 \
  --partition gpubase_l40s_b1 \
  --gpu l40s --gpus 1 \
  --cpus 8 --memory 32G --time 1h \
  --headless
```

### Monitor and manage

Use the same cluster for all operations on a job:

```bash
vector-sim status --cluster <cluster>
vector-sim status --cluster <cluster> <job-id>
vector-sim logs --cluster <cluster> <job-id>
vector-sim logs --cluster <cluster> <job-id> --follow
vector-sim cancel --cluster <cluster> <job-id>
```

### Retrieve videos

```bash
vector-sim videos --cluster <cluster>
vector-sim pull-video --cluster <cluster> --latest
```

## What is cached

| Item | Reused when | Changes when |
| --- | --- | --- |
| Cluster SIF (`isaac-lab-<version>.sif`) | The file already exists for that version | You run `deploy --force`, or pick another `--image-version` |
| Apptainer layer cache | Under `<containers>/.apptainer/` on the cluster | Pulling a new version |
| Runtime source | Never treated as image input | Synchronized for every job |

## Troubleshooting

| Problem | Next step |
| --- | --- |
| `vector-sim` not found | `source /absolute/path/to/vector-sim/activate.sh` |
| PyYAML missing | `sudo apt install python3-yaml` |
| `APPTAINER_DOCKER_PASSWORD is not set` | Export your NGC API key; see the quick start |
| NGC rejected the credentials (401) | Username must be the literal `$oauthtoken` (single-quoted); regenerate the API key if needed |
| Tag not found | Pick a tag from the [NGC tags page](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-lab/tags) |
| Pull ran out of disk | Free ~40 GiB under the containers directory on the cluster, then rerun `deploy` |
| SSH alias missing | Add `Host bonecho` or `Host killarney` to `~/.ssh/config` |
| MFA session expired | `vector-sim auth <cluster>` |
| Isaac Lab missing | `vector-sim onboard <cluster> --isaaclab /path/to/IsaacLab` |
| Container missing on the cluster | `vector-sim deploy --cluster <cluster>` |
| SLURM, scratch, or Apptainer issue | `vector-sim doctor --cluster <cluster>` |
| Pull interrupted | Rerun `vector-sim deploy --cluster <cluster>` |
| GUI startup failed | The error names the component and its log under the run's `logs/gui/` |
| `Xvfb` or `websockify` missing | Those tools must already be on the compute node; GUI mode does not install them with apt |

## Architecture and lower-level commands

Vector Sim separates the user-facing cluster profile name, SSH alias, and
cluster implementation. Discovery allows Bonecho and Killarney to use their
own home paths, scratch paths, modules, and GPU partitions without treating
either cluster's settings as universal defaults.

Most users need only `bootstrap`, `auth`, `onboard`, `doctor`, `deploy`, `run`,
`gui`, and the monitoring commands. Lower-level commands such as `init`,
`setup`, and `shell` remain available. The former local `build` and `push`
commands were removed in favor of `deploy`.

Historical acceptance evidence is in
[docs/KNOWN_GOOD.md](docs/KNOWN_GOOD.md). The clean-machine checklist is in
[docs/FRESH_MACHINE_TEST.md](docs/FRESH_MACHINE_TEST.md).
