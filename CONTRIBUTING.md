# Contributing to RxyCode

Thanks for your interest in contributing! This project is developed with a
strict "development plan first" workflow, so please read the contributing
guidelines before opening a PR.

## How to contribute

- **Report bugs / request features** — open a [GitHub issue](https://github.com/xin-yi33/RxyCode/issues).
- **Ask questions** — use the [Discussions](https://github.com/xin-yi33/RxyCode/discussions) tab (if enabled) or open an issue.
- **Submit a pull request** — see the checklist below.

## Development setup

```bash
git clone https://github.com/xin-yi33/RxyCode.git
cd RxyCode
python -m pip install -e .
# frontend (OpenTUI)
cd frontend && npm install && npm run build
cd ../frontend/opentui-app && bun install
```

## Before opening a PR

1. **Lint**: `python -m ruff check .`
2. **Tests**: `python -m pytest tests -q --timeout=600`
3. **Frontend tests**: `cd frontend && npm test`, `cd frontend/opentui-app && bun test`
4. **Evals**: if your change affects model/provider behavior, run
   `python -m evals.cli run --backend agent --compare-baseline evals/baselines/latest-agent.json`
   and confirm no regression.

## Commit conventions

- Follow the existing commit style (e.g. `feat(model): ...`, `fix(agent): ...`).
- One logical change per commit.
- Do not commit secrets or API keys (`.env` is gitignored — keep it that way).
