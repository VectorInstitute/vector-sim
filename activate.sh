#!/usr/bin/env bash
# Source this file (bash or zsh) to make vector-sim available in your shell:
#   source /absolute/path/to/vector-sim/activate.sh
# To have it in every new shell, add that line to ~/.bashrc or ~/.zshrc.

# Path of this file while being sourced. BASH_SOURCE is bash-only; zsh exposes
# the same thing through the %x prompt escape.
if [ -n "${BASH_VERSION:-}" ]; then
    _vector_sim_src="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    _vector_sim_src="${(%):-%x}"
else
    _vector_sim_src="$0"
fi

VECTOR_SIM_HOME="$(cd "$(dirname "${_vector_sim_src}")" >/dev/null 2>&1 && pwd)"
export VECTOR_SIM_HOME
unset _vector_sim_src

case ":${PATH}:" in
    *":${VECTOR_SIM_HOME}/bin:"*) ;;
    *) export PATH="${VECTOR_SIM_HOME}/bin:${PATH}" ;;
esac
