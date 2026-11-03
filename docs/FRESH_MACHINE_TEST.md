# Fresh-machine acceptance test

Assume:

- Ubuntu-like laptop
- no existing `vector-sim` state
- no Isaac Lab clone
- a working Bonecho or Killarney account

Do **not** treat this as a script to run unattended. Several steps are
intentionally manual.

## Procedure

1. Clone vector-sim and `cd` into it.
2. `source ./activate.sh` (no virtual environment or package install).
3. Optionally add `source /absolute/path/to/vector-sim/activate.sh` to `~/.bashrc`.
4. `vector-sim bootstrap` (and `bootstrap --install` only to print commands).
5. Configure the cluster SSH alias in `~/.ssh/config` (tool will not write it).
6. Authenticate / MFA: `vector-sim auth <cluster>`.
7. `vector-sim onboard <cluster>`.
8. `vector-sim doctor --cluster <cluster>` — expect `Overall: READY`.
9. Export `APPTAINER_DOCKER_USERNAME='$oauthtoken'` and `APPTAINER_DOCKER_PASSWORD=<NGC API key>`, then `vector-sim deploy --cluster <cluster>` — the first pull of the NGC image (~20 GiB) is expensive.
10. `vector-sim smoke-test --cluster <cluster> --video`.
11. Verify job `COMPLETED` / ExitCode `0:0`
12. Verify an MP4 exists with `vector-sim videos --cluster <cluster>`.
13. Re-run `vector-sim onboard <cluster>` and `vector-sim deploy --cluster <cluster> --plan` and confirm `Pull SKIPPED` and the doctor's `remote SIF READY`.

## Intentionally manual

| Step | Why |
| --- | --- |
| Editing `~/.ssh/config` | Tool must not rewrite SSH config |
| MFA / `vector-sim auth` | Keyboard-interactive; no secret storage |
| Creating the NGC account and API key | Needs your NVIDIA login |
| First `deploy` | Multi-GB `apptainer pull` from `nvcr.io` on the cluster |

## Pass criteria

- Onboard is idempotent on a second run
- Deploy skips the pull when the SIF for that version already exists
- Smoke-test Cartpole completes with `0:0`
- At least one MP4 is listed or pulled
- No edits to Isaac Lab `docker/cluster/` scripts
