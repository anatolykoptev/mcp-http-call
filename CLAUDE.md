# CLAUDE.md

Single-file CLI: `mcp-http-call` (Python 3, standard library only). Tests: `python3 -B tests/test_cli.py`.

- Keep it one file with no third-party imports; `jq` is the only optional external tool.
- Config comes from `MCP_HTTP_CALL_HELPER` and `MCP_HTTP_CALL_GATEWAY` only. A secret never goes to argv, the call's environment or a file.
- Exit codes are part of the interface (0 ok, 1 tool error, 2 usage, 3 transport or auth); a change to them needs a README and CHANGELOG line.
- A behaviour change gets a test in `tests/test_cli.py` that fails without it.
- Index of documents: [docs/INDEX.md](docs/INDEX.md).
