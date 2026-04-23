#!/usr/bin/env python3
"""Proactive style-cleanup bot: propose and open a PR of comment/whitespace
fixes against a target module in a sandbox repository.

Usage:
    BEDROCK_ENDPOINT_URL=... BEDROCK_BEARER_TOKEN=... \
        python scripts/cleanup_module.py \
            --repo scouten-adobe/TEMP-c2pa-rs \
            --path sdk/src/parser \
            [--dry-run] [--max-files 20] [--workdir /tmp/style-bot]

This is Phase 3 (MVP): manually initiated. No rotation, no scheduling.
Reuses pieces of review_pr.py (Bedrock call, style-guide loading, skip lists,
.botignore, JSON array extraction).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

# Reuse the helpers already proven in review_pr.py.
from review_pr import (  # type: ignore
    GENERATED_MARKERS,
    SKIP_EXTENSIONS,
    SKIP_FILENAMES,
    _bedrock_completion,
    _extract_json_array,
    get_style_guide,
    load_botignore,
    matches_botignore,
    should_skip_file,
)

MAX_PROMPT_CHARS = 180_000  # rough Bedrock-safe ceiling for the prompt body
MAX_EDITS = 40
SUPPORTED_EXTENSIONS = {".rs"}  # Rust only for MVP
COMMENT_LINE_RE = re.compile(r"//.*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Shell helpers
# --------------------------------------------------------------------------- #


def run(cmd: list[str], *, cwd: str | None = None, check: bool = True,
        capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess, echoing the command for traceability."""
    printable = " ".join(cmd)
    print(f"$ {printable}" + (f"   (cwd={cwd})" if cwd else ""))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if capture and result.stdout:
        # Trim very long stdout so logs stay readable.
        out = result.stdout if len(result.stdout) < 4000 else result.stdout[:4000] + "\n[...truncated...]"
        print(out)
    if capture and result.stderr:
        err = result.stderr if len(result.stderr) < 4000 else result.stderr[:4000] + "\n[...truncated...]"
        print(err, file=sys.stderr)
    if check and result.returncode != 0:
        raise SystemExit(f"Command failed ({result.returncode}): {printable}")
    return result


# --------------------------------------------------------------------------- #
# Repo setup
# --------------------------------------------------------------------------- #


def clone_repo(repo: str, workdir: Path) -> Path:
    """Clone the target repo into workdir/<name>. Uses gh for auth."""
    name = repo.split("/")[-1]
    dest = workdir / name
    if dest.exists():
        print(f"Reusing existing clone at {dest}")
        run(["git", "fetch", "origin", "main"], cwd=str(dest))
        run(["git", "checkout", "main"], cwd=str(dest))
        run(["git", "reset", "--hard", "origin/main"], cwd=str(dest))
        return dest
    run(["gh", "repo", "clone", repo, str(dest), "--", "--depth=1"])
    return dest


# --------------------------------------------------------------------------- #
# File enumeration
# --------------------------------------------------------------------------- #


def enumerate_files(repo_root: Path, subpath: str,
                    botignore: list[str], max_files: int) -> list[Path]:
    """Return the list of files to send to Claude."""
    base = repo_root / subpath
    if not base.exists():
        raise SystemExit(f"Path does not exist in repo: {subpath}")

    if base.is_file():
        walk_iter: list[Path] = [base]
    else:
        walk_iter = sorted(base.rglob("*"))

    candidates: list[Path] = []
    for f in walk_iter:
        if not f.is_file():
            continue
        if f.suffix not in SUPPORTED_EXTENSIONS:
            continue
        rel = str(f.relative_to(repo_root))
        if should_skip_file(rel):
            continue
        if matches_botignore(rel, botignore):
            continue
        # Skip generated files by looking at the first ~40 lines.
        try:
            head = "".join(f.open().readlines()[:40])
        except (UnicodeDecodeError, OSError):
            continue
        if any(marker in head for marker in GENERATED_MARKERS):
            continue
        candidates.append(f)

    if len(candidates) > max_files:
        print(f"Truncating candidate list from {len(candidates)} to {max_files} files.")
        candidates = candidates[:max_files]
    return candidates


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #


def build_file_sections(repo_root: Path, files: list[Path]) -> str:
    sections: list[str] = []
    for f in files:
        rel = str(f.relative_to(repo_root))
        try:
            content = f.read_text()
        except UnicodeDecodeError:
            continue
        numbered = "\n".join(
            f"{n:5d}: {ln}" for n, ln in enumerate(content.splitlines(), start=1)
        )
        sections.append(
            f"### File: {rel}\n\n```\n{numbered}\n```"
        )
    return "\n\n".join(sections)


def build_prompt(style_guide: str, file_sections: str, subpath: str) -> str:
    return f"""You are an automated style-cleanup assistant. Propose
**comment-only and whitespace-only** edits that bring the files below into
conformance with the style guide. You must NOT alter program logic, rename
identifiers, change control flow, or modify any non-comment tokens.

## Style guide

{style_guide}

---

## Files from `{subpath}`

Each file is shown with line numbers. The full file content is in scope for
proposing edits.

{file_sections}

---

## Instructions

1. Propose a JSON array of edits. Each edit applies a single **block
   replacement** in a single file. Return at most {MAX_EDITS} edits total;
   prefer quality over quantity.

2. Each edit object MUST have:
   - `path` (string): repo-relative path as shown in the `### File:` header.
   - `original_block` (string): the **exact, verbatim** current text to
     replace. It must appear **exactly once** in the file (character-for-
     character, including indentation and newlines). Include enough
     surrounding context (typically 1–3 lines) to make it unique.
   - `new_block` (string): the replacement text. It must differ from
     `original_block` ONLY in comments and/or whitespace. Do not change
     any code tokens, string literals, or control flow.
   - `rule` (string): which style-guide rule this fixes (e.g. "Rule 2").
   - `rationale` (string): one sentence explaining what changed and why.

3. **Allowed changes:**
   - Rewording or capitalizing comment text.
   - Adding a trailing period to a comment.
   - Fixing sentence case or acronym casing in comments / doc comments.
   - Adding or removing blank lines (Rule 4).
   - Moving a trailing end-of-line comment that describes behavior onto its
     own line above the statement (Rule 9). This is still a comment-and-
     whitespace change — the code statement itself stays byte-identical.

4. **Forbidden changes:**
   - Any change to code tokens, identifiers, literals, or operators.
   - Adding or removing imports, functions, or tests.
   - Changing function bodies beyond comment/whitespace.
   - Modifying anything inside a string literal or raw-string block.

5. If you are uncertain whether a change is logic-preserving, SKIP IT. A
   smaller, confidently-safe PR is better than a larger risky one.

6. Return ONLY the JSON array — no prose, no code fences. Start with `[`
   and end with `]`. Return `[]` if you find nothing safe to change.
"""


def call_claude_for_edits(style_guide: str, file_sections: str, subpath: str) -> list[dict]:
    prompt = build_prompt(style_guide, file_sections, subpath)
    print(f"Prompt size: {len(prompt):,} chars")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise SystemExit(
            f"Prompt too large ({len(prompt):,} > {MAX_PROMPT_CHARS:,}); "
            "reduce --max-files or pick a smaller path."
        )
    raw = _bedrock_completion(prompt, max_tokens=8192)
    print(f"Raw response ({len(raw)} chars).")
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    extracted = _extract_json_array(text)
    if extracted is None:
        print("Warning: no JSON array in Claude response; treating as no edits.")
        return []
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        print(f"Warning: JSON array failed to parse ({e}); treating as no edits.")
        return []


# --------------------------------------------------------------------------- #
# Edit application + guardrails
# --------------------------------------------------------------------------- #


def _strip_comments_and_whitespace(text: str) -> str:
    """Return the non-comment, whitespace-normalized form of `text`.

    Used as a sanity check that an edit only touches comments/whitespace.
    This is a heuristic (does not understand string literals), so `cargo
    check` remains the authoritative backstop.
    """
    no_comments = COMMENT_LINE_RE.sub("", text)
    return re.sub(r"\s+", " ", no_comments).strip()


def validate_edit(edit: dict, repo_root: Path) -> tuple[bool, str]:
    """Return (ok, reason). Does not mutate anything."""
    for key in ("path", "original_block", "new_block"):
        if not isinstance(edit.get(key), str):
            return False, f"missing or non-string field: {key}"

    path = edit["path"]
    target = repo_root / path
    if not target.exists():
        return False, f"file not in repo: {path}"

    content = target.read_text()
    original = edit["original_block"]
    if content.count(original) != 1:
        return False, f"original_block not uniquely present in {path} (found {content.count(original)} times)"

    new = edit["new_block"]
    if new == original:
        return False, "no-op edit (new_block == original_block)"

    if _strip_comments_and_whitespace(new) != _strip_comments_and_whitespace(original):
        return False, "edit touches non-comment / non-whitespace content"

    return True, ""


def apply_edits(edits: list[dict], repo_root: Path) -> list[dict]:
    """Apply validated edits in order. Returns the list of edits actually applied."""
    applied: list[dict] = []
    for i, edit in enumerate(edits):
        ok, reason = validate_edit(edit, repo_root)
        if not ok:
            print(f"[{i}] DROP {edit.get('path')!r}: {reason}")
            continue
        target = repo_root / edit["path"]
        content = target.read_text()
        # Re-check uniqueness at apply time (earlier edits may have shifted things).
        if content.count(edit["original_block"]) != 1:
            print(f"[{i}] DROP {edit['path']!r}: original_block no longer unique after prior edits")
            continue
        target.write_text(content.replace(edit["original_block"], edit["new_block"], 1))
        applied.append(edit)
        print(f"[{i}] APPLY {edit['path']}  ({edit.get('rule', '?')})")
    return applied


def run_guardrails(repo_root: Path) -> None:
    """Run cargo fmt + cargo check. Raises SystemExit on failure."""
    # cargo fmt is a formatter — safe to run. It normalizes our whitespace edits.
    run(["cargo", "fmt", "--all"], cwd=str(repo_root))
    # cargo check is the backstop that proves we didn't break compilation.
    run(["cargo", "check", "--all-targets"], cwd=str(repo_root))


# --------------------------------------------------------------------------- #
# PR creation
# --------------------------------------------------------------------------- #


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def check_existing_pr(repo: str, subpath: str) -> str | None:
    """Return the URL of an existing open style-bot PR for this path, else None."""
    result = run(
        ["gh", "pr", "list", "--repo", repo, "--state", "open",
         "--search", f"head:style-bot/cleanup-{_slug(subpath)}",
         "--json", "url,headRefName"],
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return items[0]["url"] if items else None


def open_pr(repo_root: Path, repo: str, subpath: str, applied: list[dict]) -> str:
    date = _dt.date.today().isoformat()
    branch = f"style-bot/cleanup-{_slug(subpath)}-{date}"
    run(["git", "checkout", "-b", branch], cwd=str(repo_root))

    # Commit
    run(["git", "add", "-A"], cwd=str(repo_root))
    title = f"style: Clean up comment formatting in `{subpath}`"
    body_lines = [
        f"Automated style cleanup for `{subpath}`.",
        "",
        f"Applied {len(applied)} edit(s):",
        "",
    ]
    for e in applied:
        body_lines.append(f"- **{e.get('rule', 'style')}** in `{e['path']}` — {e.get('rationale', '').strip()}")
    body_lines += [
        "",
        "This PR was produced by the style-cleanup bot and is comment-only /",
        "whitespace-only. `cargo fmt` and `cargo check` both passed locally",
        "before it was opened.",
    ]
    body = "\n".join(body_lines)
    run(["git", "commit", "-m", title, "-m", body], cwd=str(repo_root))

    # Push + PR
    run(["git", "push", "-u", "origin", branch], cwd=str(repo_root))
    result = run(
        ["gh", "pr", "create", "--repo", repo,
         "--base", "main", "--head", branch,
         "--title", title, "--body", body,
         "--label", "style-bot", "--label", "auto-generated"],
        cwd=str(repo_root),
        check=False,
    )
    if result.returncode != 0:
        # Retry without labels in case they don't exist in the sandbox yet.
        print("Retrying PR creation without labels ...", file=sys.stderr)
        result = run(
            ["gh", "pr", "create", "--repo", repo,
             "--base", "main", "--head", branch,
             "--title", title, "--body", body],
            cwd=str(repo_root),
        )
    return result.stdout.strip()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                        help="Target repo in owner/name format")
    parser.add_argument("--path", default=os.environ.get("TARGET_PATH"),
                        help="Subdirectory (or file) within the repo to clean up")
    parser.add_argument("--workdir", default=None,
                        help="Working directory for the clone (default: temp dir)")
    parser.add_argument("--max-files", type=int, default=20,
                        help="Maximum files to send to Claude in one run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apply edits locally but do not push or open a PR")
    args = parser.parse_args()

    if not args.repo or not args.path:
        parser.error("--repo and --path are required (or set GITHUB_REPOSITORY / TARGET_PATH)")

    # Required secrets for Bedrock.
    for env in ("BEDROCK_ENDPOINT_URL", "BEDROCK_BEARER_TOKEN"):
        if not os.environ.get(env):
            parser.error(f"{env} must be set in the environment")

    workdir_owned = args.workdir is None
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="style-bot-"))
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"Working directory: {workdir}")

    try:
        # 1. Pre-flight: bail if there's already an open PR for this path.
        if not args.dry_run:
            existing = check_existing_pr(args.repo, args.path)
            if existing:
                print(f"Open style-bot PR already exists for {args.path}: {existing}")
                print("Skipping this run. Close or merge the existing PR first.")
                return

        # 2. Clone + enumerate.
        repo_root = clone_repo(args.repo, workdir)
        botignore = load_botignore(str(repo_root))
        files = enumerate_files(repo_root, args.path, botignore, args.max_files)
        print(f"Selected {len(files)} file(s) under {args.path}.")
        if not files:
            print("No eligible files. Exiting.")
            return

        # 3. Prompt Claude.
        style_guide = get_style_guide()
        file_sections = build_file_sections(repo_root, files)
        edits = call_claude_for_edits(style_guide, file_sections, args.path)
        print(f"Claude proposed {len(edits)} edit(s).")
        if not edits:
            print("Nothing to do. Exiting.")
            return

        # 4. Apply + guardrails.
        applied = apply_edits(edits, repo_root)
        if not applied:
            print("No edits survived validation. Exiting.")
            return
        run_guardrails(repo_root)

        # 5. PR.
        if args.dry_run:
            print(f"Dry run — {len(applied)} edit(s) applied locally in {repo_root}.")
            diff = run(["git", "diff"], cwd=str(repo_root), check=False).stdout
            print("\n=== DIFF ===\n" + diff)
            return

        url = open_pr(repo_root, args.repo, args.path, applied)
        print(f"Opened PR: {url}")

    finally:
        if workdir_owned and not args.dry_run:
            # Keep the workdir around on dry run so the user can inspect.
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
