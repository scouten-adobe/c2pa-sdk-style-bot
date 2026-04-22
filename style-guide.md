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

**This applies to admonition bodies.** The text after `TODO:`, `FIXME:`,
`NOTE:`, `WARNING:`, `HACK:` must itself be a complete sentence — leading
capital letter and trailing period. The keyword casing is governed by Rule 1;
the body text is governed by this rule. Always flag admonition bodies that
omit the leading capital or trailing period, even if the keyword is correct.

**Exceptions:**

1. **Titles and captions** (section headings in docs, short field descriptions
   in structs) may omit the trailing period if they are not full sentences.
   Still use sentence case.

2. **Short descriptive fragments** that label a data structure, a variable's
   contents, or a specific value — typically end-of-line comments next to a
   literal, struct field, or single statement — may be sentence fragments.
   They do **not** require a leading capital or trailing period. Acronym
   casing (Rule 3) and informal-abbreviation rules (Rule 7) still apply,
   as does grammar (Rule 8).

3. **Pull request titles and commit message summaries** must **not** end
   with a trailing period. The rest of this rule still applies (leading
   capital after any `type:` or `type(scope):` prefix, proper acronym
   casing, etc.), as do all other rules.

**Good:**
```rust
// Recursively apply passthrough replacement and write the result.
/// Returns the number of items processed.
// TODO: Investigate whether this edge case can actually occur.
let mut no_bytes = vec![0; 50]; // enough bytes to be valid
no_bytes.splice(16..20, C2PA_MARKER); // CAI UUID signature
```

**Bad:**
```rust
// recursively apply passthrough replacement and write the result
/// returns the number of items processed
// Check for null
// TODO: investigate this edge case      // admonition body needs capital + period
// TODO: optimize this by implementing a streaming parser   // same problem
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

**Severity:** suggestion

**Rule:** Use blank lines to separate distinct logical sections within a
function or block. Blank lines signal transitions between different concerns.
Think of them like paragraph breaks in prose.

- Separate parsing/setup from computation from output
- Add blank lines around multi-line expressions to give them visual breathing room
- Group related fields in structs with blank lines between conceptual groups
- In `match` / `switch` statements, put a blank line between arms whenever
  at least one arm spans more than a single line. Single-line arms can stay
  contiguous, but as soon as any arm has a body block or multi-line expression,
  separate every arm in that statement with a blank line.

**When to flag:**

1. If a contiguous block inside a function or branch contains roughly 8 or
   more statement lines with no blank line between them, and you can identify
   at least one natural conceptual boundary (e.g., "parse input" → "do the
   work" → "build result"), flag it and suggest a blank-line break at that
   boundary. Prefer flagging the first (outermost) offending block rather
   than every nested one.

2. If a `match` / `switch` statement has two or more arms and at least one
   arm spans multiple lines, flag any adjacent arms that aren't separated by
   a blank line. When this happens, post a single comment on the first arm
   of the statement that is missing the separator, describing the problem
   once for the whole statement — do not post one comment per arm.

**Good (match arms separated by blank lines):**
```rust
match seg.marker() {
    markers::APP11 => {
        // Handle JUMBF marker.
        let raw = seg.contents();
        process(raw);
    }

    markers::APP1 => {
        // Handle XMP / Exif marker.
        positions.push(make_position(seg));
    }

    _ => {
        positions.push(make_position(seg));
    }
}
```

**Bad (multi-line match arms with no blank lines between them):**
```rust
match seg.marker() {
    markers::APP11 => {
        let raw = seg.contents();
        process(raw);
    }
    markers::APP1 => {
        positions.push(make_position(seg));
    }
    _ => {
        positions.push(make_position(seg));
    }
}
```

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

## Rule 7: Spell out informal word abbreviations

**Severity:** suggestion

**Rule:** In comments and documentation, prefer full words to informal
partial-word abbreviations. Words like `seg`, `func`, `msg`, `cnt`, `tmp`,
`buf` (outside of established API names), `idx`, `ptr` reduce readability
when the full word would fit just as easily.

**Exceptions:**

- **Language keywords and conventional identifiers:** `impl`, `fn`, `mut`,
  `ref`, `pub` in Rust; similar keywords in other languages. These are
  part of the language, not informal shortenings.
- **Domain-standard acronyms:** `HTTP`, `URL`, `JSON`, `XMP`, `JUMBF`, etc.
  See Rule 3 for casing.
- **Established identifiers in the surrounding code.** Do not flag a
  variable name just because it uses an abbreviation — that's a naming
  convention, not a comment.

This rule targets **free-text prose in comments**, not identifier names.

**Good:**
```rust
// Create a dummy JUMBF segment.
// The message counter wraps around at u32::MAX.
```

**Bad:**
```rust
// create dummy JUMBF seg
// The msg cnt wraps around at u32::MAX.
```

**Reference:** <https://howicode.ericscouten.com/language/no-abbreviations>

---

## Rule 8: Basic grammar and typos

**Severity:** suggestion

**Rule:** Check comments and documentation for clear grammatical errors.
Be conservative — only flag high-confidence fixes. Do not flag
stylistic disagreements.

**What to catch:**

- **Possessive apostrophes:** `for completeness sake` → `for completeness' sake`;
  `the users data` → `the user's data`.
- **Homophones:** `it's` vs `its`; `they're` / `their` / `there`;
  `your` vs `you're`; `to` / `too` / `two`.
- **Subject-verb agreement:** `the list contain` → `the list contains`.
- **Clear typos:** `teh` → `the`, `recieve` → `receive`.

**Do NOT flag:**

- Stylistic variations (e.g., Oxford comma preference).
- Regional spelling differences (US vs UK; "color" vs "colour").
- Anything where the error is ambiguous or a judgment call.

**Good:**
```rust
// Save other for completeness' sake.
// The list contains three entries when parsing succeeds.
```

**Bad:**
```rust
// save other for completeness sake
// The list contain three entries when parsing succeed.
```

**Reference:** <https://howicode.ericscouten.com/language/grammar>

---

## Rule 9: Trailing comments that describe behavior go on their own line

**Severity:** suggestion

**Rule:** Trailing end-of-line comments are reserved for **short noun-phrase
fragments that label the adjacent value, field, or literal**. If the trailing
comment instead describes **what the statement does** — the action or
behavior of that line of code — move it to its own line above the statement
and rewrite it as a complete sentence (Rule 2: leading capital, trailing
period).

**How to tell which is which:**

- **Labels a value** (OK as trailing fragment): you could replace it with a
  named constant or a `name:` prefix and it would still make sense. Examples:
  `let retries = 3; // retry budget`, `C2PA_MARKER, // CAI UUID signature`,
  `0x1F, // start-of-image marker`.
- **Describes an action** (move to its own line, write as full sentence):
  starts with an imperative verb (`store`, `skip`, `flush`, `initialize`,
  `fetch`), or uses a verb phrase that narrates what the code is doing.
  Examples: `// store the identifier`, `// skip the header`,
  `// flush to disk`.

**This does NOT override Rule 2 Exception 2.** Short fragments that label
data stay valid as trailing comments and do not need sentence case or a
trailing period. This rule targets action/behavior narration, regardless of
length — even a two-word imperative like `// store the identifier` is an
action description and should move.

**Good:**
```rust
// Store the identifier for later comparison against subsequent segments.
cai_en.clone_from(&en);

let retries = 3; // retry budget
C2PA_MARKER, // CAI UUID signature
```

**Bad:**
```rust
cai_en.clone_from(&en); // store the identifier
output.flush()?; // flush to disk
let output = decode(&frames[1..]); // Skip the first frame because the decoder primes it with zeros.
```

**Reference:** <https://howicode.ericscouten.com/language/complete-sentences>

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
