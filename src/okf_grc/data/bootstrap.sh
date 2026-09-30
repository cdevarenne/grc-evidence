#!/usr/bin/env bash
# Install the pinned scanners into ./.tools of the current directory (git-ignored) and verify their versions.
# The pins come from the tools.lock shipped next to this script.
set -euo pipefail
source "$(dirname "$0")/tools.lock"
TOOLS="$PWD/.tools"
BIN="$TOOLS/bin"
mkdir -p "$BIN"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) TRIVY_OS=macOS-ARM64; CONFTEST_OS=Darwin_arm64; PLATFORM=DARWIN_ARM64 ;;
  Linux-x86_64) TRIVY_OS=Linux-64bit; CONFTEST_OS=Linux_x86_64; PLATFORM=LINUX_X86_64 ;;
  *) echo "unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

# fetch_release <repo> <tag> <asset> <sha256-from-tools.lock> <binary>
fetch_release() {
  local repo=$1 tag=$2 asset=$3 sha256=$4 binary=$5
  curl -fsSL -o "$WORK/$asset" "https://github.com/$repo/releases/download/$tag/$asset"
  (cd "$WORK" && echo "$sha256  $asset" | shasum -a 256 -c -)
  tar -xzf "$WORK/$asset" -C "$WORK" "$binary"
  mv "$WORK/$binary" "$BIN/$binary"
}

TRIVY_SHA256_VAR="TRIVY_SHA256_$PLATFORM" CONFTEST_SHA256_VAR="CONFTEST_SHA256_$PLATFORM"
fetch_release aquasecurity/trivy "v$TRIVY_VERSION" "trivy_${TRIVY_VERSION}_${TRIVY_OS}.tar.gz" "${!TRIVY_SHA256_VAR}" trivy
fetch_release open-policy-agent/conftest "v$CONFTEST_VERSION" "conftest_${CONFTEST_VERSION}_${CONFTEST_OS}.tar.gz" "${!CONFTEST_SHA256_VAR}" conftest

export UV_TOOL_DIR="$TOOLS/uv" UV_TOOL_BIN_DIR="$BIN"
uv tool install --force --quiet "semgrep==$SEMGREP_VERSION"
uv tool install --force --quiet --python "$CHECKOV_PYTHON" "checkov==$CHECKOV_VERSION"

# check <binary> <expected-version> <version-args...>
check() {
  local binary=$1 expected=$2; shift 2
  if ! "$BIN/$binary" "$@" 2>&1 | grep -Fqw -- "$expected"; then
    echo "version mismatch: $binary is not $expected" >&2; exit 1
  fi
  echo "ok  $binary $expected"
}
check trivy "$TRIVY_VERSION" --version
check conftest "$CONFTEST_VERSION" --version
check semgrep "$SEMGREP_VERSION" --version
check checkov "$CHECKOV_VERSION" --version
