# Style guide bot for CAI GitHub projects

## Problem

Our team maintains several public open-source repositories across multiple programming languages. Keeping code consistent with our style guide is manual, easy to forget, and doesn't scale across repos. This project is an effort to build an automated system that both catches style issues in new PRs and gradually improves existing code.

## Goals

1. **PR Review:** Automatically review every new PR for style guide conformance and post suggested changes.
2. **Proactive Cleanup:** Periodically scan the main branch and open small, focused PRs that improve existing code.
3. **Multi-repo, multi-language:** Works across the org's public repos (Rust, possibly others).
4. **Extensible:** Start with Eric's personal style guide ([howicode.ericscouten.com](https://howicode.ericscouten.com/)); add team-specific rules over time.
5. **Low cost:** Prefer free resources; accept modest compute costs for the AI backbone.

## Style guide summary

The bot would enforce / nudge us toward these principles:
  
_(Eric's editorial comment: Some of these are language-preference style guides from [my personal style guide](https://howicode.ericscouten.com/) that may not apply here. And these are, of course, subject to debate and evolution.)_

## Proposed architecture

```
┌─────────────────────────────────────────────────────────┐
│ Bot Repo: (this repo).                                  │
│ ├── style-guide.md (canonical rules for prompt)         │
│ ├── per-repo overrides (optional)                       │
│ └── reusable workflow (.github/workflows/)              │
│ ├── pr-review.yml                                       │
│ └── proactive-cleanup.yml                               │
└─────────────────────────────────────────────────────────┘
 │ called by each repo via
 │ `uses: org/style-bot-config/.github/workflows/pr-review.yml@main`
 ▼
┌─────────────────────────────────────────────────────────┐
│ Target Repo (e.g., c2pa-rs)                             │
│ .github/workflows/                                      │
│ ├── style-review.yml → calls shared PR review           │
│ └── style-cleanup.yml → calls shared cleanup            │
└─────────────────────────────────────────────────────────┘
```

### Component 1: Shared style guide prompt

A single Markdown file that encodes our style guide as instructions for Claude. This is the single source of truth; when you update the style guide website, you update this file. It would include:

- All the rules above, written as actionable review instructions
- Per-language notes (e.g., "For Rust, check that \`rustfmt.toml\` matches these settings")
- Examples of good vs. bad style
- Severity levels (e.g., "sentence case in comments" = suggestion, "missing test coverage" = warning)

### Component 2: PR review workflow

**Trigger:** `pull_request` events (opened, synchronize)

**Flow:**

1. GitHub Actions workflow starts
2. Fetch the PR diff via `gh pr diff`
3. Fetch changed file contents for context (full files, not just hunks)
4. Send to Claude API with the style guide prompt + diff + file context
5. Parse Claude's response into file-specific inline comments
6. Post as a **GitHub PR review** using the GitHub API (`POST /repos/{owner}/{repo}/pulls/{number}/reviews`)

**Output format:** A single PR review with inline comments at specific lines, using GitHub's "COMMENT" review type (not "REQUEST\_CHANGES" — keeps it advisory). Each comment would include:

- What the style issue is
- A concrete suggested fix (using GitHub's suggestion syntax: ` ```suggestion `)
- Which style guide rule it references

**Example comment:**

> **Style: Use complete sentences in comments** ([Reference](https://howicode.ericscouten.com/language/complete-sentences))
> 
> ` ```suggestion `  
> `// Recursively apply passthrough replacement and write the result.`  
> ` ``` `

**Key design decisions:**

- Use `COMMENT` not `REQUEST_CHANGES` to keep the bot advisory, not blocking
- Rate-limit: max ~15-20 comments per review to avoid overwhelming the author
- Skip files that are auto-generated, vendored, or in `.botignore`
- Only comment on lines that are part of the diff (new or modified lines)

### Component 3: Proactive cleanup workflow

**Trigger:** Cron schedule (e.g., weekly on Monday morning)

**Flow:**

1. GitHub Actions workflow starts on schedule
2. Select a "unit" of code to review:
    - One module/directory at a time
    - Track what's been reviewed recently (via a state file or GitHub issues) to rotate through the codebase
3. Send the files + style guide to Claude API
4. Ask Claude to propose changes, grouped by logical theme
5. For each group of changes:
    - Create a branch (`style-bot/improve-{module}-{date}`)
    - Apply changes
    - Open a PR with a clear description of what was changed and why
6. Limit: max 1-2 PRs per run to keep the queue manageable

**PR characteristics:**

- Small scope: one module or one type of improvement at a time
- Clear title: e.g., "style: Improve comment formatting in `sdk/src/parser`"
- Description explains each change with style guide references
- Labels: `style-bot`, `auto-generated`

**Guardrails:**

- Never modify logic or behavior — style/formatting/comments only
- Run `cargo fmt` / language formatter + `cargo check` / equivalent before opening PR
- Don't open a new PR if there's already an open style-bot PR for that module
- Configurable: repos can opt out of proactive cleanup
- TEMPORARY during initial development: Runs against a [separate public sandbox repo](https://github.com/scouten-adobe/TEMP-c2pa-rs), which cloned but not forked from c2pa-rs

## Technology choices

## Cost estimate

For a typical PR review (~500 lines of diff + ~2000 lines of context):

- ~3K input tokens, ~1K output tokens per review
- Claude Sonnet: ~$0.01-0.03 per PR review
- For 50 PRs/month across repos: **~$1-2/month**

For proactive cleanup (reviewing one module per week per repo):

- ~10K input tokens, ~3K output tokens per module
- 4 repos × 4 reviews/month: **~$1-2/month**

**Total estimated cost: $2-5/month** for the Claude API usage. GitHub Actions minutes are free for public repos.

## Implementation plan

### Phase 1: Foundation ✅

- ~~Create the repo~~ — done
- ~~Write the style guide prompt~~ ([`style-guide.md`](style-guide.md)) — 6 rules from [howicode.ericscouten.com](https://howicode.ericscouten.com/) with severity levels and examples
- ~~Build the core review script~~ ([`scripts/review_pr.py`](scripts/review_pr.py)) — fetches PR diff, calls Claude, posts inline GitHub review comments
- ~~Test locally against a sample PR diff from c2pa-rs~~ – DONE

### Phase 2: PR review bot ✅

- ~~Build the GitHub Actions workflow for PR review~~ ([`.github/workflows/pr-review.yml`](.github/workflows/pr-review.yml)) — reusable `workflow_call` workflow
- ~~Implement the comment-posting logic~~ (inline review comments with suggestion syntax) — done in `review_pr.py`
- ~~Handle edge cases: binary files, auto-generated files~~ — done; large PRs (chunking) still TODO
- ~~Deploy to a test repo, open a test PR~~ — successfully generated review comments against a sample PR in a sandbox repo

### Phase 3: Proactive cleanup bot

- Build the module-selection logic (rotate through directories)
- Build the change-application pipeline (branch, apply, format, check, PR)
- Implement guardrails (no logic changes, formatter check, duplicate PR check)
- Test on c2pa-rs

### Phase 4: Polish and multi-repo

- ~~Add `.botignore` support~~ — done in `review_pr.py`
- Add per-repo configuration overrides
- Deploy to a second repo to validate multi-repo support
- Write documentation for onboarding new repos

### Phase 5: Demo and iterate

- Demo to the team
- Collect feedback, iterate on prompt quality and comment formatting
- Plan post-hack-week roadmap (custom rules, dashboards, etc.)

## Alternatives considered

### Why not use existing linters (clippy, eslint, etc.)?

Linters catch mechanical issues but can't evaluate subjective style preferences like "use vertical whitespace intentionally" or "avoid cleverness." The style guide is fundamentally about judgment and readability, which is where an LLM excels. _(Also: We already use these to the extent they are available.)_

### Why not use an existing review bot (e.g., CodeRabbit, Sourcery)?

These are good products but:

- They impose their own style opinions rather than enforcing ours
- They're not easily customizable to a personal/team style guide
- Many are paid services with per-seat pricing that doesn't fit the "low cost for public repos" goal
- Building our own gives full control over the prompt, output format, and behavior
- (Separate from this proposal, I'm _also_ investigating deploying [Greptile](https://greptile.ai/), which has some ability to adapt to a team's style)

### Why Claude over GPT-4 or other models?

- Corporate support for using Claude
- Strong code review quality at competitive pricing
- Sonnet hits the sweet spot of quality vs. cost for this use case

### PR-against-PR (alternative output for large changes)

### If a review would produce more than ~20 suggestions, the bot could instead:

1. Create a branch from the PR's head
2. Apply all suggestions
3. Open a PR targeting the original PR's branch
4. Comment on the original PR: "I had a lot of suggestions, so I opened #123 with all of them applied."

This is worth building as a later enhancement.

## Open questions

1. **Bot identity:** Use a dedicated GitHub bot account or a personal access token? (Bot account is cleaner for team repos.)
2. **Review gating:** Should the bot review be required to pass before merge, or purely advisory? (Recommend: advisory to start.)
3. **Cleanup PR approval:** Should cleanup PRs auto-merge after CI passes, or always require human review? (Recommend: always human review to start.)
4. **Prompt iteration:** How do you want to iterate on the style guide prompt? Track it in the config repo with PRs, or iterate more informally?
