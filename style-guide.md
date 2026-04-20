# Style Guide for Code Review

This document defines the style rules enforced by the automated review bot.
The primary source is Eric Scouten's personal style guide at
<https://howicode.ericscouten.com/>.

---

## Rule 1: Use sentence case in comments and documentation

**Severity:** suggestion

**Rule:** Capitalize only the first word and proper nouns in comments,
documentation strings, variable names, and any other English prose in code.
Do not use title case for ordinary phrases.

**Exception:** `ALL CAPS` is acceptable and encouraged for admonitions such
as `FIXME:`, `TODO:`, `NOTE:`, `WARNING:`, `HACK:`. These should include a
colon after the keyword.

**Good:**
```rust
// Recursively apply passthrough replacement and write the result.
/// Returns the XMP metadata block if present.
// FIXME: This edge case is not handled correctly.
```

**Bad:**
```rust
// Recursively Apply Passthrough Replacement and Write the Result.
/// Returns The XMP Metadata Block If Present.
// fixme: this edge case is not handled correctly.
// fixme we probably shouldn't even get here
```

**Reference:** <https://howicode.ericscouten.com/language/sentence-case>

---

## Rule 2: Use complete sentences in comments and documentation

**Severity:** suggestion

**Rule:** Write comments and doc comments as complete sentences with proper
punctuation. A complete sentence starts with a capital letter and ends with
a period (or other appropriate terminal punctuation).

**Exception:** Titles and captions (e.g., section headings in docs, short
field descriptions in structs) may omit the trailing period if they are not
full sentences. These should still use sentence case.

**Good:**
```rust
// Recursively apply passthrough replacement and write the result.
/// Returns the number of items processed.
```

**Bad:**
```rust
// recursively apply passthrough replacement and write the result
/// returns the number of items processed
// Check for null
```

**Reference:** <https://howicode.ericscouten.com/language/complete-sentences>

---

## Rule 3: Use correct capitalization for acronyms

**Severity:** suggestion

**Rule:** Capitalize acronyms and proper names according to their established
conventions, not as ALL-CAPS unless that is the actual convention.

- `XMP` — correct (solid-caps acronym by convention)
- `Exif` — correct (this is the creator's established convention, not `EXIF`)
- `JSON`, `URL`, `HTTP` — correct (solid-caps by convention)

**Exception:** In code identifiers, follow the language's naming convention.
In Rust: `XmpReader` (struct), `xmp_reader` (function/variable). Don't
invent casing that contradicts the language spec.

**Good:**
```rust
/// Reads Exif metadata from the file.
struct XmpFileReader { ... }
fn read_exif_data() { ... }
```

**Bad:**
```rust
/// Reads EXIF metadata from the file.
struct ExifFileReader { ... }  // should be XmpFileReader if it's XMP
```

**Reference:** <https://howicode.ericscouten.com/language/acronyms>

---

## Rule 4: Use vertical whitespace intentionally

**Severity:** info

**Rule:** Use blank lines to separate distinct logical sections within a
function or block. Blank lines signal transitions between different concerns.
Think of them like paragraph breaks in prose.

- Separate parsing/setup from computation from output
- Add blank lines around multi-line expressions to give them visual breathing room
- Group related fields in structs with blank lines between conceptual groups

**What to avoid:**
- No blank lines between logically separate sections (hard to parse)
- Excessive blank lines that don't mark meaningful transitions
- Blank lines inside tightly related groups of statements

**Good:**
```rust
fn process(input: &str) -> Result<Output> {
    let parsed = parse(input)?;
    let validated = validate(&parsed)?;

    let result = transform(validated);

    write_output(&result)?;
    Ok(result)
}
```

**Bad:**
```rust
fn process(input: &str) -> Result<Output> {
    let parsed = parse(input)?;
    let validated = validate(&parsed)?;
    let result = transform(validated);
    write_output(&result)?;
    Ok(result)
}
```

**Reference:** <https://howicode.ericscouten.com/formatting/vertical-whitespace>

---

## Rule 5: Use conventional commit format for commit message references

**Severity:** info

**Rule:** When code comments reference commits, issues, or PRs, be specific.
When writing commit messages (visible in `git log` blocks in docs), use the
Conventional Commits format: `type(scope): description`.

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`.

**Good:**
```
feat(parser): add support for multi-line string literals
fix(sdk): handle empty input without panicking
```

**Bad:**
```
fixed stuff
update code
```

**Reference:** <https://howicode.ericscouten.com/git/>

---

## Rule 6: Invest in test coverage

**Severity:** warning

**Rule:** New public functions and significant logic changes should include
tests. Prefer testing edge cases and error paths, not just the happy path.

**What to flag:**
- New public API functions with no corresponding test
- Complex logic (conditionals, loops, error handling) with no test coverage
- Test files that only cover the happy path for complex functions

**Note:** Do not flag this for obviously untestable infrastructure code
(e.g., `main()`, simple re-exports, pure wrappers with no logic).

**Reference:** <https://howicode.ericscouten.com/credit-cards/code-coverage>

---

## Scope limitations

**Only comment on:**
- Lines that are additions in the diff (lines starting with `+`, not the `+++` header)
- Code in source files (`.rs`, `.py`, `.ts`, `.js`, `.go`, `.md`, etc.)

**Do NOT comment on:**
- Auto-generated files (e.g., `Cargo.lock`, `package-lock.json`, `*.pb.go`, any file with a `// Code generated` header)
- Build artifacts, vendored dependencies
- Files listed in `.botignore` at the repo root
- Binary files
- Trivial changes (version bumps in manifest files, adding a single import)
- Lines that were not changed in this PR (context lines, deletion lines)
