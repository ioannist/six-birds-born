# Source this file from Bash in each shell used for reproduction.
# Preserve explicit output/cache/toolchain choices; defaults live in scratch/.
_born_checkout="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for _born_bin in "$HOME/.elan/bin" "$HOME/.cargo/bin"; do
    case ":$PATH:" in
        *":$_born_bin:"*) ;;
        *) PATH="$_born_bin:$PATH" ;;
    esac
done
export PATH
export RUSTUP_TOOLCHAIN="${RUSTUP_TOOLCHAIN-1.93.1}"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
export DATA_OUT="${DATA_OUT-$_born_checkout/scratch/reproduction}"
export BORN_LADDER_ENV_ROOT="${BORN_LADDER_ENV_ROOT-$_born_checkout/scratch/environments}"
if [ -z "$DATA_OUT" ] || [ -z "$BORN_LADDER_ENV_ROOT" ]; then
    echo 'DATA_OUT and BORN_LADDER_ENV_ROOT must be nonempty; set them before sourcing env.sh.' >&2
    unset _born_checkout _born_bin
    return 1
fi
unset _born_checkout _born_bin
