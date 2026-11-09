# Cleanup Checklist — Phases 3–4

This document tracks files and code that should be removed after specific milestones.

---

## Phase 3 Cleanup (After Angular Components ✅)

**Trigger:** Angular UI achieves pixel-perfect parity with legacy UI and sign-off is given.

### Files to Delete from Repository

#### Legacy Static UI
- [ ] `static/index.html` (4,900+ lines)
  - **Reason:** Replaced by Angular app (frontend/dist/stox/browser)
  - **Verification:** Screenshot comparison shows 100% parity
  - **Backup:** Git history preserves it forever; can restore with `git show HEAD~N:static/index.html`

#### Dead Code in static/index.html (before deletion)

These are documented for reference, but deletion will remove them:

- [ ] Lines ~4047–4202: Duplicate add/search/remove symbol functions
  - **Reason:** Already ported to Angular in Phase 3
  - **Status:** Dead copy, never used

- [ ] Lines ~4804–4875: `exportAsHTML` function and `.btn-export` CSS
  - **Reason:** Export feature never used
  - **Status:** Dead code (~200 LOC)

- [ ] Hard-coded `curated` long-term table (33 symbols)
  - **Reason:** Effectively dead, server-side signal is authoritative
  - **Status:** Contradicts server data

- [ ] Unused CSS classes:
  - `.pct-result`, `.pct-rr`, `.pill-already-added`
  - `--accent-teal` (unused variable)
  - **Reason:** Not used in Angular UI

- [ ] Undefined CSS variables (legacy bug):
  - `--accent-rose` (5 uses in removed code)
  - **Reason:** Never defined, causes CSS errors

- [ ] Latent double-listener bug on Add→Remove button swap
  - **Reason:** Angular avoids this with proper event handling

#### Temporary Test/Patch Scripts (Outside Repo)

These are utility scripts created during development:

- [ ] `C:\Users\tdewangan\AppData\Local\Temp\stox_patch\patch_pct2.py`
  - **Reason:** One-off HTML patching script, no longer needed
  - **Status:** Outdated after Angular migration

- [ ] `C:\Users\tdewangan\AppData\Local\Temp\stox_patch\*.py` (all patch scripts)
  - **Reason:** All patches incorporated; no longer needed
  - **Action:** Safe to delete (outside git)

#### JavaScript Test Harnesses (Outside Repo)

- [ ] `C:\Users\tdewangan\AppData\Local\Temp\stox_dom_check.js`
  - **Reason:** jsdom tests now in Vitest
  - **Status:** Reference for migration, can be deleted

- [ ] `C:\Users\tdewangan\AppData\Local\Temp\stox_calc_check.js`
  - **Reason:** Calculator tests now in Vitest
  - **Status:** Reference for migration, can be deleted

- [ ] `%TEMP%\stox_dom_path.txt`
  - **Reason:** Temporary path tracker for jsdom
  - **Status:** Can be deleted

---

## Phase 4 Cleanup (After Heroku Deployment ✓)

**Trigger:** App deployed to Heroku and verified working.

### Files to Delete from Repository

#### Legacy Dashboard Server (Optional)

- [ ] `dashboard_server.py` (if using pure Starlette)
  - **Reason:** Replaced by `api/main.py` via `uvicorn`
  - **Decision:** TBD (keep for local development, remove for cloud?)
  - **Recommendation:** Keep in repo for backward compatibility, but document it's deprecated

#### Optional: Temporary Configuration Files

- [ ] `.gitignore` entries for temp files (if added during development)
  - **Reason:** Clean up after development is done

### Optional: Documentation

- [ ] `PHASE_3_COMPONENTS.md`
  - **Decision:** Keep as reference (useful for future maintenance)
  - **Archive:** Move to `docs/ARCHIVED_PHASE_3_PLAN.md` if needed

- [ ] `SESSION_SUMMARY.md`
  - **Decision:** Keep in history, move to `docs/SESSION_SUMMARY_2026_11_10.md`

---

## Never Delete (Preserve Forever)

- [ ] `.git/` directory
  - All history is valuable (recover anything with git checkout)

- [ ] `static/index.html` (in git history)
  - Will be deleted from working tree, but git preserves it
  - Recovery: `git show HEAD~N:static/index.html > static/index.html`

- [ ] Test files (`tests/test_*.py`)
  - Keep all tests

- [ ] `tools/` directory (all agents, analysis engines)
  - Core business logic, never delete

- [ ] `storage/` directory
  - Database management, never delete

---

## Execution Plan

### Phase 3 Cleanup (Day 1 of Phase 4)

```bash
# Verify parity with legacy UI (screenshots)
# Get sign-off from user

# Delete static/index.html from working tree
git rm static/index.html

# Commit
git commit -m "Remove legacy static/index.html after Angular parity verified

- Static UI fully ported to Angular 22
- Screenshot comparison confirms pixel-perfect parity
- Angular app deployed to frontend/dist/stox/browser
- Git history preserves full legacy UI if needed (git show HEAD~N:static/index.html)"

# Manual cleanup (outside repo)
rm -r "C:\Users\tdewangan\AppData\Local\Temp\stox_patch\"
rm -f "C:\Users\tdewangan\AppData\Local\Temp\stox_*.js"
rm -f "%TEMP%\stox_dom_path.txt"
```

### Phase 4 Cleanup (Deployment Day)

```bash
# Optionally: archive documentation
mkdir -p docs/archived
mv SESSION_SUMMARY.md docs/archived/SESSION_SUMMARY_2026_11_10.md
mv PHASE_3_COMPONENTS.md docs/archived/PHASE_3_COMPONENTS_2026_11_10.md

# Keep QUICK_START.md and current documentation

# Final commit
git commit -m "Archive Phase 3 planning docs after Heroku deployment"
```

---

## Definition of Done

### Phase 3 Cleanup ✓
- [ ] Angular UI achieves 100% visual parity with legacy
- [ ] Screenshot comparison completed (Playwright)
- [ ] User sign-off received
- [ ] `static/index.html` deleted from working tree
- [ ] Temporary patch/test scripts removed (outside repo)
- [ ] Commit message explains deletion
- [ ] All 93 tests still passing

### Phase 4 Cleanup ✓
- [ ] App successfully deployed to Heroku
- [ ] Production app verified working
- [ ] Documentation archived (optional)
- [ ] Final cleanup commit created
- [ ] README updated with production URL

---

## Risk Mitigation

### Rollback Plan

If something goes wrong after deletion:

```bash
# Restore static/index.html from git history
git checkout HEAD~1:static/index.html > static/index.html
git add static/index.html
git commit -m "Rollback: restore legacy static/index.html"
```

### Verification Before Deletion

**Checklist before `git rm static/index.html`:**

- [ ] Angular build runs without errors: `npm run build:prod`
- [ ] Build output at `frontend/dist/stox/browser/` exists
- [ ] Index.html copied to build output
- [ ] Starlette app configured to serve static SPA
- [ ] Local test: `ng serve` and `python dashboard_server.py` both work
- [ ] WebSocket broadcast working
- [ ] All API endpoints functional
- [ ] Live price updates working
- [ ] All 93 tests passing
- [ ] Side-by-side screenshot comparison done
- [ ] Parity verified by user

---

## Files Created This Session (Safe to Keep)

- ✅ `api/` directory (Phase 1, keep)
- ✅ `frontend/` directory (Phase 2, keep)
- ✅ `tools/events_bus.py` (Phase 1, keep)
- ✅ `SESSION_SUMMARY.md` (documentation, keep or archive)
- ✅ `QUICK_START.md` (documentation, keep)
- ✅ `PHASE_3_COMPONENTS.md` (checklist, archive after Phase 3)
- ✅ `CLEANUP_CHECKLIST.md` (this file, keep or archive)

---

## Summary Table

| File/Code | Lifecycle | Status | Action |
|-----------|-----------|--------|--------|
| static/index.html | Legacy | ✅ Ready | Delete after Phase 3 parity |
| Patch scripts | Temp | ✅ Done | Delete from %TEMP% |
| jsdom harnesses | Temp | ✅ Done | Delete from %TEMP% |
| SESSION_SUMMARY.md | Doc | ✅ Keep | Archive after Phase 4 |
| PHASE_3_COMPONENTS.md | Checklist | ✅ Keep | Archive after Phase 4 |
| QUICK_START.md | Doc | ✅ Keep | Keep forever |
| api/ | Core | ✅ Keep | Keep forever |
| frontend/ | Core | ✅ Keep | Keep forever |
| tools/events_bus.py | Core | ✅ Keep | Keep forever |
| tests/ | Testing | ✅ Keep | Keep forever |

---

## Notes for Next Sessions

1. **Before deleting static/index.html:**
   - Make sure user has verified parity
   - Document the decision in commit message
   - Ensure git history is clean

2. **Temporary files outside repo:**
   - Safe to delete anytime (not tracked in git)
   - No impact on versioning

3. **Rollback is easy:**
   - `git checkout` can restore any deleted file
   - Commit message should explain why deletion happened

4. **Document the process:**
   - Keep commit messages clear
   - Include "After Phase X complete" in message
   - Reference this checklist in commits
