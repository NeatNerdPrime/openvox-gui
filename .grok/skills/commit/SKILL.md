---
name: commit
description: Create well-formatted conventional git commits using SemVer pre-releases (e.g. 3.9.0-dev.N or 3.9.0-beta.N) for development trains. Follows strict version discipline, full pre-commit checklist, annotated tagging, and "tag and push only" policy (no GitHub Release creation). Use /commit inside the openvox-gui tree. Implements rules from project AGENTS.md + global pre-commit checklist. Use the separate /release skill to promote to clean stable SemVer.
argument-hint: optional commit message hint or scope
---

# OpenVox GUI Commit Skill (Project-Scoped)

This skill automates the complete "meaningful push" flow for openvox-gui using **SemVer + pre-releases**:

- Enforce global pre-commit checklist (CHANGELOG, applicable docs, bump-version.sh when version moves).
- **Active enforcement** of the project's strict Heredoc Safety rules (from AGENTS.md) for any touched .sh files.
- Follow the project's strict **Version Discipline** and **Release Process** from AGENTS.md (canonized across the estate):
  - Use SemVer: stable releases are clean MAJOR.MINOR.PATCH (e.g. 3.9.0). During dev trains use pre-releases such as `3.9.0-dev.1`, `3.9.0-dev.42`, `3.9.0-beta.N`, or `3.9.0-rc.N`.
  - Increment the pre-release counter on *every* meaningful push (via bump script).
  - Conventional commit (with "Assisted By: Grok AI").
  - Create annotated tag (e.g. v3.9.0-dev.42).
  - Push branch + the new tag.
  - **Never** create a GitHub Release (`gh release create`) here — those are a separate, deliberate, manual step only when a clean stable tag is "ready to ship".
- Use the separate project `/release` skill to promote a completed pre-release train to a clean stable SemVer version, finalize CHANGELOG, create/push the stable tag, and prepare (but not auto-execute) the GitHub Release.
- Always note "Assisted By: Grok AI" in the commit message.
- Keep development velocity high with lightweight pre-release tags while making official releases intentional and high-signal.

The single source of truth for version is the root `VERSION` file. `scripts/bump-version.sh` propagates it everywhere (frontend/package.json, docs headers/examples, ovox/ CLI files, etc.). ovox CLI is lockstep with GUI since 3.7.3. Full canon is in project AGENTS.md, global .grok/Agents.md (Pre-Commit Checklist + Harness Area 1), ovox/README.md, and CHANGELOG process notes.

## Prerequisites (checked by the skill)
- You must be inside the openvox-gui working tree (or a subdirectory).
- Changes should already be staged (`git add ...`) or the skill will help stage after prep.
- Default branch is `main` (per project AGENTS.md).
- Note: This project uses `.grok/skills/` for local overrides (highest precedence). Run `grok inspect` (or ask me) to verify active skills, sources, and costs.

## Step-by-Step Procedure

1. **Confirm context and review changes**
   - Run `git rev-parse --show-toplevel` and verify the path ends with `openvox-gui` (or contains it).
   - Run `git branch --show-current` (expect `main`).
   - Run `git diff --staged` (and `git status --porcelain` if needed).
   - Summarize *what* changed and *why* (in plain language + conventional type suggestion: feat, fix, chore, docs, etc.).
   - If nothing is staged, stop and ask the user to stage the desired changes first.

2. **Handle the Pre-Commit Checklist (global + project)**
   - **CHANGELOG.md**: Read the top of `CHANGELOG.md`. Analyze the staged diff for conventional types (feat, fix, docs, chore, refactor, etc.) and generate an intelligent draft entry (grouped under ### Features, ### Fixes, ### Improvements, ### Process Changes, pulling key file paths or summaries where helpful). Use Keep a Changelog format.
     - Example skeleton:
       ```
       ## [X.Y.Z-N] - $(date +%Y-%m-%d)

       ### Features / Fixes / Improvements / Process Changes
       - ...
       ```
     - Show the draft to the user. Let them edit/approve the text.
     - Once approved, insert it at the top (after the header section) using search_replace or an editor command via terminal.
   - **Version bump (STRICT — every meaningful push, using SemVer pre-releases)**:
     - Read the current version: `cat VERSION` (also note `ovox/VERSION` for parity).
     - **Auto-compute the next pre-release version** (following SemVer + the "increment on EVERY meaningful push" rule canonized in AGENTS.md):
       ```
       CURRENT=$(cat "$REPO_ROOT/VERSION" 2>/dev/null || echo "unknown")
       # Example logic for dev train: if current is 3.9.0-dev.7 or 3.8.7-7 (legacy), suggest 3.9.0-dev.8
       if [[ "$CURRENT" =~ ^([0-9]+\.[0-9]+\.[0-9]+)(-(dev|beta|rc|alpha)\.([0-9]+))?$ ]]; then
         BASE="${BASH_REMATCH[1]}"
         PRE="${BASH_REMATCH[3]:-dev}"
         NUM="${BASH_REMATCH[4]:-0}"
         SUGGESTED="${BASE}-${PRE}.$((NUM + 1))"
       elif [[ "$CURRENT" =~ (.*)-([0-9]+)$ ]]; then
         # Legacy -N migration support
         BASE="${BASH_REMATCH[1]}"
         NUM="${BASH_REMATCH[2]}"
         SUGGESTED="${BASE}-dev.$((NUM + 1))"
       else
         SUGGESTED="${CURRENT}-dev.1"
       fi
       echo "Current: $CURRENT"
       echo "Suggested next pre-release (SemVer): $SUGGESTED"
       ```
     - Show the suggested next pre-release (e.g. `3.9.0-dev.42`) with rationale referencing the project's AGENTS.md Version Discipline and global pre-commit canon.
     - Prompt: "Is this commit meaningful for version purposes? (default: yes per project policy; 'no' will skip bump but still do checklist + commit + optional tag)."
     - Let the user accept, override (e.g. switch to -beta.N or clean stable if finalizing early — but prefer /release skill for promotion), or explicitly skip bump (capture brief reason for message/CHANGELOG).
     - Confirm the exact new version string (or no-bump decision).
     - Run the bump script:
       ```
       ./scripts/bump-version.sh <NEW_VERSION>
       ```
     - The script updates root VERSION, frontend/package.json, doc headers/examples, ovox/ files, etc.
     - Review the diff of changed files.
   - **Other docs / applicable updates**: If the changes affect user-facing behavior, installation, configuration, or troubleshooting, remind the user and help edit the relevant .md files (beyond what the bump script touches). This satisfies the global checklist item "Update documentation (README, INSTALL, UPDATE, TROUBLESHOOTING) if applicable".
   - **Active Heredoc Safety Check (enforcement, per project AGENTS.md)**: 
     - Identify any `.sh` files touched in the staged diff (`git diff --staged --name-only | grep '\.sh$'`).
     - For each, inspect the heredoc usage in the diff (look for `<<`, `<< 'EOF'`, `<< EOF`, backticks, `$()`, etc.).
     - Cross-check strictly against the rules in the project's AGENTS.md (## Heredoc Safety section):
       - Default to **quoted** delimiters: `cat > file << 'EOF' ... EOF`
       - Use **unquoted** (`<< EOF`) *only* when you **explicitly** need shell variable expansion (`${VAR}`) or command substitution.
       - **Never** put backticks (`` ` ``) or `$()` inside any heredoc content unless you deliberately want the shell to execute them at runtime.
       - Add a `NOTE:` comment *above* every intentionally unquoted heredoc explaining why it must remain unquoted.
     - Report any violations with specific evidence (file, approximate line from diff, the offending pattern, and the exact rule broken).
     - Offer concrete fixes (e.g., change to quoted + NOTE:, or move the expansion outside). Use `search_replace` (or terminal editor) to apply approved fixes before continuing.
     - Do not proceed to commit/tag/push until the user confirms all heredoc issues in the change are resolved or intentionally waived with justification.
   - Stage the updated files: `git add CHANGELOG.md VERSION frontend/package.json ovox/...` (and any other doc edits). Use `git add -u` for modified files if appropriate.

3. **Build the conventional commit message**
   - Start with a conventional header: `<type>(<optional-scope>): <short summary>`
   - Add a body with the summary of changes (from step 1) plus any context.
   - **Always append** (on a new line or in the footer):
     ```
     Assisted By: Grok AI
     ```
   - If the user provided text after `/commit` (e.g. `/commit fix the maintenance page`), incorporate it as the summary or body.
   - Show the full proposed message to the user for final approval/edit.

4. **Commit**
   - Run:
     ```
     git commit -m "<the full approved message>"
     ```
   - Capture the resulting commit hash and subject.

5. **Create the annotated tag (per project "tag and push only" rule)**
   - Use the pre-release version that was just bumped (e.g. v3.9.0-dev.42). These are lightweight dev tags for traceability and deploys.
   - Create annotated tag:
     ```
     git tag -a v<NEW_VERSION> -m "Pre-release v<NEW_VERSION>

     <short description from commit or user>

     Assisted By: Grok AI"
     ```
   - Verify with `git tag -n1 | tail -5` or `git show v<NEW_VERSION>`.
   - Note: Clean stable tags (e.g. v3.9.0) are created by the separate /release skill.

6. **Push branch + tag**
   - Current branch (usually `main`):
     ```
     git push origin $(git rev-parse --abbrev-ref HEAD)
     ```
   - The tag:
     ```
     git push origin v<NEW_VERSION>
     ```
   - Confirm both succeeded (look for the " * [new tag]" line).

7. **Explicitly do NOT create a GitHub Release**
   - Under no circumstances run `gh release create`, `gh release` commands, or anything that publishes a formal GitHub Release during the dev pre-release commit flow.
   - After the push, print a clear reminder to the user:
     > Per openvox-gui AGENTS.md (and global canon): GitHub Releases are a **separate, deliberate, atomic step**. Use the /release skill to promote to a clean stable SemVer tag first, then create the GH Release (with `gh release create`) only when that stable tag is clean, tested, and explicitly "ready to ship" — typically on a pre-determined schedule. Pre-release tags are for fast iteration and deployment; clean releases are for announced, high-signal shipments.

8. **Post-push steps — complete the checklist with actual deploy execution**
   - The global pre-commit checklist and project AGENTS.md explicitly end with "push, then deploy".
   - After successful branch + tag push (pre-release dev tag):
     - Check for `OPENVOX_DEPLOY_HOST` and `OPENVOX_DEPLOY_USER`.
     - Strongly recommend the maintenance wrap.
     - Ask to run deploy now (recommended).
     - Execute `./scripts/update_remote.sh --yes` (with env) if approved; report results.
   - When the entire pre-release train is ready for users, run the separate `/release` skill to promote to clean stable SemVer, create the final tag, push it, and prepare the manual GitHub Release.
   - This keeps /commit focused on fast dev iteration while the full estate (skills + AGENTS + scripts) drives the complete SemVer lifecycle.

## Edge Cases & Safety
- If the bump script or any step fails, stop and report the error. Do not force a commit.
- If the user is on a feature branch (rare — project prefers main), still push the current branch + tag, but note the branching policy.
- Heredoc safety is now **actively enforced**.
- **SemVer pre-release discipline**: /commit produces dev pre-releases (e.g. 3.9.0-dev.N). Use /release skill (not /commit) to promote to stable clean MAJOR.MINOR.PATCH. Legacy -N suffixes are migrated automatically in suggestion logic.
- Never guess credentials or do external actions (the push here is local git + the user's configured SSH remote).
- The skill is non-destructive until the user explicitly approves each major step (version, changelog text, final message).
- Full versioning knowledge is spread in project AGENTS.md, global .grok/Agents.md, ovox/README.md, bump-version.sh, CHANGELOG process notes, and this skill.

## How to invoke
```
/commit
/commit fix the 503 maintenance page for browsers
/commit "chore(deps): update foo"
```

When this project-scoped skill is active (inside the tree), it takes precedence over the global `~/.grok/skills/commit/`. You can still force the global one with a qualified name if needed for other repos.

This implements the exact policy the user and the project's AGENTS.md have defined for fast, clean, versioned development with manual releases.

This skill directly supports the "prefer invoking /commit (or a project-enhanced variant)" rule in the global "Harness Capabilities & Active Leverage" section (Area 1) in .grok/Agents.md. Run `grok inspect` (or ask me) to verify loaded skills, sources (user/project/bundled), and token costs.
