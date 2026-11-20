"""End-to-end tests: run the CLI as a subprocess against a stub MCP server on loopback."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CLI = str(Path(__file__).resolve().parent.parent / "mcp-http-call")
TOOLS = [{"name": "echo", "description": "Echo the arguments back. Second sentence.",
          "inputSchema": {"type": "object", "required": ["msg"],
                          "properties": {"msg": {"type": "string", "description": "text"},
                                         "n": {"type": "integer", "description": "count"}}}},
         {"name": "boom", "description": "Always fails.", "inputSchema": {"type": "object"}},
         {"name": "pic", "description": "Text and an image.", "inputSchema": {"type": "object"}}]


class Stub(BaseHTTPRequestHandler):
    seen = []  # (path, Authorization header, rpc method)

    def log_message(self, *a):
        pass

    def do_DELETE(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append((self.path, self.headers.get("Authorization"), body["method"]))
        if "id" not in body:
            self.send_response(202)
            self.end_headers()
            return
        m, p = body["method"], body.get("params", {})
        if m == "initialize":
            res = {"protocolVersion": "2025-06-18", "capabilities": {}}
        elif m == "tools/list":
            res = {"tools": TOOLS}
        elif p["name"] == "echo":
            res = {"content": [{"type": "text", "text": json.dumps({"got": p["arguments"]})}]}
        elif p["name"] == "pic":
            res = {"content": [{"type": "text", "text": "hello"}, {"type": "image", "data": "x", "mimeType": "image/png"}]}
        else:
            res = {"isError": True, "content": [{"type": "text", "text": "kaput"}]}
        msg = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": res})
        if self.path.startswith("/sse"):  # same reply, framed as server-sent events
            out, ctype = ("event: message\ndata: %s\n\n" % msg).encode(), "text/event-stream"
        else:
            out, ctype = msg.encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Mcp-Session-Id", "s1")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Stub)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def run_cli(self, *args, env=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith("MCP_HTTP_CALL_")}
        e.update(env or {})
        return subprocess.run([sys.executable, "-B", CLI, *args], capture_output=True, text=True, env=e)

    def test_list_and_describe(self):
        r = self.run_cli("list", self.base + "/mcp")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("echo  Echo the arguments back.", r.stdout)
        r = self.run_cli("describe", self.base + "/mcp", "echo")
        self.assertIn("msg string [required] - text", r.stdout)
        self.assertIn("n integer - count", r.stdout)

    def test_call_parses_values_and_forced_strings(self):
        r = self.run_cli("call", self.base + "/mcp", "echo", "msg:=007", "n=3", "tags=[1,2]")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"got": {"msg": "007", "n": 3, "tags": [1, 2]}})

    def test_json_flag_merged_and_kv_wins(self):
        r = self.run_cli("call", self.base + "/mcp", "echo", "--json", '{"msg":"a","n":1}', "n=2")
        self.assertEqual(json.loads(r.stdout), {"got": {"msg": "a", "n": 2}})

    def test_sse_reply(self):
        r = self.run_cli("call", self.base + "/sse", "echo", "msg=hi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"got": {"msg": "hi"}})

    def test_tool_error_exits_1(self):
        r = self.run_cli("call", self.base + "/mcp", "boom")
        self.assertEqual(r.returncode, 1)
        self.assertIn("kaput", r.stderr)

    def test_non_text_content_is_announced(self):
        r = self.run_cli("call", self.base + "/mcp", "pic")
        self.assertIn("hello", r.stdout)
        self.assertIn("non-text content dropped: image", r.stdout)

    def test_jq_out_and_max_chars(self):
        if subprocess.run(["which", "jq"], capture_output=True).returncode:
            self.skipTest("jq not installed")
        r = self.run_cli("call", self.base + "/mcp", "echo", "msg=hi", "--jq", ".got.msg")
        self.assertEqual(r.stdout.strip(), "hi")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.json")
            r = self.run_cli("call", self.base + "/mcp", "echo", "msg=hi", "--out", out)
            self.assertIn("saved", r.stdout)
            self.assertEqual(json.loads(Path(out).read_text()), {"got": {"msg": "hi"}})
        r = self.run_cli("call", self.base + "/mcp", "echo", "msg=hello", "--max-chars", "5")
        self.assertEqual(len(r.stdout.strip()), 5)
        self.assertIn("output cut at 5", r.stderr)

    def test_helper_headers_sent_on_every_request(self):
        with tempfile.TemporaryDirectory() as d:
            h = Path(d) / "helper.sh"
            h.write_text('#!/bin/sh\necho "{\\"Authorization\\": \\"Bearer s3cret\\"}"\n')
            h.chmod(h.stat().st_mode | stat.S_IXUSR)
            Stub.seen.clear()
            r = self.run_cli("call", self.base + "/mcp", "echo", "msg=x", env={"MCP_HTTP_CALL_HELPER": str(h)})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(Stub.seen and all(a == "Bearer s3cret" for _, a, _ in Stub.seen), Stub.seen)

    def test_no_helper_means_no_auth_header(self):
        Stub.seen.clear()
        self.run_cli("list", self.base + "/mcp")
        self.assertTrue(Stub.seen and all(a is None for _, a, _ in Stub.seen))

    def test_failing_helper_exits_3(self):
        r = self.run_cli("list", self.base + "/mcp", env={"MCP_HTTP_CALL_HELPER": "false"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("auth helper", r.stderr)

    def test_bare_name_needs_gateway_and_uses_template(self):
        r = self.run_cli("list", "search")
        self.assertEqual(r.returncode, 2)
        self.assertIn("MCP_HTTP_CALL_GATEWAY", r.stderr)
        Stub.seen.clear()
        r = self.run_cli("list", "search", env={"MCP_HTTP_CALL_GATEWAY": self.base + "/{}/mcp"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Stub.seen[0][0], "/search/mcp")

    def test_unreachable_server_exits_3(self):
        r = self.run_cli("list", "http://127.0.0.1:1/mcp")
        self.assertEqual(r.returncode, 3)


if __name__ == "__main__":
    unittest.main()
