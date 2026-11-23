# Running Isaac Lab 2.x (older releases) with vector-sim

vector-sim supports both Isaac Lab **3.x** (for example `3.0.0`) and **2.x**
(for example `2.3.2`). You do **not** need to change any vector-sim code to use
an older release. You only need to:

1. use an Isaac Lab **checkout** at the older version, and
2. pull the **container image** with the same version.

vector-sim looks at your local checkout to decide which conventions to use, so
the checkout and the image **must be the same version**. If they don't match,
jobs fail. See [Troubleshooting](#troubleshooting).

## What vector-sim does differently for 2.x and 3.x

vector-sim treats a checkout as **3.x** when it has
`scripts/reinforcement_learning/train.py` and does not have
`scripts/reinforcement_learning/rsl_rl/train.py`. Any other checkout is treated
as **2.x**, and the job runs exactly as it did before 3.x support was added.

| | Isaac Lab 2.x | Isaac Lab 3.x |
|---|---|---|
| Training script | `scripts/reinforcement_learning/rsl_rl/train.py` | `scripts/reinforcement_learning/train.py --rl_library rsl_rl` |
| Task names | Have a version suffix: `Isaac-Cartpole-v0` | No suffix: `Isaac-Cartpole` |
| `--headless`, `--enable_cameras` | Passed to the training script | Not passed (3.x rejects them; it runs headless by default and `--video` turns cameras on) |
| GUI session | Script launched as is | `--viz kit` added so a window opens |
| Video library (MoviePy) | Already in the image | Installed once into `<workspace>/python-deps/video` on the first `--video` job |
| Smoke-test task | `Isaac-Cartpole-v0` | `Isaac-Cartpole` |

Both versions share the rest: jobs start through `isaaclab.sh -p` inside the
container, and the wrappers set up `_isaac_sim` and `logs/` in the synced
copy. You never edit these by hand.

## Steps

The examples use Bonecho and Isaac Lab `2.3.2`. For Killarney, replace
`bonecho` with `killarney`. Any 2.x release follows the same steps.

### 1. Pick a version

Pick an image tag from the
[NGC Isaac Lab tags page](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-lab/tags),
for example `2.3.2`. The matching git tag has a `v` in front: `v2.3.2`.

### 2. Clone the matching Isaac Lab version

Use a separate folder so you can keep your 3.x checkout:

```bash
cd ..   # the parent folder of vector-sim
git clone --branch v2.3.2 https://github.com/isaac-sim/IsaacLab.git IsaacLab-2.3.2
```

### 3. Point your cluster profile at that checkout

```bash
source ./activate.sh
vector-sim auth bonecho
vector-sim onboard bonecho --isaaclab /absolute/path/to/IsaacLab-2.3.2
```

This updates `isaaclab_path` in `.vector-sim/bonecho.yaml`.

### 4. Pull the matching image

```bash
vector-sim deploy --cluster bonecho --image-version 2.3.2
```

This pulls `isaac-lab-2.3.2.sif` into the profile's containers directory. It's
about 20 GiB, so allow about 40 GiB free while it converts. It also sets
`image.version: 2.3.2` in the profile, so later `run`, `gui` and `smoke-test`
commands use this image by default. Images you pulled before, such as
`isaac-lab-3.0.0.sif`, stay where they are.

### 5. Check it works

```bash
vector-sim doctor --cluster bonecho          # should end with: READY
vector-sim smoke-test --cluster bonecho --video
```

The smoke test should end with `smoke-test PASS`, `COMPLETED / 0:0` and
`video OK`.

### 6. Run your own tasks

Use the 2.x task names, which end in `-v0`:

```bash
vector-sim run --cluster bonecho --task Isaac-Cartpole-v0
vector-sim run --cluster bonecho --task Isaac-Cartpole-v0 --video
vector-sim gui --cluster bonecho --time 1h
```

To use an RL library other than RSL-RL on 2.x, pass its training script:

```bash
vector-sim run --cluster bonecho --task Isaac-Cartpole-v0 \
  --python-executable scripts/reinforcement_learning/skrl/train.py
```

On 3.x, keep the default script and choose the library with
`--extra-arg=--rl_library --extra-arg=skrl` instead.

## Switching between versions

You can keep both checkouts and both images. Steps 3 and 4 decide which pair
the profile uses:

```bash
# Switch back to 3.0.0 (the deploy is skipped if the SIF is already there)
vector-sim onboard bonecho --isaaclab /absolute/path/to/IsaacLab
vector-sim deploy --cluster bonecho --image-version 3.0.0
```

Always change the checkout and the image together. Passing `--image-version`
to a single `run` doesn't change which checkout is synced, so it only works if
that image matches the profile's checkout.

## What you should not change

- **Don't edit the generated wrappers.** These are `submit_job_slurm.sh`,
  `run_singularity.sh` and `env.cluster`, under `.vector-sim/generated`.
  vector-sim regenerates them for every job.
- **Don't edit Isaac Lab's `docker/cluster/` scripts.** vector-sim doesn't
  use them.
- **Don't add `--rl_library` or `--viz kit` yourself on 2.x.** Those flags
  only exist in 3.x.
- **Don't set `python_executable` in the profile to the 3.x path on 2.x, or
  the reverse.** The default (`scripts/reinforcement_learning/rsl_rl/train.py`)
  works for both: on 3.x it is switched to the new script automatically.

## Troubleshooting

| Symptom in the job log | Likely cause | Fix |
|---|---|---|
| `can't open file '.../rsl_rl/train.py'` | 3.x image with a 2.x checkout | Make the checkout and the image the same version (steps 3–4) |
| `Environment version v0 for environment Isaac-Cartpole doesn't exist` | 3.x checkout, but you used a 2.x task name | Drop the `-v0` suffix |
| A gymnasium error saying `Isaac-Cartpole` doesn't exist | 2.x checkout, but you used a 3.x task name | Add the `-v0` suffix |
| `ModuleNotFoundError` for `torch` or `isaaclab`, or errors from `isaaclab.sh` | The checkout and the image are different versions | Check that `isaaclab_path` and `image.version` in `.vector-sim/bonecho.yaml` match |
| `container not found: .../isaac-lab-<version>.sif` | Image not pulled | `vector-sim deploy --cluster bonecho --image-version <version>` |

## Versions older than 2.x

Isaac Lab 1.x and earlier use a different repository layout and image setup.
They have not been tested with vector-sim and are not supported.
