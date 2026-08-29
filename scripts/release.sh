#!/usr/bin/env bash
#
# Tag a release.
#
#   scripts/release.sh 2.4.0            # check everything, create the tag locally
#   scripts/release.sh 2.4.0 --push     # ... and push it to origin
#   scripts/release.sh 2.4.0 --quick    # skip the browser suite (see below)
#   scripts/release.sh 2.4.0 --dry-run  # run every gate, create no tag
#   scripts/release.sh 2.4.0 -m "..."   # custom annotation message
#
# Why this exists rather than a bare `git tag`:
#
#   * Consumers pin this fork by tag, so a tag whose commit carries a
#     different version in pyproject.toml is a pin that lies. Nothing else in
#     the repo checks tag-against-version — `test_component_manifest.py` only
#     checks the two pyproject.toml files against each other.
#
#   * `st_aggrid/frontend/build/` is committed on purpose: installs come
#     straight from git and nothing builds the frontend at install time. So a
#     tag freezes a built bundle. Tagging a commit whose TypeScript changed
#     without a rebuild ships a stale bundle to every consumer, silently and
#     permanently. The rebuild-and-diff check below is the only cheap way to
#     catch that.
#
#   * A published tag must never move: pip and uv cache by URL+ref, so a
#     force-moved tag hands different code to different machines with no
#     signal at all. Pushing is therefore opt-in, and re-tagging an existing
#     version is refused outright — ship the next patch instead.

set -euo pipefail

readonly RELEASE_BRANCH="main"
readonly BUILD_DIR="st_aggrid/frontend/build"
readonly FRONTEND_DIR="st_aggrid/frontend"

die() { printf '\n\033[31mrelease: %s\033[0m\n' "$*" >&2; exit 1; }
warn() { printf '    \033[33mwarn\033[0m %s\n' "$*"; }

# Under --dry-run the checks about *where you are* — the branch, its remote,
# whether the tag is taken — soften to warnings, so the gates can be exercised
# from a feature branch before this script is itself merged. The checks about
# *what you would ship* — the declared versions, the lockfile, the bundle, the
# typecheck, the tests — stay fatal, because those are the point of a dry run.
place_gate() { if [ "$DRY_RUN" -eq 1 ]; then warn "$*"; else die "$*"; fi; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok() { printf '    \033[32mok\033[0m  %s\n' "$*"; }

usage() {
    sed -n '3,9p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

VERSION=""
MESSAGE=""
PUSH=0
QUICK=0
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --push)  PUSH=1; shift ;;
        --quick) QUICK=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -m)      MESSAGE="${2:-}"; [ -n "$MESSAGE" ] || die "-m needs a message"; shift 2 ;;
        -h|--help) usage 0 ;;
        -*)      die "unknown flag: $1" ;;
        *)       [ -z "$VERSION" ] || die "give exactly one version"; VERSION="$1"; shift ;;
    esac
done

[ -n "$VERSION" ] || usage 1
[ "$DRY_RUN" -eq 1 ] && [ "$PUSH" -eq 1 ] && die "--dry-run and --push contradict each other"


# Accept `2.4.0` or `v2.4.0`; the tag carries the `v`, pyproject.toml does not.
VERSION="${VERSION#v}"
readonly VERSION
readonly TAG="v${VERSION}"

case "$VERSION" in
    [0-9]*.[0-9]*.[0-9]*) ;;
    *) die "'$VERSION' does not look like a version (expected e.g. 2.4.0)" ;;
esac

cd "$(git rev-parse --show-toplevel)"

# ---------------------------------------------------------------------------
# 1. The tag must not already exist
# ---------------------------------------------------------------------------

step "Tag $TAG is unused"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    place_gate "$TAG already exists locally. A published tag must never move — ship the next patch version instead."
fi
if git ls-remote --exit-code --tags origin "$TAG" >/dev/null 2>&1; then
    place_gate "$TAG already exists on origin. A published tag must never move — ship the next patch version instead."
fi
ok "$TAG is free"

# ---------------------------------------------------------------------------
# 2. We are on an up-to-date, clean release branch
# ---------------------------------------------------------------------------

step "Working tree is $RELEASE_BRANCH, clean and current"

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "$RELEASE_BRANCH" ] || place_gate "on '$branch'; releases are tagged from '$RELEASE_BRANCH'"

[ -z "$(git status --porcelain)" ] || die "working tree is dirty; commit or stash first"

git fetch --quiet origin "$RELEASE_BRANCH" 2>/dev/null || place_gate "could not fetch origin/$RELEASE_BRANCH"
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "origin/$RELEASE_BRANCH")"
if [ "$local_head" != "$remote_head" ]; then
    place_gate "HEAD ($(git rev-parse --short HEAD)) differs from origin/$RELEASE_BRANCH ($(git rev-parse --short "origin/$RELEASE_BRANCH")); pull or push first"
fi
ok "$RELEASE_BRANCH at $(git rev-parse --short HEAD), in sync with origin"

# ---------------------------------------------------------------------------
# 3. Both pyproject.toml files declare exactly the version being tagged
# ---------------------------------------------------------------------------

step "Declared version matches $TAG"

read_version() {
    grep -m1 '^version[[:space:]]*=' "$1" | sed 's/.*=[[:space:]]*"\(.*\)".*/\1/'
}

root_version="$(read_version pyproject.toml)"
inner_version="$(read_version st_aggrid/pyproject.toml)"

[ "$root_version" = "$VERSION" ] \
    || die "pyproject.toml says '$root_version', tag says '$VERSION'"
[ "$inner_version" = "$VERSION" ] \
    || die "st_aggrid/pyproject.toml says '$inner_version', tag says '$VERSION'"
ok "pyproject.toml and st_aggrid/pyproject.toml both say $VERSION"

# uv.lock pins the editable `st-aggrid` at its own version, so a bump that
# updates the two pyproject.toml files and stops there leaves a lockfile that
# disagrees with them — and every `uv run` silently rewrites it, so it shows up
# as phantom churn rather than as an error. This exact miss shipped in 2.4.0's
# bump and was caught by hand.
uv lock --check >/dev/null 2>&1 \
    || die "uv.lock is out of date with pyproject.toml. Run 'uv lock' and commit the result."
ok "uv.lock agrees with pyproject.toml"

# ---------------------------------------------------------------------------
# 4. The committed bundle is the one this source produces
# ---------------------------------------------------------------------------
#
# The build script wipes `build/` and re-emits content-hashed filenames, so an
# unchanged source tree reproduces byte-identical names and git sees nothing.
# Any output at all here means the committed bundle does not match the source.

step "Committed frontend bundle is current"

(
    cd "$FRONTEND_DIR"
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build >/dev/null
) || die "frontend build failed"

if [ -n "$(git status --porcelain -- "$BUILD_DIR")" ]; then
    printf '\n%s\n' "$(git status --short -- "$BUILD_DIR")"
    # `build/` is entirely generated, so restoring it leaves the tree exactly
    # as this script found it.
    git checkout --quiet -- "$BUILD_DIR" 2>/dev/null || true
    git clean --quiet -fd -- "$BUILD_DIR"
    die "rebuilding changed $BUILD_DIR — the committed bundle is stale.
     Run 'cd $FRONTEND_DIR && corepack yarn build', commit the result
     (a rebuild is a delete plus an add, not a modify), then release again."
fi

js_count="$(find "$BUILD_DIR" -maxdepth 1 -name 'index-*.js' | wc -l)"
css_count="$(find "$BUILD_DIR" -maxdepth 1 -name 'index-*.css' | wc -l)"
[ "$js_count" -eq 1 ] && [ "$css_count" -eq 1 ] \
    || die "st_aggrid/component.py globs each expect exactly one file; found $js_count js and $css_count css"
ok "bundle reproduces byte-for-byte; one js, one css"

# ---------------------------------------------------------------------------
# 5. Typecheck, pure-module checks, tests
# ---------------------------------------------------------------------------

step "Typecheck"
(
    cd "$FRONTEND_DIR"
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn tsc --noEmit
) || die "tsc reported errors"
ok "tsc clean"

# The pure colour-scale modules run directly under node (v22 strips types), so
# they have a test cycle with no JS test runner. Absent on older tags.
checks=("$FRONTEND_DIR"/src/colorScales/__checks__/*.check.ts)
if [ -e "${checks[0]}" ]; then
    step "Pure-module checks"
    for check in "${checks[@]}"; do
        node "$check" || die "$(basename "$check") failed"
    done
    ok "${#checks[@]} check script(s) passed"
fi

step "Tests"
if [ "$QUICK" -eq 1 ]; then
    printf '    \033[33mskipping the browser suite (--quick)\033[0m\n'
    uv run pytest -m "not e2e" -q || die "unit tests failed"
else
    # Bare `pytest` runs everything except the slow 1M-row performance suite.
    uv run pytest -q || die "tests failed"
fi
ok "tests passed"

# ---------------------------------------------------------------------------
# 6. Tag
# ---------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
    step "Dry run — no tag created"
    printf '\nEvery gate that judges what would ship has passed for %s.\n' "$VERSION"
    printf 'Re-run on %s without --dry-run to create the tag.\n\n' "$RELEASE_BRANCH"
    exit 0
fi

step "Creating annotated tag $TAG"

[ -n "$MESSAGE" ] || MESSAGE="st-aggrid $VERSION"
git tag -a "$TAG" -m "$MESSAGE"
ok "$TAG -> $(git rev-parse --short HEAD)"

if [ "$PUSH" -eq 1 ]; then
    step "Pushing $TAG to origin"
    git push origin "$TAG"
    ok "pushed"
    printf '\nPin it with:\n  st-aggrid @ git+https://github.com/af-ryb/streamlit-aggrid@%s\n\n' "$TAG"
else
    printf '\nTag created locally, not pushed. When you are ready:\n\n  git push origin %s\n\nPin it with:\n  st-aggrid @ git+https://github.com/af-ryb/streamlit-aggrid@%s\n\n' "$TAG" "$TAG"
fi
