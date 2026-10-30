from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MAX_REPOSITORY_FILE = 50 * 1024 * 1024
EXCLUDED_PARTS = {
    "data",
    "uploads",
    "work",
    "dist",
    "releases",
    ".playwright-cli",
    "__pycache__",
}
EXCLUDED_NAMES = {
    "avatar.png",
    "runtime.json",
    "api-connections.json",
    "connections.json",
    "superteam.db",
}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".iss",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}
CREDENTIAL_PATTERNS = (
    re.compile(r"\bark-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+(?!\$|<|\{|YOUR_)[A-Za-z0-9._-]{16,}"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*['\"](?!\$|<|YOUR_)[^'\"]{12,}['\"]"),
)
ABSOLUTE_USER_PATH = re.compile(r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s:'\"]+")


def _issue(code: str, path: Path, detail: str) -> dict[str, str]:
    return {"code": code, "path": path.as_posix(), "detail": detail}


def audit_tree(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    issues: list[dict[str, str]] = []
    files = 0
    total_bytes = 0
    if not base.is_dir():
        return {
            "ok": False,
            "root": str(base),
            "files": 0,
            "bytes": 0,
            "issues": [_issue("missing-root", base, "directory does not exist")],
        }

    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base)
        lower_parts = {part.lower() for part in relative.parts}
        if path.is_dir():
            if lower_parts & EXCLUDED_PARTS:
                issues.append(_issue("excluded-path", relative, "runtime/build directory is public"))
            continue
        files += 1
        size = path.stat().st_size
        total_bytes += size
        lower_name = path.name.lower()
        if lower_parts & EXCLUDED_PARTS or lower_name in EXCLUDED_NAMES:
            issues.append(_issue("excluded-path", relative, "runtime or personal file is public"))
        if lower_name.startswith("installed-app-"):
            issues.append(_issue("generated-app-icon", relative, "machine-derived icon is public"))
        if size > MAX_REPOSITORY_FILE:
            issues.append(_issue("large-file", relative, f"{size} bytes exceeds 50 MiB"))
        if path.suffix.lower() not in TEXT_SUFFIXES or size > 4 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ABSOLUTE_USER_PATH.search(text):
            issues.append(_issue("absolute-user-path", relative, "contains a Windows user profile path"))
        if any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS):
            issues.append(_issue("credential-pattern", relative, "contains a credential-like value"))

    unique = []
    seen = set()
    for item in issues:
        key = (item["code"], item["path"], item["detail"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return {
        "ok": not unique,
        "root": str(base),
        "files": files,
        "bytes": total_bytes,
        "issues": unique,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a SuperTeam public source export")
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args()
    report = audit_tree(args.root)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(output + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
