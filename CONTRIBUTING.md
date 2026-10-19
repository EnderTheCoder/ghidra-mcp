# Contributing

Thank you for improving Ghidra MCP. Contributions must be based on public official documentation, observable behavior, and original work created for this repository.

By intentionally submitting a pull request, you confirm that you have the right to submit the material and agree to license the contribution under Apache License 2.0, unless the communication is explicitly marked "Not a Contribution."

## Set up the development environment

Requirements are Python 3.11–3.13, `uv`, Zig for generating ELF fixtures, and Ghidra 12.1.3+ for integration tests.

```bash
uv sync --locked --extra dev
uv run --locked pytest -m 'not integration' -q
uv run --locked ruff check src tests scripts
```

Generate the original ELF fixtures before running real Ghidra tests:

```bash
python scripts/build_fixtures.py
GHIDRA_INSTALL_DIR=/absolute/path/to/ghidra \
  _JAVA_OPTIONS=-Duser.home=/tmp/ghidra-mcp-java-home \
  uv run --locked pytest tests/integration/test_real_ghidra.py -q -s
```

The integration tests under `tests/integration/` are the executable reference for real Ghidra and container behavior.

## Change requirements

- Add a failing regression test before fixing a behavior bug, then implement the smallest root-cause fix.
- Keep tools task-oriented and bounded. Do not add synonymous batch/bulk tools or GUI-dependent capabilities.
- When a tool changes, update its schema contract, the [tool catalog](https://github.com/xjoker/ghidra-mcp/wiki/Tool-catalog), and relevant tests.
- Preserve configuration precedence: environment variables > `.env` > TOML > defaults. Update `.env.example` and the public documentation when adding configuration.
- Do not commit binary samples, real analysis projects, credentials, private-network addresses, personal paths, or production deployment details.
- Verify implementation decisions against current public official documentation or the installed Ghidra distribution.

## Run checks before opening a pull request

```bash
uv run --locked pytest -m 'not integration' -q
uv run --locked ruff check src tests scripts
git diff --check
```

Changes affecting Ghidra APIs, persistence, containers, or HTTP boundaries also require the corresponding real integration tests. List the commands actually run and their results in the pull request; explicitly identify checks that were not run.

Do not disclose security vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md) instead.
