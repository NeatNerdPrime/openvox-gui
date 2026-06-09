---
name: release
description: Promote a completed SemVer pre-release train (e.g. 3.9.0-dev.N series or -beta.N) to a clean stable MAJOR.MINOR.PATCH version. Updates CHANGELOG as needed, creates/pushes the stable annotated tag, and prepares for (but does not auto-execute) the manual GitHub Release. Use inside openvox-gui tree when a dev cycle is ready for users. Implements the Release Process and Version Discipline from project AGENTS.md + global canon. Never auto-creates GitHub Releases.
argument-hint: optional target stable version or notes
---

# OpenVox GUI Release Skill (Project-Scoped)

This skill finalizes a pre-release development train into a user-facing stable SemVer release while preserving the "tag and push only for dev, separate deliberate releases" policy.

It complements the `/commit` skill (which handles rapid pre-release dev commits with tags like v3.9.0-dev.42) and the global pre-commit checklist.

**Core rules enforced (canonized across the estate in .grok/Agents.md, openvox-gui/AGENTS.md, ovox/README.md, bump-version.sh, CHANGELOG process notes, and skills):**
- SemVer + pre-releases: Stable releases are clean MAJOR.MINOR.PATCH (e.g. 3.9.0). Dev uses pre-release identifiers (3.9.0-dev.N, 3.9.0-beta.N, 3.9.0-rc.N).
- Every meaningful dev push uses /commit for pre-release bump + conventional commit + pre-release tag + branch+tag push.
- GitHub Releases are **never** automatic. They are manual only when a clean stable tag is "ready to ship" (on schedule).
- ovox CLI lockstep with GUI via root VERSION + bump script (since 3.7.3).
- Always pair dev work with full pre-commit (CHANGELOG, docs, bump, deploy).
- Lightweight pre-release tags for continuous testing/deployment; clean stable tags + manual GH Releases for high-signal user shipments.

## Prerequisites
- You must be inside the openvox-gui tree.
- A series of pre-release commits (via /commit) should have been made for the current train.
- Current state should be on main (default branch).
- The last tag should be a pre-release in the train you want to promote.

## Step-by-Step Procedure

1. **Confirm context and review the pre-release train**
   - Run `git rev-parse --show-toplevel` and verify openvox-gui.
   - Run `git branch --show-current` (expect main).
   - Run `git log --oneline -20` or `git tag --sort=-version:refname | head -10` to show recent pre-release activity and the current train.
   - Read current `VERSION` and the top of `CHANGELOG.md`.
   - Summarize the changes since the last stable tag (or since the start of this pre-release series). Identify key features/fixes from conventional commits.
   - Confirm with user that this train is ready to promote (no more dev commits expected before the stable release).

2. **Determine the target stable SemVer version**
   - Read current VERSION (e.g. 3.8.7-dev.42 or legacy 3.8.7-42).
   - **Auto-compute promotion** per the canon (increment second octet / minor for a new train, reset patch to 0 for clean release; or simply strip pre-release suffix if staying on same base):
     ```
     CURRENT=$(cat VERSION)
     # Strip any pre-release suffix (dev, beta, rc, alpha, or legacy -N)
     BASE=$(echo "$CURRENT" | sed -E 's/[-+].*$//')
     # Example promotion logic (customize per user rules):
     # If promoting a dev train on 3.8.7-xxx to next minor: suggest 3.9.0
     # Or for patch within minor: 3.8.8
     # User can override.
     MAJOR=$(echo "$BASE" | cut -d. -f1)
     MINOR=$(echo "$BASE" | cut -d. -f2)
     PATCH=$(echo "$BASE" | cut -d. -f3)
     SUGGESTED="${MAJOR}.$((MINOR + 1)).0"   # Common promotion: bump minor, reset patch
     # Alternative for patch train: "${MAJOR}.${MINOR}.$((PATCH + 1))"
     echo "Current pre-release: $CURRENT"
     echo "Suggested stable (SemVer): $SUGGESTED"
     ```
   - Show suggestion with rationale (references AGENTS.md Version Discipline).
   - Let user accept, override with exact stable version (must be clean MAJOR.MINOR.PATCH), or adjust (e.g. 3.9.1).
   - Confirm.

3. **Prepare release artifacts (CHANGELOG, version files)**
   - Read top of CHANGELOG.md.
   - Propose or help finalize a release entry for the stable version (convert the pre-release summary into clean "Features / Fixes / Improvements" under the new stable header). Use Keep a Changelog format.
   - If the computed stable version differs from current base, run the bump script for the stable version (it will update root VERSION + all propagated locations: frontend, docs, ovox/ files).
   - Review all changes (git diff).
   - Stage: `git add CHANGELOG.md VERSION ...` (or git add -u).
   - If any files were updated, create a conventional commit for the release promotion itself (e.g. "chore(release): prepare 3.9.0").

4. **Create the stable annotated tag**
   - Use the confirmed clean stable version.
   - Create annotated tag:
     ```
     git tag -a v<STABLE_VERSION> -m "Release v<STABLE_VERSION>

     <release notes summary or link to CHANGELOG>

     Assisted By: Grok AI"
     ```
   - Verify: `git tag -n1 | tail -5` and `git show v<STABLE_VERSION>`.

5. **Push the stable tag**
   - `git push origin main` (if the promotion commit exists).
   - `git push origin v<STABLE_VERSION>`
   - Confirm success.

6. **Prepare (do not auto-create) the GitHub Release**
   - Print the exact command for the user:
     ```
     gh release create v<STABLE_VERSION> --title "v<STABLE_VERSION>" --notes "..." --target main
     ```
   - Remind (quoting AGENTS.md): GitHub Releases are a separate, deliberate, manual step. Only do this when the tag is clean, tested, and "ready to ship" (per schedule). Do not run it now unless explicitly instructed.
   - Optionally generate release notes from CHANGELOG or recent commits and show them for copy-paste.
   - Strongly recommend wrapping any immediate post-release deploy with maintenance mode.

## Edge Cases & Safety
- If the current state is already a clean stable (no pre-release), the skill will note this and suggest whether to start a new dev train (via /commit) or cut a patch.
- Promotion logic can be overridden; always confirm before tagging.
- Never create GitHub Releases automatically.
- Respect the full pre-commit checklist for any promotion commit.
- If on a feature branch, warn and require explicit main merge first.
- The skill is non-destructive until user approves version, changelog, and tag steps.
- This implements the exact SemVer + pre-release + separate-release policy canonized across the entire estate (global .grok/Agents.md, this project's AGENTS.md, skills, bump-version.sh, ovox/README.md, CHANGELOG process entries).

## How to invoke
```
/release
/release 3.9.0
/release "promote current dev train"
```

When active (inside the tree), this skill takes precedence for release promotion work. It works alongside (does not replace) the /commit skill for dev work.

This completes the SemVer lifecycle while keeping fast dev cadence and intentional user releases.