#!/usr/bin/env python3
"""Review a pull request against the style guide and post an inline GitHub review."""

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

MAX_DIFF_CHARS = 80_000
MAX_COMMENTS = 25
CONTEXT_LINES = 20  # lines of surrounding context shown to Claude around each hunk
ALIGNMENT_SEARCH_RADIUS = 5  # how far to look when correcting off-by-N line numbers

SKIP_EXTENSIONS = {
    ".lock", ".pb", ".pb.go", ".min.js", ".min.css", ".svg", ".png",
    ".jpg", ".jpeg", ".gif", ".ico", ".wasm", ".bin",
}

SKIP_FILENAMES = {
    "Cargo.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.sum", "poetry.lock", "Pipfile.lock",
}

GENERATED_MARKERS = [
    "// Code generated",
    "// DO NOT EDIT",
    "# This file is auto-generated",
    "# DO NOT EDIT",
    "/* Auto-generated",
]


def should_skip_file(path: str) -> bool:
    name = Path(path).name
    if name in SKIP_FILENAMES:
        return True
    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def load_botignore(repo_root: str) -> list[str]:
    botignore_path = Path(repo_root) / ".botignore"
    if not botignore_path.exists():
        return []
    lines = botignore_path.read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def matches_botignore(path: str, patterns: list[str]) -> bool:
    import fnmatch
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern):
            return True
    return False


def get_pr_info(pr_number: str, repo: str) -> dict:
    result = subprocess.run(
        ["gh", "pr", "view", pr_number, "--repo", repo,
         "--json", "title,body,headRefOid"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def get_pr_diff(pr_number: str, repo: str) -> str:
    result = subprocess.run(
        ["gh", "pr", "diff", pr_number, "--repo", repo],
        capture_output=True, text=True, check=True,
    )
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[...diff truncated due to size...]"
    return diff


_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_NEW_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")


def parse_diff_added_ranges(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Return per-path list of (start, end) inclusive ranges of *added* new-file lines.

    Only lines prefixed with '+' in the diff body are in-scope. Context lines
    (prefix ' ') are excluded even when they fall inside a hunk, because an
    unchanged line adjacent to a deletion is not actually part of this change.
    """
    added: dict[str, list[int]] = {}
    current_path: str | None = None
    new_counter = 0
    in_hunk = False

    for line in diff.splitlines():
        m = _NEW_FILE_HEADER_RE.match(line)
        if m:
            path = m.group(1)
            current_path = None if path == "dev/null" else path
            if current_path is not None:
                added.setdefault(current_path, [])
            in_hunk = False
            continue
        if line.startswith("diff --git ") or line.startswith("--- "):
            in_hunk = False
            continue
        m = _HUNK_HEADER_RE.match(line)
        if m and current_path is not None:
            new_counter = int(m.group(1))
            in_hunk = True
            continue
        if not in_hunk or current_path is None:
            continue
        if line.startswith(" "):
            new_counter += 1
        elif line.startswith("+"):
            added[current_path].append(new_counter)
            new_counter += 1
        elif line.startswith("-") or line.startswith("\\"):
            pass
        else:
            in_hunk = False

    result: dict[str, list[tuple[int, int]]] = {}
    for path, lines in added.items():
        if not lines:
            result[path] = []
            continue
        lines.sort()
        ranges = [(lines[0], lines[0])]
        for n in lines[1:]:
            s, e = ranges[-1]
            if n == e + 1:
                ranges[-1] = (s, n)
            else:
                ranges.append((n, n))
        result[path] = ranges
    return result


def fetch_file_lines(repo: str, path: str, ref: str) -> list[str] | None:
    """Fetch file content at ref and return it as a list of lines, or None on failure."""
    # Put ref in the URL query string. Using `-f ref=...` would cause gh api
    # to switch to POST and hit the wrong endpoint.
    from urllib.parse import quote
    api_url = f"/repos/{repo}/contents/{quote(path)}?ref={quote(ref)}"
    result = subprocess.run(
        ["gh", "api", api_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Warning: could not fetch {path}@{ref[:7]}: {result.stderr.strip()}", file=sys.stderr)
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    encoded = data.get("content")
    if not encoded:
        return None
    try:
        text = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return text.splitlines()


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent (start, end) inclusive ranges."""
    if not ranges:
        return []
    ordered = sorted(ranges)
    merged = [ordered[0]]
    for s, e in ordered[1:]:
        ms, me = merged[-1]
        if s <= me + 1:
            merged[-1] = (ms, max(me, e))
        else:
            merged.append((s, e))
    return merged


def build_file_sections(
    repo: str,
    ref: str,
    added_ranges: dict[str, list[tuple[int, int]]],
    botignore: list[str],
) -> tuple[str, dict[str, list[str]]]:
    """Build the per-file context block for the prompt and return a cache of file lines."""
    sections: list[str] = []
    file_cache: dict[str, list[str]] = {}

    for path in sorted(added_ranges):
        ranges = added_ranges[path]
        if not ranges:
            continue
        if should_skip_file(path) or matches_botignore(path, botignore):
            continue
        lines = fetch_file_lines(repo, path, ref)
        if lines is None:
            continue
        file_cache[path] = lines

        display_windows = _merge_ranges([
            (max(1, s - CONTEXT_LINES), min(len(lines), e + CONTEXT_LINES))
            for s, e in ranges
        ])

        ranges_str = ", ".join(f"{s}-{e}" if s != e else str(s) for s, e in ranges)

        chunk: list[str] = [
            f"### File: {path}",
            f"**In-scope line ranges (lines ADDED by this PR — the only lines you may post comments on):** {ranges_str}",
            "",
            "**File content (line numbers shown; unchanged lines outside the in-scope ranges are context only — do not flag them even if they contain style issues):**",
            "```",
        ]
        for i, (ws, we) in enumerate(display_windows):
            if i > 0:
                chunk.append("...")
            for n in range(ws, we + 1):
                chunk.append(f"{n:5d}: {lines[n - 1]}")
        chunk.append("```")
        sections.append("\n".join(chunk))

    return "\n\n".join(sections), file_cache


def get_style_guide() -> str:
    guide_path = Path(__file__).parent.parent / "style-guide.md"
    return guide_path.read_text()


def build_prompt(
    style_guide: str,
    file_sections: str,
    diff: str,
    pr_title: str,
    pr_body: str,
) -> str:
    return f"""You are a code style reviewer for an open-source project. Review the pull request changes below against the provided style guide and return inline review comments as a JSON array.

## Style Guide

{style_guide}

---

## Pull Request

**Title:** {pr_title}

**Description:**
{pr_body or "(no description provided)"}

---

## Files changed (with surrounding context)

Each file shows the new-file content around the changed regions with real line numbers on the left. **You may only post comments on lines inside the declared in-scope ranges for that file.** Lines outside those ranges are shown for context so you can understand the surrounding code; never flag them.

{file_sections}

---

## Diff (for reference)

```diff
{diff}
```

---

## Instructions

1. Identify style violations on lines **inside the declared in-scope ranges** above (these are the lines ADDED by this PR). Consider the surrounding context when judging the change, but **never flag unchanged lines** — even if they contain style issues, they are not part of this change. In particular, a line shown near a deletion but unchanged in the new file is out of scope.

2. Be selective — flag only genuine violations of the rules above. Do not invent rules. Do not flag code style preferences that aren't in the guide. Focus on the {MAX_COMMENTS} most impactful issues.

3. For each issue, produce a JSON object with:
   - `path` (string): file path (no `a/` or `b/` prefix)
   - `line` (integer): the new-file line number where the issue appears, copied from the numbered listing above
   - `original_line` (string): the exact, verbatim current content of that line in the new file (copy it from the numbered listing; omit the line-number prefix and the `: ` separator, but preserve all leading/trailing whitespace in the actual code). This is used to verify alignment — if it doesn't match the file, your comment will be dropped.
   - `body` (string): GitHub-flavored markdown comment body including:
     - Bold header: the rule name
     - Reference link to the style guide page
     - Brief explanation of the issue
     - A concrete `suggestion` code block if a fix is straightforward (use GitHub suggestion syntax: three backticks followed by `suggestion`). The suggestion block **replaces the single line at `line`** — make sure its content is a drop-in replacement for `original_line`, preserving the same indentation and surrounding code structure.
   - `severity` (string): one of `"suggestion"`, `"warning"`, or `"info"`

4. If multiple rules are violated on the same line, **consolidate them into a single comment** that covers all violations. List each rule name and explanation in the same comment body, and provide only one `suggestion` block that fixes all issues at once.

5. Return **only** a JSON array — no prose, no code fences wrapping the JSON itself. If there are no issues, return `[]`.

6. **CRITICAL output format**: Your entire response must start with the character `[` and end with the character `]`. Do not write any text, explanation, reasoning, preamble, or analysis before or after the JSON array. Do your analysis silently; only the JSON array should appear in your output.

Example output (two comments):
[
  {{
    "path": "src/lib.rs",
    "line": 42,
    "original_line": "    // recursively apply passthrough replacement and write",
    "body": "**Style: Use complete sentences in comments** ([Reference](https://howicode.ericscouten.com/language/complete-sentences))\\n\\nThis comment is missing a trailing period and a capital letter.\\n\\n```suggestion\\n    // Recursively apply passthrough replacement and write the result.\\n```",
    "severity": "suggestion"
  }},
  {{
    "path": "src/parser.rs",
    "line": 17,
    "original_line": "// Parses The Header Block",
    "body": "**Style: Use sentence case** ([Reference](https://howicode.ericscouten.com/language/sentence-case))\\n\\nComment uses title case. Only capitalize the first word and proper nouns.",
    "severity": "suggestion"
  }}
]"""


def _extract_json_array(text: str) -> str | None:
    """Find the first top-level JSON array in text by bracket matching.

    Tracks string literals so brackets inside strings don't confuse the scan.
    """
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_claude_response(text: str) -> list[dict]:
    print(f"Raw response text ({len(text)} chars): {text!r}")
    text = text.strip()
    if not text:
        return []
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    array_text = _extract_json_array(text)
    if array_text is None:
        print("Warning: no JSON array found in Claude response; treating as no comments.")
        return []
    try:
        return json.loads(array_text)
    except json.JSONDecodeError as e:
        print(f"Warning: extracted JSON array failed to parse ({e}); treating as no comments.")
        return []


def _bedrock_completion(prompt: str, *, max_tokens: int = 4096) -> str:
    """Send a single-turn prompt to the Bedrock endpoint and return the response text."""
    bearer_token = os.environ["BEDROCK_BEARER_TOKEN"]
    url = os.environ["BEDROCK_ENDPOINT_URL"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    payload = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
    }

    response = requests.post(url, json=payload, headers=headers, timeout=120)
    if not response.ok:
        print(
            f"Bedrock returned HTTP {response.status_code}. Body: {response.text[:2000]}",
            file=sys.stderr,
        )
        response.raise_for_status()
    data = response.json()

    stop_reason = data.get("stopReason")
    content_blocks = data.get("output", {}).get("message", {}).get("content", [])
    print(f"API response — stopReason: {stop_reason!r}, content blocks: {len(content_blocks)}")

    text_blocks = [b["text"] for b in content_blocks if "text" in b]
    if not text_blocks:
        raise RuntimeError(
            f"Bedrock returned no text content (stopReason={stop_reason!r}). "
            f"Full response: {data}"
        )
    return text_blocks[0]


def call_claude(
    style_guide: str,
    file_sections: str,
    diff: str,
    pr_title: str,
    pr_body: str,
) -> list[dict]:
    prompt = build_prompt(style_guide, file_sections, diff, pr_title, pr_body)
    print(f"Prompt size: {len(prompt):,} chars")
    return parse_claude_response(_bedrock_completion(prompt))


def _extract_json_object(text: str) -> str | None:
    """Find the first top-level JSON object in text by balanced-brace matching."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def build_title_prompt(style_guide: str, pr_title: str) -> str:
    return f"""You are reviewing the title of a pull request against the style guide below.

## Style Guide

{style_guide}

---

## PR Title

{pr_title}

---

## Instructions

Apply the full rule set above to this PR title. Note these specifics:

- **PR titles must NOT end with a period.** This is an explicit exception to Rule 2's complete-sentence requirement (see Rule 2, Exception 3). If the current title ends with a period, that is itself a violation — remove it.
- Rule 5 (Conventional Commits format) applies: a good PR title looks like `type(scope): description` or `type: description`.
- **Rule 1 (sentence case) applies to the description portion after any `type:` or `type(scope):` prefix.** The first word of the description MUST start with a capital letter. This overrides the common Conventional Commits convention of lowercase descriptions. Examples:
  - `perf: optimize signing passes` → **violation** — must be `perf: Optimize signing passes`
  - `fix(parser): handle empty input` → **violation** — must be `fix(parser): Handle empty input`
  - `feat: Add multi-line support` → compliant
  - `Optimize signing passes` (no prefix) → compliant (already capitalized)
- Rules 3, 7, 8 apply (acronym casing, no informal abbreviations, grammar).
- Only propose a retitle for clear rule violations — not for stylistic preferences. A lowercase first word of the description after a `type:` prefix IS a clear violation.

Output a single JSON object.

If the title has one or more clear violations, output:
{{
  "needs_retitle": true,
  "new_title": "<revised title with violations fixed, no trailing period>",
  "reason": "<one or two sentences citing the specific rule(s) violated>"
}}

If the title is compliant, output exactly:
{{"needs_retitle": false}}

**CRITICAL output format:** Your entire response must be a single JSON object, starting with `{{` and ending with `}}`. No prose, no code fences, no analysis before or after.
"""


def review_pr_title(style_guide: str, pr_title: str) -> dict:
    """Ask Claude to evaluate the PR title. Returns a dict with needs_retitle/new_title/reason."""
    prompt = build_title_prompt(style_guide, pr_title)
    print(f"Title-review prompt size: {len(prompt):,} chars")
    raw = _bedrock_completion(prompt, max_tokens=512)
    print(f"Title-review raw response ({len(raw)} chars): {raw!r}")

    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    parsed: dict | None = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            obj = _extract_json_object(text)
            if obj is not None:
                try:
                    parsed = json.loads(obj)
                except json.JSONDecodeError as e:
                    print(f"Warning: title-review JSON object failed to parse ({e}).", file=sys.stderr)

    if not isinstance(parsed, dict):
        print("Warning: title-review response was not a JSON object; treating as compliant.", file=sys.stderr)
        return {"needs_retitle": False}
    return parsed


def retitle_pr(pr_number: str, repo: str, new_title: str) -> bool:
    """Update the PR title via gh. Returns True on success."""
    result = subprocess.run(
        ["gh", "pr", "edit", pr_number, "--repo", repo, "--title", new_title],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Warning: could not retitle PR: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


_SUGGESTION_BLOCK = re.compile(r"```suggestion\n.*?```", re.DOTALL)


def _line_in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(s <= line <= e for s, e in ranges)


def _strip_suggestion(body: str) -> str:
    return _SUGGESTION_BLOCK.sub("", body).rstrip()


def align_comments(
    comments: list[dict],
    file_cache: dict[str, list[str]],
    added_ranges: dict[str, list[tuple[int, int]]],
) -> list[dict]:
    """Verify each comment's `original_line` against the actual file content.

    - If it matches at the given `line`, keep the comment as-is.
    - If it matches at a nearby line, correct `line` and keep the comment.
    - If it doesn't match anywhere nearby, strip the suggestion block (keeping
      the explanation) so a misaligned suggestion can't destroy real code.
    - If the final line is not in the added-line ranges, drop the comment —
      unchanged lines (even those shown as hunk context) are out of scope.
    """
    result: list[dict] = []
    for c in comments:
        path = c.get("path")
        line = c.get("line")
        if not isinstance(path, str) or not isinstance(line, int):
            print(f"Dropping comment with invalid path/line: {c!r}", file=sys.stderr)
            continue
        if path not in file_cache:
            print(f"Dropping comment on unavailable file {path}: {c!r}", file=sys.stderr)
            continue

        lines = file_cache[path]
        ranges = added_ranges.get(path, [])
        original = (c.get("original_line") or "").rstrip("\n")
        body = c.get("body", "")

        def file_line(n: int) -> str | None:
            if 1 <= n <= len(lines):
                return lines[n - 1]
            return None

        corrected = line
        aligned = original != "" and file_line(line) is not None and file_line(line).rstrip() == original.rstrip()

        if not aligned and original:
            for delta in range(1, ALIGNMENT_SEARCH_RADIUS + 1):
                for cand in (line - delta, line + delta):
                    if file_line(cand) is not None and file_line(cand).rstrip() == original.rstrip():
                        corrected = cand
                        aligned = True
                        break
                if aligned:
                    break

        if not aligned:
            print(
                f"Alignment failure on {path}:{line}: original_line={original!r} does not match "
                f"file content within ±{ALIGNMENT_SEARCH_RADIUS} lines; stripping suggestion block.",
                file=sys.stderr,
            )
            body = _strip_suggestion(body)
            if not body:
                print(f"Dropping comment on {path}:{line} — empty after stripping suggestion.", file=sys.stderr)
                continue

        if not _line_in_ranges(corrected, ranges):
            print(
                f"Dropping comment on {path}:{corrected} — line was not added by this PR "
                f"(added ranges: {ranges}).",
                file=sys.stderr,
            )
            continue

        if corrected != line:
            print(f"Corrected {path}:{line} -> {path}:{corrected} based on original_line match.")

        new_c = dict(c)
        new_c["line"] = corrected
        new_c["body"] = body
        new_c.pop("original_line", None)
        result.append(new_c)
    return result


def _merge_comment_group(group: list[dict]) -> dict:
    suggestions = []
    stripped_bodies = []
    for c in group:
        body = c["body"]
        m = _SUGGESTION_BLOCK.search(body)
        if m:
            suggestions.append(m.group(0))
            stripped_bodies.append(_SUGGESTION_BLOCK.sub("", body).rstrip())
        else:
            stripped_bodies.append(body)

    severity_rank = {"info": 0, "suggestion": 1, "warning": 2}
    severity = max(
        (c.get("severity", "suggestion") for c in group),
        key=lambda s: severity_rank.get(s, 1),
    )

    combined = "\n\n---\n\n".join(stripped_bodies)
    if suggestions:
        combined += "\n\n" + suggestions[-1]

    return {"path": group[0]["path"], "line": group[0]["line"], "body": combined, "severity": severity}


def consolidate_comments(comments: list[dict]) -> list[dict]:
    """Merge multiple comments targeting the same (path, line) into one."""
    groups: dict[tuple, list[dict]] = {}
    for c in comments:
        groups.setdefault((c["path"], c["line"]), []).append(c)

    result = []
    for group in groups.values():
        result.append(group[0] if len(group) == 1 else _merge_comment_group(group))
    return result


def delete_previous_bot_comments(pr_number: str, repo: str, bot_login: str) -> int:
    """Delete all inline review comments authored by `bot_login` on this PR.

    GitHub has no API to delete a COMMENTED review summary, but removing the
    inline threads means the stale summary has no attached discussion.
    """
    owner, repo_name = repo.split("/", 1)
    result = subprocess.run(
        ["gh", "api", "--paginate",
         f"/repos/{owner}/{repo_name}/pulls/{pr_number}/comments"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Warning: could not list prior review comments: {result.stderr.strip()}", file=sys.stderr)
        return 0
    try:
        comments = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Warning: could not parse prior review comments as JSON.", file=sys.stderr)
        return 0

    deleted = 0
    for c in comments:
        if c.get("user", {}).get("login") != bot_login:
            continue
        cid = c.get("id")
        if cid is None:
            continue
        dr = subprocess.run(
            ["gh", "api", "--method", "DELETE",
             f"/repos/{owner}/{repo_name}/pulls/comments/{cid}"],
            capture_output=True, text=True,
        )
        if dr.returncode == 0:
            deleted += 1
        else:
            print(f"Warning: could not delete comment {cid}: {dr.stderr.strip()}", file=sys.stderr)
    return deleted


def post_review(
    pr_number: str,
    repo: str,
    comments: list[dict],
    commit_sha: str,
    title_note: str | None = None,
):
    owner, repo_name = repo.split("/", 1)
    api_path = f"/repos/{owner}/{repo_name}/pulls/{pr_number}/reviews"

    if not comments:
        summary = "Style review complete — no issues found. :white_check_mark:"
    else:
        count = len(comments)
        summary = (
            f"Style review found {count} issue{'s' if count != 1 else ''}. "
            "See inline comments below."
        )

    if title_note:
        summary += "\n\n" + title_note

    gh_comments = [
        {
            "path": c["path"],
            "line": c["line"],
            "side": "RIGHT",
            "body": c["body"],
        }
        for c in comments
    ]

    review_payload = {
        "commit_id": commit_sha,
        "body": summary,
        "event": "COMMENT",
        "comments": gh_comments,
    }

    result = subprocess.run(
        ["gh", "api", api_path, "--method", "POST", "--input", "-"],
        input=json.dumps(review_payload),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error posting review:\n{result.stderr}", file=sys.stderr)
        # Retry without inline comments so we at least leave a summary
        if gh_comments:
            print("Retrying with summary-only review ...", file=sys.stderr)
            review_payload["comments"] = []
            review_payload["body"] = (
                summary + "\n\n_(Inline comments could not be posted — "
                "the line numbers may be outside the diff range.)_"
            )
            retry = subprocess.run(
                ["gh", "api", api_path, "--method", "POST", "--input", "-"],
                input=json.dumps(review_payload),
                capture_output=True,
                text=True,
            )
            if retry.returncode != 0:
                print(f"Retry also failed:\n{retry.stderr}", file=sys.stderr)
                sys.exit(1)
    else:
        print(f"Posted review with {len(comments)} inline comment(s).")


def main():
    pr_number = os.environ.get("PR_NUMBER")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not pr_number or not repo:
        print(
            "Error: PR_NUMBER and GITHUB_REPOSITORY environment variables must be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Reviewing PR #{pr_number} in {repo} ...")

    bot_login = os.environ.get("BOT_LOGIN", "github-actions[bot]")
    removed = delete_previous_bot_comments(pr_number, repo, bot_login)
    if removed:
        print(f"Deleted {removed} prior inline comment(s) authored by {bot_login}.")

    botignore = load_botignore(os.environ.get("GITHUB_WORKSPACE", "."))
    pr_info = get_pr_info(pr_number, repo)
    head_sha = pr_info["headRefOid"]
    diff = get_pr_diff(pr_number, repo)
    style_guide = get_style_guide()

    original_title = pr_info["title"]
    title_review = review_pr_title(style_guide, original_title)
    title_note: str | None = None
    effective_title = original_title
    if title_review.get("needs_retitle"):
        new_title = (title_review.get("new_title") or "").strip()
        reason = (title_review.get("reason") or "").strip()
        if new_title and new_title != original_title:
            if retitle_pr(pr_number, repo, new_title):
                effective_title = new_title
                print(f"Retitled PR: {original_title!r} -> {new_title!r}")
                title_note = (
                    f"_I also updated the PR title: `{original_title}` → `{new_title}`"
                    + (f" ({reason})_" if reason else "_")
                )
            else:
                title_note = (
                    f"_The PR title appears to violate the style guide "
                    f"(suggested: `{new_title}`"
                    + (f" — {reason}" if reason else "")
                    + "), but I was unable to update it automatically._"
                )
        elif new_title:
            print("Title-review suggested the same title; skipping retitle.")

    print(f"Diff size: {len(diff):,} chars")

    added_ranges = parse_diff_added_ranges(diff)
    total_files = sum(1 for r in added_ranges.values() if r)
    print(f"Parsed {total_files} file(s) with added lines.")

    file_sections, file_cache = build_file_sections(repo, head_sha, added_ranges, botignore)
    print(f"Built file sections for {len(file_cache)} file(s) ({len(file_sections):,} chars).")

    raw_comments = call_claude(
        style_guide, file_sections, diff, effective_title, pr_info.get("body") or ""
    )
    print(f"Claude returned {len(raw_comments)} candidate comment(s).")

    # Filter comments for skipped/ignored files
    comments = [
        c for c in raw_comments
        if isinstance(c.get("path"), str)
        and not should_skip_file(c["path"])
        and not matches_botignore(c["path"], botignore)
    ]

    if len(comments) < len(raw_comments):
        skipped = len(raw_comments) - len(comments)
        print(f"Skipped {skipped} comment(s) for ignored/generated files.")

    before_align = len(comments)
    comments = align_comments(comments, file_cache, added_ranges)
    dropped = before_align - len(comments)
    if dropped:
        print(f"Dropped {dropped} misaligned or out-of-range comment(s).")

    before_consolidation = len(comments)
    comments = consolidate_comments(comments)
    merged = before_consolidation - len(comments)
    if merged:
        print(f"Consolidated {merged} duplicate comment(s) at the same line.")

    post_review(pr_number, repo, comments, head_sha, title_note=title_note)


if __name__ == "__main__":
    main()
