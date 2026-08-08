#!/usr/bin/env bash
# Install DVD Maker prerequisites on Ubuntu or Debian.

set -euo pipefail

readonly PACKAGES=(
    python3
    python3-pip
    python3-venv
    make
    ffmpeg
    dvdauthor
    genisoimage
    lsdvd
)

# ffprobe is provided by ffmpeg; spumux and dvdunauthor are provided by
# dvdauthor on Ubuntu and Debian.
readonly REQUIRED_COMMANDS=(
    python3
    make
    ffmpeg
    ffprobe
    dvdauthor
    spumux
    genisoimage
    lsdvd
    dvdunauthor
)

usage() {
    cat <<'EOF'
Usage: ./scripts/setup.sh [--check | --dry-run]

Install DVD Maker's Ubuntu/Debian system prerequisites.

Options:
  --check    Verify that every required command is available without installing.
  --dry-run  Print the apt commands without running them.
  -h, --help Show this help text.
EOF
}

check_commands() {
    local missing=()
    local command_name

    for command_name in "${REQUIRED_COMMANDS[@]}"; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            missing+=("$command_name")
        fi
    done

    if ((${#missing[@]} > 0)); then
        printf 'Missing required commands: %s\n' "${missing[*]}" >&2
        return 1
    fi

    printf 'All DVD Maker system prerequisites are installed.\n'
}

mode="install"
if (($# > 1)); then
    usage >&2
    exit 2
elif (($# == 1)); then
    case "$1" in
        --check) mode="check" ;;
        --dry-run) mode="dry-run" ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
fi

if [[ "$mode" == "check" ]]; then
    check_commands
    exit $?
fi

if ! command -v apt-get >/dev/null 2>&1; then
    printf 'This setup script requires apt-get (Ubuntu or Debian).\n' >&2
    exit 1
fi

privilege_command=()
if ((EUID != 0)); then
    privilege_command=(sudo)
fi

if [[ "$mode" == "dry-run" ]]; then
    printf 'Would run: %sapt-get update\n' "${privilege_command[*]:+${privilege_command[*]} }"
    printf 'Would run: %sapt-get install -y %s\n' \
        "${privilege_command[*]:+${privilege_command[*]} }" "${PACKAGES[*]}"
    exit 0
fi

if ((EUID != 0)) && ! command -v sudo >/dev/null 2>&1; then
    printf 'sudo is required when setup is not run as root.\n' >&2
    exit 1
fi

"${privilege_command[@]}" apt-get update
"${privilege_command[@]}" apt-get install -y "${PACKAGES[@]}"

check_commands

cat <<'EOF'

System setup complete.

To create the Python environment:
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -r requirements.txt -r requirements-dev.txt
EOF
