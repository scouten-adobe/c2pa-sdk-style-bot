# Style Guide for Code Review

This document defines the style rules enforced by the automated review bot.

Each rule has a stable ID (e.g., `CMT-01`, `FN-02`) so the bot can reference rules consistently in its suggestions. Rule IDs are grouped by category:

- `CMT` — Comment & prose rules (all languages)
- `WS` — Vertical whitespace (all languages)
- `GIT` — Git & PR title conventions
- `TEST` — Testing
- `GEN`, `SUM`, `FN`, `TY`, `MOD`, `MD`, `PR`, `AP` — Rust documentation rules
  (apply to `.rs` files only), synthesized from RFC 505, RFC 1574, the Rust
  API Guidelines, and the Rust standard library's conventions.

Rules are tagged with a **severity** (`warning`, `suggestion`, or `info`) or
are marked **Required** / **Recommended**. Required rules are load-bearing:
breaking them breaks tooling, harms discoverability, or diverges materially
from community norms. Recommended rules are quality norms with legitimate
exceptions.

When the bot cites a rule in a review comment, it should use the rule ID
(for example: "**CMT-01 — Use sentence case**").

The primary source for the `CMT` / `WS` / `GIT` / `TEST` rules is Eric
Scouten's personal style guide at <https://howicode.ericscouten.com/>.

---

## Comment & prose rules (`CMT`)

### `CMT-01` — Use sentence case in comments and documentation

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

### `CMT-02` — Use complete sentences in comments and documentation

**Severity:** suggestion

**Rule:** Write comments and doc comments as complete sentences with proper
punctuation. A complete sentence starts with a capital letter and ends with
a period (or other appropriate terminal punctuation).

**This applies to admonition bodies.** The text after `TODO:`, `FIXME:`,
`NOTE:`, `WARNING:`, `HACK:` must itself be a complete sentence — leading
capital letter and trailing period. The keyword casing is governed by
`CMT-01`; the body text is governed by this rule. Always flag admonition
bodies that omit the leading capital or trailing period, even if the
keyword is correct.

**Mechanical rubric you MUST apply to every standalone-line comment in scope
(a line whose only content after the indent is a `//`, `///`, `//!`, `#`,
`"""`, or similar comment marker):**

1. Is the first character of the comment body lowercase? → violation of `CMT-01`.
2. Does the comment body end with a period (or `?` / `!`)? → if not, violation of `CMT-02`.
3. Apply this rubric even to short comments (three or four words). The only
   comments exempt from the leading-capital / trailing-period requirement
   are trailing end-of-line comments covered by Exception 2 below — not
   standalone comments, regardless of how short or casual they look.

Examples of standalone comments that MUST be flagged:
- `// we need at least 16 bytes in each segment for CAI` → lowercase "we", no period.
- `// check if this is a CAI JUMBF block` → lowercase "check", no period.
- `// create dummy JUMBF seg` → lowercase "create", no period.

**Exceptions:**

1. **Titles and captions** (section headings in docs, short field descriptions
   in structs) may omit the trailing period if they are not full sentences.
   Still use sentence case.

2. **Short descriptive fragments** that label a data structure, a variable's
   contents, or a specific value may be sentence fragments. They do **not**
   require a leading capital or trailing period. Acronym casing (`CMT-03`)
   and informal-abbreviation rules (`CMT-04`) still apply, as does grammar
   (`CMT-05`).

   **Scope of this exception, narrow and strict:** this applies ONLY to
   trailing end-of-line comments attached to a literal, struct field, or
   single statement (e.g., `C2PA_MARKER, // CAI UUID signature`). A comment
   that occupies its own line — even a very short one like `// check length`
   or `// we need 16 bytes for CAI` — is NOT covered by this exception and
   must obey `CMT-02` (leading capital, trailing period) and `CMT-01`
   (sentence case). If you see a standalone-line comment that starts
   lowercase or lacks terminal punctuation, flag it.

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

### `CMT-03` — Use correct capitalization for acronyms

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

### `CMT-04` — Spell out informal word abbreviations

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
  See `CMT-03` for casing.
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

### `CMT-05` — Basic grammar and typos

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
- Regional spelling differences (US vs UK; "color" vs "colour"). For
  published Rust crates, `GEN-04` separately requires American English.
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

### `CMT-06` — Trailing comments that describe behavior go on their own line

**Severity:** suggestion

**Rule:** Trailing end-of-line comments are reserved for **short noun-phrase
fragments that label the adjacent value, field, or literal**. If the trailing
comment instead describes **what the statement does** — the action or
behavior of that line of code — move it to its own line above the statement
and rewrite it as a complete sentence (`CMT-02`: leading capital, trailing
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

**This does NOT override `CMT-02` Exception 2.** Short fragments that label
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

### `CMT-07` — Wrap comment prose at 80 characters

**Severity:** suggestion

**Rule:** Wrap the prose content of comments and doc comments so that no
line exceeds 80 characters of total column width (counting the leading
indentation and the comment marker). When a comment runs longer, break
it across multiple lines at a natural word boundary.

This applies to all standalone-line comments (`//`, `///`, `//!`, `#`,
`"""`, etc.). It does not apply to code — only to the human-readable
prose inside comments.

**Mechanical rubric you MUST apply to every standalone comment line in
scope:**

1. Count the column width of the full source line as it appears in the
   file: leading indentation + comment marker (`//`, `///`, `//!`, `#`)
   + the single space after the marker + the prose text. When the prompt
   renders lines with a `NNNNN: ` line-number prefix, that prefix is NOT
   part of the source — do not count it.
2. If the width is greater than 80, flag the line unless one of the
   exceptions below applies. Do this even when the line is only slightly
   over (81, 85, 90, 100 are all violations).
3. Provide a concrete re-wrap as the `suggestion`, broken at a natural
   word boundary, preserving the original indentation and comment marker
   on every continuation line. Aim for each wrapped line to be as close
   to 80 columns as possible without exceeding it.

A line that is ~100 columns, contains no URLs or long identifiers, and
consists of ordinary prose is always a violation. Do not skip it.

**Exceptions:**

- **Unbreakable tokens.** If the overflow is caused by a single token
  that cannot be broken — a URL, an intra-doc link, a long identifier,
  or a line inside a fenced code block — leave the line alone.
- **Trailing end-of-line comments** that label a value (`CMT-02`
  Exception 2). These follow the adjacent code's column; do not rewrap
  them onto the next line.
- **Tables, ASCII art, or pre-formatted content** inside doc comments
  where wrapping would break the layout.

**Good:**
```rust
// Store the identifier for later comparison against subsequent
// segments so the reader can detect duplicates.
/// Returns the XMP metadata block if the file contains one; otherwise
/// returns `None` without reading the rest of the stream.
```

**Bad:**
```rust
// Store the identifier for later comparison against subsequent segments so the reader can detect duplicates.
/// Returns the XMP metadata block if the file contains one; otherwise returns `None` without reading the rest of the stream.
```

---

## Vertical whitespace (`WS`)

### `WS-01` — Use vertical whitespace intentionally

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

1. If a contiguous block inside a function or branch contains roughly 5 or
   more statement lines with no blank line between them, and you can identify
   at least one natural conceptual boundary (e.g., "parse input" → "do the
   work" → "build result"), flag it and suggest a blank-line break at that
   boundary. Prefer flagging the first (outermost) offending block rather
   than every nested one. Multi-line expressions (e.g., a builder chain, an
   `Some(...)`-wrapped result, or a `match` arm body) count as a single
   "statement line" for this purpose — what matters is the visual run of
   back-to-back code without breathing room. Apply this test to **every**
   offending run in the diff, including short `if`/`else` branches whose
   body happens to be 5–8 lines long. Do not skip a run just because it's
   inside a larger region where you already flagged another `WS-01` issue.

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

## Git & PR title conventions (`GIT`)

### `GIT-01` — Use Conventional Commits format for commit messages and PR titles

**Severity:** info

**Rule:** When code comments reference commits, issues, or PRs, be specific.
When writing commit messages and PR titles (visible in `git log` blocks in
docs), use the Conventional Commits format: `type(scope): description`.

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`.

The first word of the description after the `type:` or `type(scope):`
prefix must be capitalized (`CMT-01`). PR titles must not end with a
period (`CMT-02` Exception 3).

**Good:**
```
feat(parser): Add support for multi-line string literals
fix(sdk): Handle empty input without panicking
```

**Bad:**
```
fixed stuff
update code
perf: optimize signing passes
```

**Reference:** <https://howicode.ericscouten.com/git/>

---

## Testing (`TEST`)

### `TEST-01` — Invest in test coverage

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

## Rust documentation rules

The rule groups that follow — `GEN`, `SUM`, `FN`, `TY`, `MOD`, `MD`, `PR`,
`AP` — apply **only to Rust source files** (`.rs`). They are synthesized
from RFC 505, RFC 1574, the Rust API Guidelines, and the conventions
followed by the Rust standard library.

When in doubt on a style point not covered here, the operating principle
is: **do what std does.** Read the rustdoc output for a comparable item in
std and follow its shape.

---

## General Rust rules (`GEN`)

### `GEN-01` — Public items must be documented **(Required)**

Every public item (crate, module, trait, struct, enum, function, method,
macro, type alias, constant, static) must have a doc comment.

- Mark intentionally undocumented items with `#[doc(hidden)]`.
- Enable `#![warn(missing_docs)]` at the crate root for enforcement.

### `GEN-02` — Use `///` for items, `//!` for enclosing scope **(Required)**

- `///` documents the item that follows it.
- `//!` documents the enclosing item — use **only** at the top of a crate
  root or module file.
- Do not use `//!` to document sibling items.

### `GEN-03` — Use line doc comments, not block doc comments **(Recommended)**

Prefer `///` / `//!` over `/** */` / `/*! */`. Block doc comments are
permitted (e.g., for accessibility reasons) but line doc comments are the
std convention.

### `GEN-04` — American English **(Required for public crates)**

Use American English spelling, grammar, and punctuation (e.g., "color" not
"colour", "synchronize" not "synchronise").

### `GEN-05` — Full sentences with proper punctuation **(Required)**

Doc comments — including the summary line — must be complete sentences
ending with a period (or `?` / `!` where appropriate). Prefer full
sentences over fragments. See `CMT-02` for the mechanical rubric; this
rule extends the same requirement to Rust doc comments specifically.

---

## Summary line (`SUM`)

The summary line is the first line of any doc comment. It is extracted by
rustdoc for module listings and search results.

### `SUM-01` — Single-sentence summary on the first line **(Required)**

The first line must be a single short sentence summarizing the item. It
must be followed by a blank doc-comment line (`///` with nothing after it)
before any further content.

```rust
/// Returns the number of elements in the vector.
///
/// More detail here if needed...
```

### `SUM-02` — Third-person singular present indicative **(Required)**

Write "Returns", "Constructs", "Converts", "Computes" — not "Return",
"Construct", or "Will return".

- ✅ `/// Returns the length of the string.`
- ❌ `/// Return the length of the string.`
- ❌ `/// This function will return the length.`

### `SUM-03` — Keep the summary concise **(Recommended)**

Target: under ~100 characters. If the summary wraps to a second line in
source, it is probably too long for the rustdoc summary view.

### `SUM-04` — Do not restate the signature **(Recommended)**

Type information is rendered by rustdoc and linked automatically. Do not
write "Takes a `&str` and returns a `usize`" — describe behavior, not types.

---

## Function & method documentation (`FN`)

### `FN-01` — Required structure **(Required)**

Function docs must follow this order when sections are present:

1. Summary line (per `SUM-01`)
2. Blank line
3. Extended description (optional but recommended for non-trivial functions)
4. `# Panics` (if applicable — see `FN-04`)
5. `# Errors` (if applicable — see `FN-05`)
6. `# Safety` (if applicable — see `FN-06`)
7. `# Examples` (per `FN-07`)

Other sections recognized by convention: `# Aborts`, `# Undefined Behavior`.
Use them only when applicable.

### `FN-02` — Use top-level `#` headings for sections **(Required)**

Section headings must be H1 (`#`), not H2 (`##`) or bold text.

```rust
/// # Panics
```

### `FN-03` — Use plural section names **(Required)**

Always use the plural form, even with only one example or one panic
condition: `# Examples`, `# Panics`, `# Errors`. This is for tooling
consistency.

### `FN-04` — Document panics **(Required)**

Any function that can panic in a way observable by the caller must have a
`# Panics` section listing the panic conditions.

```rust
/// # Panics
///
/// Panics if `index` is out of bounds.
```

Functions that only panic via OOM or similar global conditions do not
require this section.

### `FN-05` — Document errors **(Required for functions returning `Result`)**

Any function returning `Result<_, E>` must have an `# Errors` section
describing when each error variant can occur. This applies to trait
methods whose implementations may return errors.

```rust
/// # Errors
///
/// Returns `Err(ParseIntError)` if the string does not contain a valid integer.
```

### `FN-06` — Document safety invariants **(Required for `unsafe fn`)**

Every `unsafe fn` must have a `# Safety` section stating the invariants
callers must uphold.

```rust
/// # Safety
///
/// `ptr` must be non-null and point to a valid, initialized `T`.
/// The caller must ensure no other references to `*ptr` exist for the duration of the call.
```

### `FN-07` — Provide examples **(Required for public items, within reason)**

Every public function should have at least one `# Examples` section
containing a runnable doctest.

Exceptions where a linked example elsewhere is sufficient:
- Trivial getters/setters whose behavior is obvious from the signature.
- Functions that are one of many similar methods on a type, where an
  example on the type or a sibling method is linked.

Examples should demonstrate **why** and **how**, not just syntactic usage.
Prefer examples that exercise the function in a realistic context.

### `FN-08` — Doctest style **(Recommended)**

- Default language for fenced blocks is Rust; the `rust` tag may be omitted.
- Tag non-Rust blocks explicitly (```` ```text ````, ```` ```ignore ````,
  ```` ```compile_fail ````) so rustdoc does not try to test them.
- Use `assert_eq!` / `assert!` in examples to verify behavior.
- Hide setup/boilerplate with `#` prefixes.

### `FN-09` — Fallible example pattern **(Recommended)**

Examples that use `?` should wrap in `fn main() -> Result<…>` with hidden
lines:

```rust
/// ```
/// # use std::error::Error;
/// #
/// # fn main() -> Result<(), Box<dyn Error>> {
/// let parsed = "42".parse::<i32>()?;
/// assert_eq!(parsed, 42);
/// # Ok(())
/// # }
/// ```
```

### `FN-10` — Do not document type-signature information in prose **(Recommended)**

Avoid prose like "This function takes two arguments, a `&str` and a
`usize`". Describe semantics, not types.

---

## Type documentation (`TY`)

Covers `struct`, `enum`, `union`, trait, and type alias definitions.

### `TY-01` — Summary describes the type's purpose **(Required)**

The summary line should describe what the type represents, not its literal
structure.

- ✅ `/// A growable, heap-allocated sequence of elements.`
- ❌ `/// A struct containing a pointer, length, and capacity.`

### `TY-02` — Document construction and invariants **(Recommended)**

For non-trivial types, document:
- How instances are typically constructed.
- Invariants the type maintains.
- Performance characteristics (Big-O) where relevant.
- `Drop` behavior if it is non-obvious.

### `TY-03` — Document enum variants individually **(Required)**

Each public enum variant must have its own `///` doc comment. Do not
document variants collectively in the enum-level comment.

```rust
/// A parsed HTTP method.
pub enum Method {
    /// The HTTP `GET` method.
    Get,
    /// The HTTP `POST` method.
    Post,
}
```

### `TY-04` — Document public struct fields **(Required for public fields)**

Public fields on a struct must have `///` doc comments. Private fields may
have comments but are not required to.

### `TY-05` — Traits document required vs. provided methods **(Recommended)**

Trait-level docs should clarify which methods implementors must provide and
which have default implementations. Each method in the trait still follows
the function rules in the `FN` section.

---

## Module & crate documentation (`MOD`)

### `MOD-01` — Crate root has `//!` documentation **(Required)**

The crate root (`lib.rs` or `main.rs`) must begin with a `//!` doc comment
describing:
- What the crate does (summary line).
- Its primary use cases.
- At least one top-level usage example.

### `MOD-02` — Modules have `//!` documentation **(Required)**

Every public module must have a `//!` comment at the top describing its
role and the kinds of items it contains.

### `MOD-03` — Front-page structure for non-trivial crates **(Recommended)**

For crates beyond a single file, the crate-root doc should include:
- A one-paragraph description of what the crate does and why you would use it.
- A "Getting started" or quickstart example.
- Links to the primary types/modules.
- Feature flag documentation (if any).

---

## Markdown & formatting (`MD`)

### `MD-01` — Inline code uses backticks **(Required)**

Wrap identifiers, types, values, and code fragments in single backticks:
`` `Vec<T>` ``, `` `None` ``, `` `self` ``.

### `MD-02` — Use intra-doc links **(Required)**

Link to other items in the current crate or its dependencies using
intra-doc link syntax: `` [`Vec`] ``, `` [`Option::Some`] ``,
`[name](path::to::Item)`.

Do not use hardcoded URLs to docs.rs or doc.rust-lang.org for items you
can link with intra-doc syntax.

### `MD-03` — Link all the things **(Recommended)**

When a doc references another type, function, module, or external resource,
it should be linked. This applies even to common std types on first mention
in a long doc block.

### `MD-04` — Reference-style links for readability **(Recommended)**

For long URLs or links referenced multiple times, use reference-style
links and place definitions at the bottom of the doc comment:

```rust
/// See [the Rust website] for more.
///
/// [the Rust website]: https://www.rust-lang.org
```

### `MD-05` — Fenced code blocks, not indented **(Required)**

Use triple-backtick fences. Do not use 4-space indented code blocks —
rustdoc treats them inconsistently and they cannot carry language tags.

---

## Prose style for Rust docs (`PR`)

### `PR-01` — Third person, present tense **(Required)**

Consistent with `SUM-02`, use third-person present indicative throughout,
not just in the summary line. Avoid "we", "you", and "I" in reference
documentation. ("You" is acceptable in tutorial-style crate-level docs.)

### `PR-02` — Active voice **(Recommended)**

Prefer active voice. "The function returns X" over "X is returned by the
function".

### `PR-03` — Avoid "simply", "just", "obviously", "of course" **(Recommended)**

These words alienate readers who do not find the material obvious. Omit
them.

### `PR-04` — Define terminology on first use **(Recommended)**

When introducing a term specific to the crate or domain, define it or link
to its definition. Do not assume familiarity.

### `PR-05` — Heading capitalization **(Recommended)**

Capitalize the first word and all significant words in a heading. Do not
capitalize:
- Articles (a, an, the) unless first.
- Coordinating conjunctions (and, but, for, or, nor).
- Short prepositions (of, in, to, by) unless first or last.
- Function, method, or crate names (keep their natural casing in backticks).

---

## Anti-patterns the bot should flag (`AP`)

Quick-reference list of common mistakes in Rust doc comments:

- `AP-01`: Summary line in imperative mood ("Return the…") → should be
  indicative ("Returns the…"). See `SUM-02`.
- `AP-02`: Missing blank line between summary and body → rustdoc will
  merge them. See `SUM-01`.
- `AP-03`: `## Examples` instead of `# Examples` → violates `FN-02`.
- `AP-04`: `# Example` (singular) → violates `FN-03`.
- `AP-05`: Missing `# Safety` on `unsafe fn` → violates `FN-06`.
- `AP-06`: Missing `# Errors` on `Result`-returning function → violates
  `FN-05`.
- `AP-07`: Missing `# Panics` on a function containing `panic!`, `unwrap`,
  `expect`, indexing, or arithmetic that may overflow → likely violates
  `FN-04`.
- `AP-08`: Hardcoded `https://doc.rust-lang.org/...` URL where intra-doc
  link would work → violates `MD-02`.
- `AP-09`: Public item with no doc comment → violates `GEN-01`.
- `AP-10`: Prose restating the type signature → violates `SUM-04` /
  `FN-10`.
- `AP-11`: Undocumented public enum variant or struct field → violates
  `TY-03` / `TY-04`.
- `AP-12`: Non-Rust code block without a language tag (rustdoc will
  attempt to test it) → violates `FN-08`.

---

## Scope limitations

**Only comment on:**
- Lines that are additions in the diff (lines starting with `+`, not the
  `+++` header)
- Code in source files (`.rs`, `.py`, `.ts`, `.js`, `.go`, `.md`, etc.)

**Do NOT comment on:**
- Auto-generated files (e.g., `Cargo.lock`, `package-lock.json`, `*.pb.go`,
  any file with a `// Code generated` header)
- Build artifacts, vendored dependencies
- Files listed in `.botignore` at the repo root
- Binary files
- Trivial changes (version bumps in manifest files, adding a single import)
- Lines that were not changed in this PR (context lines, deletion lines)

The Rust documentation rule groups (`GEN`, `SUM`, `FN`, `TY`, `MOD`, `MD`,
`PR`, `AP`) apply **only to `.rs` files**. Do not flag those rules on
other languages.

---

## References

- [RFC 505: API Comment Conventions](https://rust-lang.github.io/rfcs/0505-api-comment-conventions.html)
- [RFC 1574: More API Documentation Conventions](https://rust-lang.github.io/rfcs/1574-more-api-documentation-conventions.html)
- [Rust API Guidelines — Documentation](https://rust-lang.github.io/api-guidelines/documentation.html)
- [The rustdoc book — How to write documentation](https://doc.rust-lang.org/rustdoc/how-to-write-documentation.html)
- Eric Scouten's personal style guide: <https://howicode.ericscouten.com/>
