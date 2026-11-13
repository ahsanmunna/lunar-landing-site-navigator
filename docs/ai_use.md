# Use of AI

## Tools
- **Google Antigravity** (AI coding agent, Pro plan): wrote the code. The model(s) used inside it were whatever the
  tool selected; versions were not recorded.
- **Claude** (Anthropic, claude.ai chat): technical supervisor and reviewer.

## What each tool did
**Antigravity:** the Python engine (`lunar_engine/`), the data-pack builder, the region digitizer, tests, the static
web app (`web/`) and documentation drafts, from task briefs written by Claude and approved by the project owner.
**Claude:** wrote the task briefs; recommended the static-web-app architecture; reviewed every phase's code and
reports; ran independent checks (DEM orientation against known crater floors, recomputed horizons from the 160 m DEM
copy, measured light-time and aberration size with SPICE, compared region picks with box positions); and drafted
documentation text.

## Data the tools worked on
NASA LOLA 20 m south polar DEM (PGDA) and NAIF SPICE kernels, via the project's own scripts. Neither tool had
access to anything else.

## Prompts
- Every Antigravity prompt, verbatim, with a summary of changes: `docs/ai_log.md`.
- Claude: the structured review requests for Phase 1 and Phase 2 are in `docs/claude_review_prompts.md`. Other
  conversation messages (questions, screenshots, uploaded zips) are not reproduced here.

## Human verification
The owner ran every test and every data rebuild on their own machine, picked the nine region centres in
`scripts/pick_regions.py`, and decided what to accept. Automated tests are listed in `docs/validation.md`.

## AI mistakes that were caught and corrected
1. Antigravity first filled `data_src/regions.json` with coordinates from its own memory and labelled them as hand
   digitized. Review caught this; the file was replaced by picks made in `scripts/pick_regions.py`, and the build now
   refuses regions without a `picked_by` and `picked_utc` stamp.
2. The original script hard-coded Earth's and the Sun's angular radii; they are now computed from distance. Antigravity
   also reported a wrong Earth angular-radius range (0.938-0.963 deg); the SPICE-computed range is 0.898-1.022 deg.
3. The web page claimed the light-time offset was under 0.001 deg; measured with SPICE it is 0.006 deg for the Sun and
   0.0002 deg for Earth. The text was corrected.
4. Documentation drafts contained unverified claims (lazy loading, fixture coverage); these were corrected.