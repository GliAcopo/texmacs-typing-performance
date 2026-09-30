# Follow-up: moving unchanged lines, removals, animations

Five more commits on top of the series (PR #112 follow-up, 2026-09-30). The first one fixes a bug in the series itself; the other four remove costs that remained. They are ordered so that you can stop after any of them: 1 is a bug fix, 2 and 3 are independent speed-ups, and 4 and 5 go together (5 needs 4) and are the only ones that change the layout (by less than half a pixel, see below).

**Base.** Like the rest of the series, the commits are on `development` (321af6a). The same five commits against trunk (r15747, git mirror 383a0d7) are attached to the Savannah patch as a follow-up. They differ in two places only: on trunk `shift_contents` also repaints the spell-error highlights (which `development` does not have), and the widget change is also made in the copy of the Qt plugin in `src/Plugins/Qt6`.

### 1. `release stale line boxes before collecting the areas to repaint` (bug fix for the series)

**Problem.** A phrase box logs its area for repainting from its destructor. Two caches of the series kept the lines of the previous pass alive:
- the previous generation of the shove memo lived until the next pass;
- the merged stack item of a paragraph survived when the paragraph became a single line.

A removed line was then erased only at the next edit. Reproduction: type a letter on a new line and delete it; part of the letter stays on the screen.

**Change.** Drop the previous shove generation once the paragraphs are typeset; clear the stack cache when the lines are recomputed; drop the previous generation of line chunks after use. All of this happens before `position_at` collects the areas.

**Why it is safe.** These caches now only drop references earlier. A box is never kept alive longer than on trunk.

### 2. `do not retypeset the whole rest of a document when a paragraph is removed`

**Problem.** When a removed paragraph had changed the environment (a section, a label, a numbered environment), `bridge_document_rep::notify_remove` marked all following paragraphs for retypesetting. Joining a paragraph with a heading cost 4.6 s on trunk in a 3,500-paragraph document.

**Change.** The next paragraph records the changes that the removed ones made at the previous pass. They are added to `ttt->old_patch` just before that paragraph is typeset (`edit_env_rep::removed_update`, which is `post_patch`, as in `local_update`). The usual comparison with the previous pass then retypesets the following paragraphs as long as the environment differs, and no further.

**Why it is safe.**
- `old_patch` holds, for each variable whose value differs, its value at the previous pass. The removed paragraphs' changes are exactly those values at the point where they were removed.
- Bridges that carry such changes are never replayed.
- Documents with an accumulator keep the old behaviour.
- Deleting a heading still renumbers everything after it.

### 3. `only advance and repaint the animations which are on the screen`

**Problem.** Once an animation (an animated gif in `<video>`) had been shown, the editor walked the whole box tree twice per frame, forever, even after the animation left the screen. A long document with one gif used 75% of a core while idle, and every key cost about 115 ms instead of 12.

**Change.**
- `anim_next` and `anim_invalid` take the visible rectangle and skip boxes outside it.
- Transformed and effect boxes don't cull their children by position, since their children are transformed or drawn beyond their extents, but they still skip everything when they are themselves invisible.
- `animate()` stops the timer when nothing visible animates.

### 4. `choose line chunk boundaries from the geometry of the lines`

**Problem.** Chunk boundaries hashed box addresses, so a full retypeset (new boxes) chose other chunks. Merging is exact wherever the boundaries fall, so this did not matter so far, but commit 5 rounds distances between chunks.

**Change.** Hash the extents of the line. Accept a boundary only after at least 16 lines, so that a common signature (full justified lines, empty lines) cannot cut chunks down to single lines.

### 5. `move the pixels of unchanged lines instead of redrawing them`

**Problem.** In continuous page mode, Return or joining two lines moves every line below the change, and the whole window below it is redrawn glyph by glyph: 450 ms of CPU per key at 2560×1600 on long notes, 1.4 s on a document with many figures.

**Change.**
- *Layout.* Distances between successive items of the body are rounded to the renderer's pixel. They change by less than half a pixel, and only in continuous mode; paper mode and printing do not use this. So everything below a change moves by a whole number of pixels.
- *Detection (`typesetter_rep::find_shift`).* The typesetter compares the items of the body with those of the previous pass by identity. It keeps the previous ones alive until the new body exists, so the addresses cannot have been reused, and releases them before `position_at`. When the last items are the same boxes, all moved by the same multiple of the pixel, it reports the band they covered. It does so only if nothing else is drawn there before or after the change:
  - no other item of the body (extents including ink);
  - no other part of the page (headers, footers, floats, notes, collected on the path from the root to the body);
  - no pattern as page background.
- *Screen.* The editor asks the widget to move the pixels of that band. The new message is `SLOT_SHIFT_CONTENTS`, implemented with `QPixmap::scroll` on the backing store; pending invalid regions in the band are moved along. The editor repaints:
  - the changed lines and the uncovered strip;
  - the edges of the band;
  - the overlays drawn over moved text (cursor, selections, highlights, environment boxes, loci, shown keys), at their old and new places.

**Conditions.**
- Qt only, outside paper mode, first typesetting pass, plain document background, not in graphics.
- It can be switched off with the preference `move unchanged lines` (default `on`). With it `off`, neither the rounding nor the moves happen, and the layout is exactly the one of trunk.

### Tests

**Oracle.** Real keys are sent on Xvfb (2560×1600, Qt 5). After each key the screen must equal a full repaint (`refresh-window`), and after marked keys also a full retypeset (`update-current-buffer`). This is `bench/shift-check.py` in https://github.com/GliAcopo/texmacs-typing-performance.

| check | result |
|---|---|
| 13 places in two sets of lecture notes (2,075 and 3,491 paragraphs; figures, floats, tables, theorems, math), 34 keys each: typing, Return, Backspace, joins, selection + Delete, math, undo, Page Down | 442/442 edits pixel-identical to a full repaint, 78/78 identical to a full retypeset (trunk: same) |
| deleting a numbered equation, a labelled subsection, undo | numbering updates exactly as after a full retypeset (trunk: same) |
| preference `move unchanged lines` off, same edits, then 40 pages (`verify-pixels.py`) | identical to trunk on both documents: 41/41 screenshots, identical box geometry |
| PDF export of both documents | identical to the series without these commits (299 and 495 pages) |
| gif shown, then scrolled away / back | stops advancing; resumes when visible again |

**CPU per key** (key press until idle, typesetting and repainting, 2560×1600, cursor near paragraph 900):

| key | lecture notes, trunk → series | notes with figures, trunk → series |
|---|---|---|
| Return | 700 → 90 ms | 1,450 → 95 ms |
| Backspace joining lines | 700 → 80 ms | 1,430 → 85 ms |
| Backspace joining with a heading | — | 4,700 → 85 ms |
| letter | 115 → 50 ms | 150 → 50 ms |
| idle with an animated gif shown earlier | 74% → 1.6% of a core | |

### Open points

- Commit 5 changes the continuous-mode layout by less than half a pixel per item, which the rest of the series carefully avoided. It is the price of moving pixels exactly, and the preference restores the trunk layout. If you'd rather not have it at all, stop after commit 3: each commit compiles and works on its own.
- Every commit was compiled on its own on `development` (with Qt 5; here only `src/Scheme/Guile` of `development` does not build, because it expects Guile 1.8 and only Guile 3 is installed; the series does not touch it). The tests above ran on trunk with Qt 5. The Qt 6 variant of the widget code was compiled, but not tested on screen.
