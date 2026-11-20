# Contributing

1. Open an issue for anything beyond a small fix.
2. Run `python3 -B tests/test_cli.py` before pushing; CI runs the same command on `ubuntu-24.04-arm`.
3. Add a test that fails without your change. Keep the tool a single standard-library file.
4. One logical change per pull request; describe what changed, why, and how it was tested.

Security issues: see [SECURITY.md](SECURITY.md), not a public issue.
