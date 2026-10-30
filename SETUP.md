# Setting up Isaac Lab on Bon Echo with vector-sim

A step-by-step guide. The full reference is the [README](README.md); this page
is the short path from zero to a running Isaac Lab job.

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

| Piece | What it is | Plain-English role |
| --- | --- | --- |
| **vector-sim** | A small Python CLI (no install needed) | The remote control. It runs the other steps for you. |
| **Isaac Lab (git clone)** | Your code: tasks, training scripts | *What* you run. You edit this. |
| **The container image (`.sif`)** | NVIDIA's official Isaac Lab, packaged as one ~12 GB file | *Where* it runs. Isaac Sim and all dependencies are inside, so nothing is installed on the cluster. |
| **SLURM** | The cluster's job queue | Gives your job a GPU. |
| **Apptainer** | The container runtime (Docker isn't allowed on HPC) | Opens the `.sif` on the GPU node. |

Every time you `vector-sim run`, it copies your Isaac Lab code to scratch,
writes a SLURM job script, submits it, and the job starts the container with
your code mounted in. **You edit code, not the image.**

## Where do I run this? (read this first)

**Run every `vector-sim` command on your own computer (laptop or desktop),
not on the cluster.**

```
 YOUR LAPTOP  (you type everything here)          BON ECHO CLUSTER (you never type here)
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

**Do not** run vector-sim while logged into the cluster (login node, VS Code
Remote-SSH, `srun`/`salloc`). The cluster would SSH into itself. That can be made to work
(see the note in step 5) but needs extra SSH tweaks and is the main source of
confusion. Never run it from a compute node.

Each step below is tagged **[laptop]** (your computer) or **[browser]**.
Nothing in this guide asks you to type on the cluster.

Your laptop needs: Linux, macOS, or Windows with WSL; `git`, `ssh`, `rsync`;
Python 3.10+ with PyYAML (`pip install pyyaml` if it is missing).
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
source ./activate.sh          # adds `vector-sim` to your PATH for this shell
vector-sim --version
```
To have it in every new shell, add `source /absolute/path/to/vector-sim/activate.sh`
to `~/.bashrc`. It needs `python3` (3.10+ recommended) with PyYAML.

### 4. Clone Isaac Lab, matching the image version  [laptop]
The code you clone and the container you pull **must be the same version**,
otherwise you will get confusing errors.
```bash
cd ..    # clone next to vector-sim
git clone --branch v3.0.0 https://github.com/isaac-sim/IsaacLab.git IsaacLab
```
(`v3.0.0` here goes with `--image-version 3.0.0` in step 6.)

### 5. Tell SSH how to reach Bon Echo, and log in  [laptop]
vector-sim talks to the cluster through `ssh bonecho`, so that alias must exist.
It never edits your SSH config. Add to `~/.ssh/config` **on your laptop**:

```sshconfig
Host bonecho
    HostName bonecho.vectorinstitute.ai
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
```bash
vector-sim onboard bonecho --isaaclab /absolute/path/to/IsaacLab   # path on YOUR laptop
vector-sim deploy  --cluster bonecho --image-version 3.0.0
vector-sim doctor  --cluster bonecho
```
- **onboard** inspects the cluster (scratch path, GPU partitions, Apptainer
  module) and writes a profile to `.vector-sim/bonecho.yaml`.
- **deploy** downloads the image onto the cluster (~12-20 GB, takes a while,
  needs ~40 GB free while converting). It is skipped if already there.
  `deploy --plan` previews without downloading.
- **doctor** runs every check. You want to see:
  ```
  Overall:
    READY
  ```

> **Where does the image go?** By default under your `/scratch/<user>/`.
> Scratch is small (94 GB total here), so you can move it to project space by
> setting `paths.containers` in `.vector-sim/bonecho.yaml` and adding
> `- paths.containers` under `user_set:` in the same file, **before** running
> `deploy`. `/fs02/projects` is nearly full (95%), so check `df -h` first.

## Everyday use  [laptop]

```bash
source ./activate.sh                      # once per new shell
vector-sim auth bonecho                   # only if MFA expired

vector-sim run --cluster bonecho --task Isaac-Cartpole      # submit a training job
vector-sim status --cluster bonecho                          # what's running?
vector-sim logs   --cluster bonecho <job-id> --follow       # watch output
vector-sim cancel --cluster bonecho <job-id>                # stop it

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

## Troubleshooting

| You see | What it means / fix |
| --- | --- |
| `vector-sim: command not found` | `source /path/to/vector-sim/activate.sh` |
| `Permission denied (keyboard-interactive)` / BatchMode | MFA session expired: `vector-sim auth bonecho` |
| doctor says `remote SIF NEEDS DEPLOY` but you already pulled | Usually just the line above: doctor can't see the cluster without a live SSH session. Re-auth and rerun `doctor`. |
| `APPTAINER_DOCKER_PASSWORD is not set` | Do step 2 and `source ~/.bashrc` |
| NGC 401 error | Username must be exactly `$oauthtoken` in single quotes; regenerate the key if needed |
| Pull runs out of disk | Free ~40 GB under the containers dir, rerun `deploy` |
| Weird errors at startup | Isaac Lab clone and image versions differ. Check `git describe --tags` in IsaacLab against `image.version` in `.vector-sim/bonecho.yaml` |
| `ssh bonecho` times out | You are probably logged into the cluster. Run vector-sim from your laptop instead (see "Where do I run this?"), or use the advanced internal-host config in step 5 |
| Any other cluster issue | `vector-sim doctor --cluster bonecho` names the failing check |

## Mental checklist

1. Key in shell? 2. `source activate.sh`? 3. MFA session alive (`auth`)? 4. Isaac Lab and image on the same version? 5. `doctor` says READY?

If all five are yes, `vector-sim run` will work.
