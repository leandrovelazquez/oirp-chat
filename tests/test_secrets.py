"""
No secrets in the repository.

Scans every file git tracks, plus every untracked file that isn't ignored (so
`git add -A` would pick it up), for strings shaped like API keys, tokens or
private keys. The repo is public: a committed key is a leaked key, even if a
later commit removes it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Each pattern needs a long run of key characters after a known prefix, so the
# patterns below don't match themselves and a placeholder like "sk-ant-..."
# doesn't trip them.
KEY_PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[a-z]+\d{2}-[A-Za-z0-9_\-]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "API key assigned a value": re.compile(
        r"(?i)\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN)\s*[=:]\s*['\"]?(?!\.\.\.|<|your|\$|\{)[A-Za-z0-9_\-]{24,}"
    ),
}


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs a git checkout"
)


def test_no_key_shaped_strings_in_files_git_would_commit():
    files = _git("ls-files", "--cached", "--others", "--exclude-standard")
    found = []
    for rel in files:
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in KEY_PATTERNS.items():
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                found.append(f"{rel}:{line}: {name}")  # never print the match itself
    assert not found, "Key-shaped strings in files git would commit:\n" + "\n".join(found)


def test_env_files_are_ignored():
    for name in (".env", ".env.local"):
        ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name]).returncode == 0
        assert ignored, f"{name} is not gitignored"


def test_patterns_catch_a_real_shaped_key():
    fake = "sk-ant-api03-" + "A1b2C3d4" * 10  # built at runtime, so this file holds no key
    assert KEY_PATTERNS["Anthropic API key"].search(fake)
    assert KEY_PATTERNS["API key assigned a value"].search("ANTHROPIC_API_KEY=" + fake)
    assert not KEY_PATTERNS["API key assigned a value"].search("ANTHROPIC_API_KEY=sk-ant-...")
