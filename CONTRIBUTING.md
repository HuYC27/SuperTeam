# Contributing to SuperTeam / 参与 SuperTeam

Thank you for helping SuperTeam make multi-AI collaboration more useful, traceable and honest.

感谢你帮助 SuperTeam 把多 AI 协作做得更高效、更可追溯，也更诚实。

## Before opening an issue

Search existing issues first. For a connection problem, state the SuperTeam version, Windows version, AI application name and whether the state is **detected**, **opened**, **message verified**, or **tool execution verified**. Do not post account cookies, API keys, private chats, unpublished research data or participant information.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python desktop.py
```

Frontend regression tests use Node's built-in test runner:

```powershell
node --test tests/js/*.test.mjs
```

## Pull requests

Keep a change focused. Add or update tests for behavior changes, preserve the privacy boundary, and describe what was actually verified. A discovered executable is not a validated connector. A successful response in an original AI application is not the same as a successful SuperTeam end-to-end relay.

Run the public export audit before proposing a release:

```powershell
python release/audit_public.py publish/v1.0.0/repository
```

By contributing, you agree that your contribution is licensed under Apache-2.0.

