"""Run this project's agent eval suite (build guide step 35; article p.30-31, the
``evals/check.sh`` of the p.30 workflow, in Python so it runs on Windows too).

    python evals/check.py [--framework <dir>] [run.py options...]

Written by /sdlc-init; the project owns it. It finds the SDLC framework checkout and runs its
runner against this project:

    python <framework>/plugin/evals/run.py --root <project> --plugin-dir <framework> ...

The framework is, in order: ``--framework <dir>``, ``$SDLC_FRAMEWORK_DIR``, or ``framework/``
beside ``evals/`` (where the CI workflows check it out) when it holds
``plugin/evals/run.py``. Every other option goes to the runner unchanged (``--case``,
``--report``, ``--min-pass-rate``, ``--dry-run``, ``--keep``, ``--claude``). The exit code is
the runner's: 0 the pass rate is at or above the minimum, 1 below, 2 usage. No third-party
import.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

RUNNER = ("plugin", "evals", "run.py")
ENV_VAR = "SDLC_FRAMEWORK_DIR"


def _runner(framework: Path) -> Path:
    return framework.joinpath(*RUNNER)


def split_args(argv: list[str]) -> tuple[str | None, list[str]]:
    """(the ``--framework`` value, the rest in order)."""
    framework, rest, i = None, [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--framework" and i + 1 < len(argv):
            framework, i = argv[i + 1], i + 2
            continue
        if arg.startswith("--framework="):
            framework = arg.split("=", 1)[1]
        else:
            rest.append(arg)
        i += 1
    return framework, rest


def locate(framework: str | None, env: Mapping[str, str], project: Path) -> Path | None:
    """The framework root, or None. An explicit choice (the option or the variable) must hold
    the runner; it is never silently replaced by the next candidate."""
    if framework:
        candidate = Path(framework).resolve()
        return candidate if _runner(candidate).is_file() else None
    if env.get(ENV_VAR):
        candidate = Path(env[ENV_VAR]).resolve()
        return candidate if _runner(candidate).is_file() else None
    candidate = (project / "framework").resolve()
    return candidate if _runner(candidate).is_file() else None


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    project = Path(__file__).resolve().parent.parent
    framework_arg, rest = split_args(argv)
    framework = locate(framework_arg, env, project)
    if framework is None:
        print(
            "evals/check.py: the SDLC framework was not found: pass --framework <dir>, set "
            f"{ENV_VAR}, or check it out into {project / 'framework'}",
            file=sys.stderr,
        )
        return 2
    command = [
        sys.executable,
        str(_runner(framework)),
        "--root",
        str(project),
        "--plugin-dir",
        str(framework),
        *rest,
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())
