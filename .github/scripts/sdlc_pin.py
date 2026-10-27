"""Print the framework pin this project's sdlc.yaml declares, for the workflows to check out.

Installed into the project by ``/sdlc-init`` (build guide step 30, task 30.8) and run as the
second step of every SDLC workflow, *before* the framework itself is checked out — which is
why it lives in the project and imports nothing but the standard library.

    python .github/scripts/sdlc_pin.py [--root .] [--file sdlc.yaml] \
        [--ref refs/remotes/origin/main]

``--ref`` reads the file from that git ref instead of the working tree: the workflows pass
``refs/remotes/origin/<default branch>``, because the pin is the project's, not the
branch's. A phase branch carries the ``sdlc.yaml`` it started from, and a pull request may
stay open across several framework releases: read from the head, the branch would run the
framework it was created under for its whole life (the first overturn rounds on the sample
repository, 2026-09-24, ran 0.2.14 on ``sdlc/0002/b`` while ``main`` pinned 0.2.16). The
run's own configuration (pause flag, limits) already comes from the base branch's copy.

The ref is fully qualified (plugin 0.2.24): git resolves ``refs/tags/<name>`` before
``refs/remotes/<name>``, so with the short ``origin/main`` a tag named ``origin/main``,
pushed by anyone with write access and fetched by ``actions/checkout`` with
``fetch-depth: 0``, would supply its own ``sdlc.yaml`` and pick the framework version (git
only warns "refname is ambiguous"). When a ``refs/remotes/origin/<branch>`` (or
``origin/<branch>``) ref is not in the checkout, ``refs/heads/<branch>`` is fetched from
``origin`` into that remote-tracking ref first (a by-hand run; in a workflow the ref is
always there, because the step's own ``git show`` of this script read it). The workflows run
this script from the default branch's copy, not the head's (``git show
<ref>:.github/scripts/sdlc_pin.py | python -``), for the same reason the pin is read there.

It reads the ``plugin:`` block of ``sdlc.yaml`` and writes two step outputs into
``$GITHUB_OUTPUT`` (and prints them, so a local run shows the same two lines):

    ref=v<plugin.version>            the git ref of the pinned framework release
    claude_code=<plugin.claude_code> the Claude Code CLI version the jobs install

A ``plugin.version`` that already starts with ``v`` is not doubled: ``v1.2.3`` prints
``ref=v1.2.3``. ``plugin.claude_code`` is checked against ``^[0-9A-Za-z.+-]+$`` because the
install step interpolates it into a shell command; anything else stops the workflow.

Exit codes: 0 the pin was read; 1 sdlc.yaml is missing or carries no ``plugin.version``
(the workflow must then stop rather than silently check out the framework's default branch);
2 ``plugin.claude_code`` is not a version string.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_CLAUDE_CODE = "2.1.304"  # the framework's minimum, used when the key is absent
# npm version or dist-tag characters only: the value reaches a shell command in the job
CLAUDE_CODE_RE = re.compile(r"^[0-9A-Za-z.+-]+$")
PLUGIN_BLOCK_RE = re.compile(r"(?m)^plugin:[ \t]*$")
KEY_RE = r"(?m)^[ \t]+{key}:[ \t]*[\"']?([^\"'#\r\n]+)"


def plugin_block(text: str) -> str:
    """The indented body of the top-level ``plugin:`` key, or "" when there is none."""
    match = PLUGIN_BLOCK_RE.search(text)
    if not match:
        return ""
    lines = text[match.end() :].splitlines()
    body: list[str] = []
    for line in lines:
        if line.strip() and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def read_key(block: str, key: str) -> str:
    match = re.search(KEY_RE.format(key=re.escape(key)), block)
    return match.group(1).strip() if match else ""


def _git_show(root: Path, ref: str, file: str) -> str | None:
    argv = ["git", "--no-replace-objects", "show", f"{ref}:{file}"]
    proc = subprocess.run(
        argv, cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )
    return proc.stdout if proc.returncode == 0 else None


REMOTE_PREFIXES = ("refs/remotes/origin/", "origin/")


def tracked_branch(ref: str) -> str | None:
    """The branch a ``refs/remotes/origin/<branch>`` or ``origin/<branch>`` ref tracks."""
    for prefix in REMOTE_PREFIXES:
        if ref.startswith(prefix) and len(ref) > len(prefix):
            return ref[len(prefix) :]
    return None


def read_at_ref(root: Path, ref: str, file: str) -> str | None:
    """``file`` as committed at ``ref``; a remote-tracking ref of ``origin`` that the checkout
    lacks is fetched from ``origin`` into ``refs/remotes/origin/<branch>`` first (no depth
    option: a depth-limited fetch would turn a full checkout shallow). None when nothing can
    be read."""
    if not ref or ref.startswith("-"):
        return None  # never let the value read as a git option
    text = _git_show(root, ref, file)
    branch = tracked_branch(ref)
    if text is not None or branch is None:
        return text
    tracking = f"refs/remotes/origin/{branch}"
    argv = ["git", "fetch", "origin", f"+refs/heads/{branch}:{tracking}"]
    fetched = subprocess.run(
        argv, cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )
    if fetched.returncode != 0:
        return None
    return _git_show(root, tracking, file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdlc-pin", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--file", default="sdlc.yaml")
    parser.add_argument(
        "--ref",
        default=None,
        help="read the file at this git ref (workflows: refs/remotes/origin/<default>)",
    )
    args = parser.parse_args(argv)

    path = Path(args.root) / args.file
    if args.ref:
        text = read_at_ref(Path(args.root), args.ref, args.file)
        if text is None:
            print(
                f"cannot read {args.file} at {args.ref}: fetch the default branch first",
                file=sys.stderr,
            )
            return 1
        path = Path(f"{args.ref}:{args.file}")
    else:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {path}: {exc}", file=sys.stderr)
            return 1
    block = plugin_block(text)
    version = read_key(block, "version")
    if not version:
        print(f"{path} has no plugin.version: run /sdlc-init first", file=sys.stderr)
        return 1
    claude_code = read_key(block, "claude_code") or DEFAULT_CLAUDE_CODE
    if not CLAUDE_CODE_RE.match(claude_code):
        print(
            f"{path}: plugin.claude_code {claude_code!r} is not a version string "
            "(allowed: letters, digits, '.', '+', '-')",
            file=sys.stderr,
        )
        return 2

    lines = [f"ref=v{version.removeprefix('v')}", f"claude_code={claude_code}"]
    for line in lines:
        print(line)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
