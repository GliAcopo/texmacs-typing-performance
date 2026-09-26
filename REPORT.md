# Faster editing of long documents in GNU TeXmacs

Technical report of a performance investigation of TeXmacs 2.1.4 (Debian/Ubuntu package
`1:2.1.4+ds-3`) and of the resulting patch series for upstream TeXmacs.
Written in September 2026.

## 1. The problem

Editing a long document is slow in TeXmacs, and it is slowest where one would expect
it: with the cursor near the **start** of the document (everything needs to be redrawn).
With two real sets of lecture notes
(A: ~2,100 paragraphs, many formulas; B: ~3,500 paragraphs with figures and footnotes, both
in continuous "papyrus" page mode), every keystroke cost 40–110 ms of CPU. At normal typing
speed, TeXmacs fell behind the keyboard: the screen caught up up to 2 s after the last key.

## 2. Why it happens

TeXmacs retypesets incrementally: when one paragraph changes, only that paragraph is laid
out again. But every typesetting pass still **walks all paragraphs of the document** to
rebuild the global structure, and for each paragraph it:

1. re-applies the paragraph's cached effect on the typesetting environment (counters,
   macros, …);
2. merges its lines into the global stack of lines and recomputes the vertical spacing
   ("shove") between the last line of the paragraph and the first line of the next one;
3. outside paper mode, merges the lines of the paragraph into one stack box again;
4. afterwards, repositions every box of the document and logs which screen areas moved;
5. and when the document contains floats (figures, footnotes), hands every single line to
   the page breaker, which rebuilds its tables for thousands of items.

Each step is cheap for one paragraph, but multiplied by a few thousand paragraphs it gave
the 40–110 ms per key. Almost all of this work produces exactly the same result as in the
previous pass. Additional costs came from outside the typesetter:

* `typeset_prepare` rewrote the default environment with the full style environment
  (thousands of variables) at every pass and at every `get-env` call from Scheme;
* after each pause in typing, `update_menus` re-derived the properties of every macro of the
  style (`drd_update` → `heuristic_init`, ~36 ms), although nothing had changed;
* redrawing collected rectangles with a quadratic list concatenation;
* two Scheme predicates evaluated after every change converted the whole document root
  into a list.

The whole-document walk happens wherever the cursor is; in the measurements, typing near the
start of the document was nevertheless clearly the most expensive case (e.g. 60 ms vs 41 ms
per key on A). The reason for that gap was not investigated further, since the patches
remove most of the walk and make both cases cost the same.

## 3. How it was measured

* **Build with symbols**: the Debian source package was rebuilt with `-g -O2
  -fno-omit-frame-pointer` (no install needed, run from the build tree, original package
  kept as a snapshot for rollback).
* **Profiling**: `perf` was not available (kernel restrictions), so a "poor man's
  profiler" was used: TeXmacs under gdb, interrupted every few ms while typing, with the
  collapsed stacks aggregated by a small script.
* **Benchmark harness**: TeXmacs on a private X server (Xvfb, 2560×1600), real X key events
  injected with XTest at a fixed rate (60 or 180 ms per key), on scratch copies of the
  documents and of the configuration directory. A temporary, environment-gated
  instrumentation in the binary logged the duration of every update cycle and of the phases
  of `apply_changes` and of the typesetter; it is not part of the upstream patches.
* **Build-independent measure** (for upstream trunk, which has no instrumentation): CPU time
  of the TeXmacs process per key, and the time it keeps working after the last key.

## 4. What was changed

Ten small commits, each compiling on its own (upstream `svn_mirror` as of 2026-09-24 and the
`development` branch; the touched files are identical in both):

| # | Commit | Idea |
|---|---|---|
| 1 | avoid quadratic accumulation of rectangles in `box_rep::redraw` | prepend instead of `l= ll * l` (which copies both lists) |
| 2 | compare inverse paths without reversing them in composite finalize | `path_less (reverse (a), reverse (b))` computed in place, no allocations |
| 3 | skip repositioning of stacks and phrases which did not move | boxes are immutable: a stack placed at the same absolute position for the same change log has nothing to log |
| 4 | memoize the shove between successive paragraphs in `merge_stack` | the spacing only depends on two immutable boxes and six border values; cached for two passes |
| 5 | cache the merged stack item of unchanged paragraphs | keep the item until the paragraph's lines are recomputed; bridges get a version number |
| 6 | replay blocks of unchanged paragraphs in `bridge_document` | the core change, see below |
| 7 | merge runs of lines into cached chunks when floats are present | the page breaker sees ~65 items instead of ~3,500 |
| 8 | cache the default environment patched with the preamble | recomputed only when the preamble changes; only variables with side effects are re-applied |
| 9 | skip `drd_update` when neither the drd nor the environment changed | a global stamp, incremented by every drd mutation, guards the cache |
| 10 | cheaper `tm-func?` and title/abstract proposal predicates (Scheme) | test label and arity directly; no list building |

**Block replay (commit 6).** Paragraphs are grouped into blocks. The first paragraph of a
block (the head) is processed as before. The combined effect of the others — the modified
last line of the stack, the appended lines, the stack border fields and the composition of
their environment patches — is recorded once and replayed in one step as long as every
paragraph of the block is the same bridge object with the same version and status, no
environment change is pending, and the head was merged into exactly the same line item as
when recording. Replaying is exact because, once the head is merged, the merging of the rest
of the block no longer depends on what precedes it. Block boundaries are derived from the
paragraph objects themselves (content defined), so inserting or deleting a paragraph (Return,
Backspace at the start of a paragraph) only disturbs the block where it happens.

The code follows the style of the surrounding sources (GNU-like, two spaces, a space before
argument lists, `/****…` section banners) and uses only TeXmacs containers (`hashmap`,
`array`), as the core never uses the STL.

## 5. Results

### TeXmacs 2.1.4 (Debian package) — before/after, same harness, medians of 3 runs

| scenario | CPU per key before → after | lag after the last key before → after |
|---|---|---|
| A, cursor at the top, 60 ms/key | 59.9 → 15.2 ms | 315 → 209 ms |
| A, cursor at the top, 180 ms/key | 67.7 → 15.4 ms | 323 → 206 ms |
| A, cursor at the end, 60 ms/key | 40.6 → 15.1 ms | 297 → 207 ms |
| A, text with Return | 166.0 → 88.4 ms | 2201 → 1161 ms |
| B, cursor at the top, 60 ms/key | 107.8 → 34.9 ms | 1966 → 211 ms |
| B, cursor at the top, 180 ms/key | 151.9 → 38.5 ms | 404 → 215 ms |
| B, cursor at the end, 60 ms/key | 51.0 → 15.3 ms | 368 → 213 ms |
| B, text with Return | 171.3 → 94.7 ms | 2586 → 1349 ms |

(~200 ms of every lag figure is the harness' idle detection.) After the last commit of the
series, A with the cursor at the top is at 14.5 ms/key, and the typesetting part of a key
with Return dropped from ~40 to 15–19 ms. The cost of a key no longer depends on where the
cursor is.

### Upstream trunk + series, and the videos

Measured by `bench/video.py`: two builds run side by side on their own X server
(1920×1080), the same key is sent to both at the same moment every 60 ms, after a warm-up
(so that fonts and images are loaded before recording). CPU time of the TeXmacs process per
key, and how long it keeps working after the last key (0.25 s resolution, floor 0.5 s):

| document (cursor near the start unless noted) | before | after | busy after last key |
|---|---|---|---|
| synthetic, 2,000 paragraphs (trunk) | 57.4 ms | 24.7 ms | 0.75 → ≤0.5 s |
| synthetic, 2,000 paragraphs, cursor at the end (trunk) | 56.0 ms | 22.1 ms | 0.75 → ≤0.5 s |
| synthetic, 3,500 paragraphs with floats (trunk) | 61.7 ms | 30.9 ms | 0.75 → ≤0.5 s |
| same, text with Return (trunk) | 83.3 ms | 36.2 ms | 2.25 → ≤0.5 s |
| synthetic, 2,000 paragraphs, **paper** page mode (trunk) | 63.0 ms | 62.4 ms | unchanged |
| notes A (2.1.4 package vs patched package) | 58.6 ms | 30.9 ms | ≤0.5 s both |
| notes B | 80.5 ms | 47.3 ms | 3.26 → 1.25 s |
| notes B, text with Return | 98.5 ms | 49.2 ms | 3.76 → 0.75 s |

In the videos, at the moment the last key is sent, the unpatched build is visibly behind
(e.g. about 25 characters on notes B) while the patched build is up to date.

**Paper mode is not improved**: with the default paginated page mode, the cost of a key
is dominated by something else (presumably the page breaking of the paper pager, not
profiled), and the series neither helps nor hurts there (verified identical output, see
below). The gains apply to the continuous ("papyrus") page mode.

These numbers include repainting, which the patches mostly do not change; the typesetting
part alone drops by 3–4× (section above).

## 6. Verification

* **Layout**: after a fixed sequence of edits (typing, Return, a new section near the top,
  math, Backspace, joining two paragraphs, a few new paragraphs followed by undo), the
  bounding rectangle of every paragraph was compared between the original and the patched
  build: identical on A and B (2.1.4) and on both synthetic documents (trunk), with one
  exception explained below.
* **Pixels**: after the same edits, both builds page through the document and the whole
  screen (text, toolbars, footer) is captured after each page: byte-identical screenshots
  on A (3 runs, 70 pages incl. the table of contents with all chapter/section numbers),
  B (41 pages), the two synthetic documents in continuous mode (61 pages each) and a
  synthetic document in **paper** mode (92 pages, two starting points). This also covers
  stale numbering, which the geometric check cannot see. For the 2.1.4 comparison the two
  packages were run in turn from the same installation path: TeXmacs shows slightly
  different toolbar states when the same build runs from different paths, which first
  looked like a behaviour change.
* **Scheme test suite** (`(run-all-tests)`, 178 tests before it stops): identical output with
  and without the series. One test, `image / simple link`, fails on unpatched trunk too.
* Each commit of the series compiles on its own on trunk.

**Known difference.** In a document with floats, the selection rectangles of a multi-line
paragraph can be a few hundredths of a pixel wider on the left (seen once: 4/256 px). A
multi-line selection inside a stack box extends to the left and right edges of that stack;
with commit 7 the enclosing stack is a chunk of lines instead of the page. Documents without
floats already behave like this in unpatched TeXmacs (the whole document is one stack).
Rendering is unaffected (screenshots identical).

## 7. What went well

* The biggest costs were found by profiling real typing, not guessed; each change was
  measured and verified on its own.
* All caches are exact (they reproduce what the original code computes), so the layout is
  unchanged; the checks cover geometry, pixels and the Scheme test suite.
* With the cursor at the top, typing is 3–4× cheaper, and TeXmacs keeps up with fast typing
  on documents where it used to lag by 2 s.

## 8. What was tried and went wrong (and what it taught)

* **Profiling tools**: `perf` was blocked by kernel settings; gdb backtraces were truncated at
  40 frames by TeXmacs' deeply recursive boxes → a custom collapsed-stack sampler.
* **The Scheme predicates** looked hot in early profiles, but making them cheaper did not
  change the median cost of a key (only the peaks after pauses); the real cost was in C++.
* **First version of the line chunks** shifted the whole layout of B by 4 pixels (1024
  units): the page breaker uses the extents of the first and last items for its corrections
  at the top and bottom of pages. Fixed by never merging those two items.
* **Fixed-size replay blocks** (every 32 paragraphs): Return shifted every following block,
  so all blocks were recorded again at each new paragraph. Fixed by content-defined
  boundaries.
* **Packaging**: the Ubuntu default link-time optimization produced a binary that crashed at
  start-up inside Qt (not investigated; the non-LTO builds are fine), and `xvfb-run` raced
  on a fixed display number during the documentation build.
* **Upstream builds**: Debian's Guile 3 patch no longer applies to upstream; upstream
  `development` only supports Guile 1.8; trunk bundles its own Guile 1.8 (`guile-texmacs`),
  which the GitHub mirror does not contain (fetched from Savannah SVN); trunk's man page
  target is broken and GCC 15 needs `-Wno-error=implicit-function-declaration` for Guile.
* **Test harness pitfalls**: an interrupted TeXmacs start leaves a boot lock which makes the
  next start wipe the settings and caches (the harness always works on copies); an autosave
  file blocks start-up on the recovery dialog; an empty configuration directory opens the
  Welcome document on top of the test document; comparing builds installed at different
  paths shows different toolbar states (TeXmacs keys some state on the installation path);
  RAM-backed `/tmp` filled up with document copies; the first video measurements were
  meaningless because the one-off decoding of images (15 s) and missing-font generation
  happened during recording and made both builds process the keys in a few big batches
  (fixed by a longer warm-up).

## 9. Risks

* **Stale caches** are the main risk: each cache is only correct if its validity check sees
  every relevant change. The replay cache (commit 6) is the most delicate one: it applies the
  environment changes of a block as one composed patch instead of one paragraph at a time.
  The saved "before" values are the same either way (`write_back` keeps the first value),
  and so are the final values; what differs is how often, and in which order, the `update`
  side effects of the variables run. Unpatched TeXmacs already applies the changes of each
  paragraph as one composed patch (`bridge_rep::typeset`, cached case), so the replay relies
  on the same assumption one level up.
* **Coverage**: two real documents and three synthetic ones, continuous and paper page
  modes (output verified identical in both; speed-ups only in continuous mode). Not tested:
  multi-column layouts, other styles, and interactive cursor/selection behaviour.
* **Skipped repositioning** (commit 3) relies on boxes being immutable after construction; a
  box type modified in place would show as a screen area not refreshed, not as wrong layout.
* **drd cache** (commit 9): a drd modified without going through `drd_info_rep`'s setters
  would not invalidate it.

## 10. Remaining work

* After Return, all lines below move and the whole window is redrawn glyph by glyph
  (200–400 ms at 2560×1600; unpatched: ~1.1 s). Scrolling the unchanged pixels instead of
  redrawing them would fix most of it.
* Paper (paginated) mode: the series does not speed it up; its per-key cost (~60 ms on a
  2,000-paragraph document) comes from elsewhere and deserves its own profiling.
* With images in view, a line wrap that shifts them costs a repaint of ~1.2 s (unpatched)
  or ~0.45 s (patched); the first display of the images costs ~15 s once per session.
* `update_menus` after each pause: ~17 ms of Scheme menu evaluation.
* One-off costs: first decoding of images, and failing `mktexpk` runs for a few missing fonts.
