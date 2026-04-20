#!/usr/bin/env python3
"""Review a pull request against the style guide and post an inline GitHub review."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

MAX_DIFF_CHARS = 80_000
MAX_COMMENTS = 15

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


def get_style_guide() -> str:
    guide_path = Path(__file__).parent.parent / "style-guide.md"
    return guide_path.read_text()


def build_prompt(style_guide: str, diff: str, pr_title: str, pr_body: str) -> str:
    return f"""You are a code style reviewer for an open-source project. Review the pull request diff below against the provided style guide and return inline review comments as a JSON array.

## Style Guide

{style_guide}

---

## Pull Request

**Title:** {pr_title}

**Description:**
{pr_body or "(no description provided)"}

---

## Diff

```diff
{diff}
```

---

## Instructions

1. Identify style violations in the diff. Only flag lines that are **additions** (lines starting with `+`, but NOT the `+++` file header lines).

2. Be selective — flag only genuine violations of the rules above. Do not invent rules. Do not flag code style preferences that aren't in the guide. Focus on the {MAX_COMMENTS} most impactful issues.

3. For each issue, produce a JSON object with:
   - `path` (string): file path as shown after `+++ b/` in the diff header (without the `b/` prefix)
   - `line` (integer): the **new file** line number where the issue appears (the line number in the file after the change, not the diff position)
   - `body` (string): GitHub-flavored markdown comment body including:
     - Bold header: the rule name
     - Reference link to the style guide page
     - Brief explanation of the issue
     - A concrete `suggestion` code block if a fix is straightforward (use GitHub suggestion syntax: three backticks followed by `suggestion`)
   - `severity` (string): one of `"suggestion"`, `"warning"`, or `"info"`

4. If multiple rules are violated on the same line, **consolidate them into a single comment** that covers all violations. List each rule name and explanation in the same comment body, and provide only one `suggestion` block that fixes all issues at once.

5. Return **only** a JSON array — no prose, no code fences wrapping the JSON itself. If there are no issues, return `[]`.

Example output (two comments):
[
  {{
    "path": "src/lib.rs",
    "line": 42,
    "body": "**Style: Use complete sentences in comments** ([Reference](https://howicode.ericscouten.com/language/complete-sentences))\\n\\nThis comment is missing a trailing period and a capital letter.\\n\\n```suggestion\\n// Recursively apply passthrough replacement and write the result.\\n```",
    "severity": "suggestion"
  }},
  {{
    "path": "src/parser.rs",
    "line": 17,
    "body": "**Style: Use sentence case** ([Reference](https://howicode.ericscouten.com/language/sentence-case))\\n\\nComment uses title case. Only capitalize the first word and proper nouns.",
    "severity": "suggestion"
  }}
]"""


def parse_claude_response(text: str) -> list[dict]:
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
    return json.loads(text)


def call_claude(style_guide: str, diff: str, pr_title: str, pr_body: str) -> list[dict]:
    bearer_token = os.environ["BEDROCK_BEARER_TOKEN"]
    url = os.environ["BEDROCK_ENDPOINT_URL"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    payload = {
        "messages": [{
            "role": "user",
            "content": [{"text": build_prompt(style_guide, diff, pr_title, pr_body)}],
        }],
        "inferenceConfig": {"maxTokens": 4096},
    }

    response = requests.post(url, json=payload, headers=headers, timeout=120)
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

    return parse_claude_response(text_blocks[0])


_SUGGESTION_BLOCK = re.compile(r"```suggestion\n.*?```", re.DOTALL)


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


def post_review(pr_number: str, repo: str, comments: list[dict], commit_sha: str):
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

    botignore = load_botignore(os.environ.get("GITHUB_WORKSPACE", "."))
    pr_info = get_pr_info(pr_number, repo)
    diff = get_pr_diff(pr_number, repo)
    style_guide = get_style_guide()

    print(f"Diff size: {len(diff):,} chars")

    raw_comments = call_claude(style_guide, diff, pr_info["title"], pr_info.get("body") or "")
    print(f"Claude returned {len(raw_comments)} candidate comment(s).")

    # Filter comments for skipped/ignored files
    comments = [
        c for c in raw_comments
        if not should_skip_file(c["path"])
        and not matches_botignore(c["path"], botignore)
    ]

    if len(comments) < len(raw_comments):
        skipped = len(raw_comments) - len(comments)
        print(f"Skipped {skipped} comment(s) for ignored/generated files.")

    before_consolidation = len(comments)
    comments = consolidate_comments(comments)
    merged = before_consolidation - len(comments)
    if merged:
        print(f"Consolidated {merged} duplicate comment(s) at the same line.")

    post_review(pr_number, repo, comments, pr_info["headRefOid"])


if __name__ == "__main__":
    main()
