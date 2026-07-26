# main.py - CLI Entry Point

## What Is This Module?
The main entry point for RxyCode. It handles CLI argument parsing, launches the Ink frontend, and starts the API server.

## Entry Points
- `rxycode`: Launch the Ink frontend with an embedded authenticated API server
- `python -m RxyCode`: Launch the same Ink frontend
- `python -m RxyCode.RxyCode1_1_0`: Versioned module entry point
- `rxycode --version`: Report the package version without initializing runtime state
- `rxycode --api`: Start the API server only
- `rxycode config`: Manage model configuration

The console script is declared in `pyproject.toml` and implemented by `entrypoint.py`. `_package_root/RxyCode/` provides the stable module bridge while the existing `RxyCode.RxyCode1_1_0.*` import contract remains intact.

## Core: cli()
Click options:
- `--model`, `-m`: Model name to use
- `--api`: Start the API server only
- `--api-port`: API server port, default `8765`
- `--version`: Print the package version and exit
- `--log-level`: Configure runtime logging
- `--print-logs`: Mirror logs to stderr

## Core: _launch_ink_tui(model, port)
Launch sequence:
1. Resolve and validate `frontend/package.json` and `frontend/dist/index.js`.
2. Require a `node` executable on `PATH`.
3. Select an available localhost port.
4. Start the authenticated API server in a daemon thread.
5. Poll `/status` with the generated bearer token until the API is ready.
6. Launch `node frontend/dist/index.js` with the API URL and token in its environment.
7. Shut down the embedded API server when the frontend exits.

RxyCode has one interactive frontend: Ink. Missing runtime assets, Node.js, API startup failures, and frontend process failures return explicit CLI errors. They do not fall back to another interface.
