# vector-sim

Vector Sim deploys reproducible Isaac Lab workloads to SLURM clusters over SSH
and Apptainer. It supports both **Bonecho** and **Killarney**. Cluster behavior
and paths are discovered during onboarding. Vector Sim supports Isaac Lab v3.0.0 by default. For other versions please see [Isaac Sim Version Guide](ISAACLAB_VERSIONS.md)


# Quick Setup: run Isaac Lab on Bon Echo with vector-sim

This is a step-by-step guide from zero to a running Isaac Lab job. For a more detailed documentation of each step, please refer to the [detailed installation guide](#detailed-installation-guide)

## The big picture

Isaac Lab needs a GPU, a lot of specific software, and a way to run on a shared
cluster. vector-sim glues together four things so you don't have to:

```
 You type commands            Login node                 Compute node (GPU)
 ┌──────────────┐  ssh   ┌─────────────────┐  sbatch  ┌───────────────────────┐
 │  vector-sim  │ ─────► │ SLURM scheduler │ ───────► │ Apptainer container   │
 │  (the tool)  │        │ files + image   │          │  = Isaac Sim + Lab    │
 └──────────────┘        └─────────────────┘          │  runs your code       │
                                                      └───────────────────────┘
```

| Piece | What it is | 
| --- | --- |
| **vector-sim** | A small Python CLI (no install needed). It runs the other steps for you. |
| **Isaac Lab (git clone)** | Your code: tasks, training scripts. | 
| **The container image (`.sif`)** | NVIDIA's official Isaac Lab, packaged as one ~12 GB file. Nothing is installed on cluster. |
| **Apptainer** | The container runtime (Docker isn't allowed on HPC). Opens the `.sif` on the GPU node. |  

Every time you `vector-sim run`, it copies your Isaac Lab code to a specified location (scratch by default),
writes a SLURM job script, submits it, and the job starts the container with
your code mounted in. **You edit code, not the image.**

## Where do I run this? (read this first)

**Run every `vector-sim` command on your own computer (laptop or desktop),
not on the cluster.**

```
 YOUR LAPTOP  (write your code)          COMPUTE CLUSTER (it runs here)
 ┌──────────────────────────────────┐   ssh    ┌──────────────────────────────┐
 │ vector-sim/   <- the tool        │ ───────► │ image (.sif), SLURM, GPUs    │
 │ IsaacLab/     <- your code       │  rsync   │ code copied here per job     │
 │ NGC key, SSH config              │ ───────► │ logs and videos land here    │
 └──────────────────────────────────┘ ◄─────── └──────────────────────────────┘
                                       videos
```

- The tool is a remote control. It logs into the cluster for you, so there is
  no need to log in first.
- Your Isaac Lab clone lives on the laptop and is copied to the cluster for
  each job.
- The heavy parts (downloading the image, running on GPUs) happen on the
  cluster automatically.
- `pull-video` downloads results back to the machine you run it on.

**Suggestion: Do not** run vector-sim while logged into the cluster (login node, VS Code
Remote-SSH, `srun`/`salloc`). The cluster would SSH into itself. That can be made to work
(see the note in step 5) but needs extra SSH tweaks and is the main source of
confusion. Never run it from a compute node.

Each step below is tagged **[laptop]** (your computer) or **[browser]**.
Nothing in this guide asks you to type on the cluster.

Your laptop needs: Linux, macOS, or Windows with WSL; `git`, `ssh`, `rsync`;
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) (it provides Python 3.10+ and PyYAML inside a project-local venv).
Docker is **not** needed.

## One-time setup (6 steps)

Do these once. Steps 1-2 are things only you can do (accounts, keys).

### 1. Get an NVIDIA NGC API key  [browser]
The container comes from NVIDIA's registry, which needs a free login.
1. Sign up at <https://ngc.nvidia.com>.
2. Create a key at <https://org.ngc.nvidia.com/setup/api-keys>.

### 2. Put the key in your shell  [laptop]
Add to `~/.bashrc` (or `~/.zshrc` on macOS), then source it:

```bash
export APPTAINER_DOCKER_USERNAME='$oauthtoken'   # literal text, keep the single quotes
export APPTAINER_DOCKER_PASSWORD='<your NGC API key>'
```

### 3. Get vector-sim and activate it  [laptop]
```bash
git clone git@github.com:VectorInstitute/vector-sim.git
cd vector-sim
uv sync                       # creates ./.venv with PyYAML (nothing global)
source ./activate.sh          # adds `vector-sim` to your PATH for this shell
vector-sim --version
```
`uv` is a fast Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/)).
`vector-sim` automatically uses the `.venv` that `uv sync` created, so you don't
need to activate the venv yourself.

### 4. Clone Isaac Lab, matching the image version  [laptop]
The code you clone and the container you pull **must be the same version**,
otherwise you will get confusing errors.
```bash
cd ..    # clone next to vector-sim
git clone --branch v3.0.0 https://github.com/isaac-sim/IsaacLab.git IsaacLab
```
(`v3.0.0` here goes with `--image-version 3.0.0` in step 6.)

### 5. Tell SSH how to reach the cluster, and log in  [laptop]
vector-sim talks to the cluster through `ssh bonecho`, so that alias must exist.
It never edits your SSH config. Add to `~/.ssh/config` **on your laptop**:

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


Now log in once, answering the MFA prompt:
```bash
vector-sim auth bonecho
# you land in an ssh shell on the cluster -> type `exit` to come back
```

<details>
<summary>Advanced: running from the cluster login node instead (not recommended)</summary>

From inside the cluster the public name times out, so point the alias at the
internal login node and use a short `ControlPath`:
```sshconfig
Host bonecho
    HostName blogin02.becho.vectorinstitute.ai
    User <your-user>
    ControlMaster auto
    ControlPersist 10m
    ControlPath /tmp/ssh-cm-%r@%h-%p
```
Everything else is the same, except the paths (`IsaacLab`, `vector-sim`) are
cluster paths. Use this only if you have no way to run locally.
</details>

This keeps an open connection (`ControlPersist 10m`) so later commands don't
ask for MFA again. **It expires** after ~10 idle minutes; rerun `auth` when
any command says "Permission denied" or "BatchMode".

### 6. Onboard, pull the image, verify  [laptop]

#### **onboard** inspects the cluster (scratch path, GPU partitions, Apptainer
  module) and writes a profile to `.vector-sim/bonecho.yaml`.

```bash
vector-sim onboard bonecho --isaaclab /absolute/path/to/IsaacLab   # path on YOUR laptop
```
#### **deploy** downloads the image onto the cluster (~12-20 GB, takes a while,
  needs ~40 GB free while converting). It is skipped if already there.
  `deploy --plan` previews without downloading.
> **Where does the image go?** By default under your `/scratch/<user>/`.
> Scratch is small (94 GB total here), so you can move it to project space by
> setting `paths.containers` in `.vector-sim/bonecho.yaml` and adding
> `- paths.containers` under `user_set:` in the same file, **before** running
> `deploy`. Check the remaining storage by running`df -h` first.

```bash
vector-sim deploy  --cluster bonecho --image-version 3.0.0
```

#### **doctor** runs every check. 
You want to see:
  Overall:
    READY

```bash
vector-sim doctor  --cluster bonecho
```


## Everyday use  [laptop]

```bash
source ./activate.sh                      # once per new shell
vector-sim auth bonecho                   # only if MFA expired, run exit after auth is done

vector-sim run --cluster bonecho --task Isaac-Cartpole      # submit a training job
vector-sim status --cluster bonecho                          # what's running?
vector-sim logs --cluster bonecho <job-id> --follow       # watch output
vector-sim cancel --cluster bonecho <job-id>                # stop the job

vector-sim videos --cluster bonecho                         # list recorded MP4s
vector-sim pull-video --cluster bonecho --latest            # download newest
```

**Smoke test** (recommended the first time; trains Cartpole and records a video):
```bash
vector-sim smoke-test --cluster bonecho --video
```
A healthy run ends `COMPLETED`, exit code `0:0`.

**Interactive GUI in your browser:**
```bash
vector-sim gui --cluster bonecho --time 3h
```
It prints an `ssh -N -L ...` command and a `http://127.0.0.1:<port>/vnc.html...`
URL. Leave the ssh command running and open the URL.

**Change resources per job:**
```bash
vector-sim run --cluster bonecho --task Isaac-Cartpole \
  --partition a100_b1 --gpu a100 --gpus 1 --cpus 8 --memory 32G --time 2h --headless
```
Default is 1x A40 on `a40_b1`, 8 CPUs, 32 GB, 1 hour. Other partitions
(`a100_b*`, `rtx6000_b*`) are listed in `.vector-sim/bonecho.yaml`.
You can manually edit `default_job` in `.vector-sim/bonecho.yaml` or pass it with the command:

```bash
vector-sim gui --cluster bonecho --time 3h --partition rtx6000_b1 --gpu rtx6000
```

You can pass python executables to run your own scene, for example:
```bash
vector-sim gui --cluster bonecho --time 1h --python-executable scripts/tutorials/00_sim/spawn_prims.py

```

When you're done, close the tunnel and free the GPU:

```bash
vector-sim cancel <Job-ID>
```

# Detailed Installation Guide

## 1. Install the package

Clone the repository:

```bash
git clone git@github.com:VectorInstitute/vector-sim.git
cd vector-sim
```

Vector Sim uses a project-local [uv](https://docs.astral.sh/uv/) environment,
so nothing is installed globally. Create it once, then source the setup script:

```bash
uv sync                  # creates ./.venv with PyYAML
source ./activate.sh
vector-sim --version
```

To make the command available in every shell, add the **absolute** path to
`~/.bashrc` (or `~/.zshrc` on macOS):

```bash
echo 'source /absolute/path/to/vector-sim/activate.sh' >> ~/.zshrc
source ~/.zshrc
```

The launcher automatically uses `./.venv/bin/python` when it exists, and falls
back to system `python3` (3.10+ with PyYAML) otherwise.

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
| PyYAML missing | `uv sync` in the vector-sim directory |
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
