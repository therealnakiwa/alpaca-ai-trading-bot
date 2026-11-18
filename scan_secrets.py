"""Scan the project for API keys before you push to GitHub. Exit code 1 if anything is found.

Usage:  python scan_secrets.py            scan every file git would upload
Install as a git pre-commit hook (blocks commits that contain keys):
        python scan_secrets.py --install-hook
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = [
    ("Alpaca API key ID", re.compile(r"\b(PK|AK|CK)[A-Z0-9]{16,}\b")),
    ("Secret assigned in code", re.compile(r"(?i)(secret|api_?key|token|password)\w*\s*[=:]\s*['\"]?([A-Za-z0-9/+_\-]{24,})")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
PLACEHOLDERS = ("your_paper", "your_", "example", "xxxx", "<", "placeholder")
ALLOW_PRAGMA = "scan: allow"      # put this in a comment on a line holding a deliberately FAKE key (tests)
SKIP_DIRS = {".git", "venv", "data", "logs", "__pycache__", ".pytest_cache"}


def files_to_scan():
    try:   # prefer exactly what git would commit (tracked + new, minus .gitignore)
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=HERE,
                             capture_output=True, text=True, check=True).stdout.split()
        return [os.path.join(HERE, f) for f in out]
    except Exception:
        found = []
        for root, dirs, files in os.walk(HERE):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            found += [os.path.join(root, f) for f in files if f != ".env"]
        return found


def scan(paths):
    hits = []
    for path in paths:
        name = os.path.basename(path)
        if name == ".env":
            hits.append((path, 0, ".env file would be uploaded (it must stay in .gitignore)"))
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for n, line in enumerate(f, 1):
                    for label, rx in RULES:
                        m = rx.search(line)
                        if (m and ALLOW_PRAGMA not in line and "re.compile" not in line
                                and not any(p in line.lower() for p in PLACEHOLDERS)):
                            hits.append((path, n, label))
        except (IsADirectoryError, PermissionError):
            continue
    return hits


def install_hook():
    hook = os.path.join(HERE, ".git", "hooks", "pre-commit")
    if not os.path.isdir(os.path.dirname(hook)):
        raise SystemExit("Not a git repository yet (run `git init` first).")
    with open(hook, "w", newline="\n") as f:
        f.write("#!/bin/sh\npython scan_secrets.py || { echo 'Commit blocked: possible secret found.'; exit 1; }\n")
    os.chmod(hook, 0o755)
    print("Pre-commit hook installed: commits containing keys will be blocked.")


if __name__ == "__main__":
    if "--install-hook" in sys.argv:
        install_hook()
        sys.exit(0)
    hits = scan(files_to_scan())
    if not hits:
        print("No secrets found. Safe to push.")
        sys.exit(0)
    print("POSSIBLE SECRETS FOUND. Do not push:")
    for path, n, label in hits:
        print(f"  {os.path.relpath(path, HERE)}:{n}  {label}")
    sys.exit(1)
