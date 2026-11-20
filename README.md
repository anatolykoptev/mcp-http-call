# mcp-http-call

Call a tool on an HTTP MCP server from the shell: `list`, `describe`, `call`. One Python 3 file, standard
library only (`jq` optional, for `--jq`). It speaks MCP streamable HTTP (initialize, tools/list, tools/call;
JSON or SSE replies).

## Why

An agent that loads an MCP server pays for every tool schema in its context window, on every turn, whether it
calls the tool or not. A CLI moves that cost to the moment of use: the agent runs `list` once, `describe` for
the one tool it needs, and `call` for the result, and a skill or a README line is enough to teach it the
pattern. `--jq` and `--out` keep large results out of the context as well.

## Install

No dependencies beyond Python 3.8+ (tested on 3.12). Copy or symlink the file:

```
ln -s "$PWD/mcp-http-call" ~/.local/bin/mcp-http-call
```

## Usage

```
mcp-http-call list SERVER
mcp-http-call describe SERVER TOOL
mcp-http-call call SERVER TOOL [k=v ...] [--json '{...}'] [--jq FILTER] [--out FILE] [--max-chars N]
```

`SERVER` is a full `http(s)` URL. A bare name (`search`) works only when `MCP_HTTP_CALL_GATEWAY` holds a URL
template with one `{}`, for example `https://gateway.example.com/{}/mcp`.

```
$ mcp-http-call call https://example.com/mcp web_search query="streamable http" limit=3 --jq '.results[].url'
```

- `k=v`: the value is JSON when it parses (`limit=10`, `flag=true`, `ids=[1,2]`), else a string; `k:=text`
  forces a string (`code:=007`). `--json` merges a whole object; `k=v` wins.
- Output is the text content of the result, JSON re-emitted compact. `--jq` pipes it through `jq -cr`.
  `--out FILE` writes the full output and prints one line with its size and top-level shape. Without `--out`,
  output beyond `--max-chars` (20000) is cut and the cut is announced on stderr.
- Exit 0 ok, 1 the tool returned `isError` (message on stderr), 2 usage, 3 transport or auth failure.

## Auth

None by default. Set `MCP_HTTP_CALL_HELPER` to a command (a path, optionally with arguments); it is run as
`COMMAND URL` on every invocation and must print a JSON object of HTTP headers, for example
`{"Authorization": "Bearer ..."}`. This is the same contract as Claude Code's `headersHelper`, so a helper
that reads a secret store works unchanged. The headers live in the process's memory only: never in argv, never
in the environment of the call, never in a file. A helper that fails or prints something else exits 3.

## What it can and cannot be trusted for

- It returns what the server returns; only whitespace and the `--jq` / `--max-chars` cut change the text.
- Text content only: image, audio and resource parts are dropped with a one-line note, so it is the wrong tool
  for servers that return pictures.
- Each call is initialize, one request, session close. Stateful servers (an opened file, a browser session)
  lose their state between calls; use it for stateless request/response tools.
- No OAuth flow, no stdio servers, no server-initiated requests (sampling, elicitation), no progress stream.
- Related projects: [mcporter](https://github.com/openclaw/mcporter) and
  [lydakis/mcpx](https://github.com/lydakis/mcpx) cover more ground (stdio, OAuth, config files). This one
  is a single dependency-free file whose only job is the header-helper auth path above.

## Tests

`python3 -B tests/test_cli.py` starts a stub MCP server on loopback and runs the CLI against it: list,
describe, argument parsing, JSON and SSE replies, `isError`, dropped non-text content, `--jq` / `--out` /
`--max-chars` (the `--jq` test is skipped when `jq` is not installed), helper headers, gateway template,
unreachable server.

## License

Apache-2.0, see [LICENSE](LICENSE).
