# Agent CLI Quick Start Research

Research date: 2026-07-25. Only official repositories and first-party
documentation were used.

## Compared projects

| Project | Official Quick Start | Distribution pattern |
|---|---|---|
| [OpenAI Codex](https://github.com/openai/codex/blob/main/README.md) | Platform installer, npm, Homebrew, then `codex` | Hosted installer plus a stable executable |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npx @google/gemini-cli` or global npm install, then `gemini` | Registry-backed one-shot run and permanent install |
| [OpenCode](https://github.com/anomalyco/opencode/blob/dev/README.md) | Hosted shell installer or package manager, then `opencode` | OS-aware bootstrap, version selection, PATH management |
| [Aider](https://github.com/Aider-AI/aider/blob/main/README.md) | uv/pipx installer, then `aider` | Isolated Python tool environment and console script |
| [Goose](https://github.com/aaif-goose/goose) | GitHub Release installer, then `goose session` | Versioned release assets and stable command |

The relevant Python mechanism is also documented by
[uv's tool guide](https://docs.astral.sh/uv/guides/tools/): `uvx --from` runs
a command from another package source in an isolated environment, while
`uv tool install <package-source>` permanently installs the executables that
the package exposes.

## RxyCode decision

RxyCode follows the Aider-style Python distribution model:

1. `pyproject.toml` builds a standard wheel and source distribution.
2. `[project.scripts]` exposes a stable lowercase `rxycode` command.
3. `uvx --from git+... rxycode` supports an isolated one-shot run.
4. `uv tool install --force git+...` supports repeatable install and upgrade.
5. `install.ps1` and `install.sh` bootstrap uv when needed and install the
   pinned `v1.1.0` source without a manual clone.
6. Fresh-install tests build the wheel, install it away from the checkout,
   clear `PYTHONPATH`, and execute the real console and module launchers.

The installed command uses the Ink frontend exclusively. The Python wheel and
source distribution contain a self-contained JavaScript bundle, while Node.js
20 or newer remains an explicit host runtime prerequisite. Docker images copy
the Node.js runtime into the final image.

## Release boundary

The local package and clean-environment installation can be verified before a
release. The public Git URL and raw installer commands cannot succeed until the
new tree is pushed to `xin-yi33/RxyCode` and the `v1.1.0` tag exists. The tag
release workflow enforces the build and installed-entrypoint checks before it
uploads artifacts.
