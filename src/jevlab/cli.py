"""Thin `jevlab` console entry point — dispatches to the real CLIs."""
from __future__ import annotations

import sys

_COMMANDS = {
    "build-catalog": "jevlab.build_catalog:main",
    "find": "jevlab.find_effects:main",
    "eval": "jevlab.evals.run_eval:main",
}


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        cmds = ", ".join(sorted(_COMMANDS))
        print(f"usage: jevlab <command> [args...]\ncommands: {cmds}")
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd not in _COMMANDS:
        print(f"unknown command {cmd!r}; expected one of: "
              + ", ".join(sorted(_COMMANDS)), file=sys.stderr)
        return 2
    module_name, func_name = _COMMANDS[cmd].rsplit(":", 1)
    import importlib
    func = getattr(importlib.import_module(module_name), func_name)
    sys.argv = [f"jevlab {cmd}", *rest]
    return func()


if __name__ == "__main__":
    raise SystemExit(main())
