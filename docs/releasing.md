# Releasing

This checklist is for project maintainers. Claude Code Gateway uses semantic versions and GitHub
Releases. Version tags use the `vMAJOR.MINOR.PATCH` format.

## Prepare the release

1. Confirm `main` contains only the intended release changes.
2. Set the same version in `pyproject.toml` and
   `src/claude_code_gateway/__init__.py`.
3. Move the release notes from `[Unreleased]` into a dated changelog section such as
   `[1.0.0] - 2026-07-13`, then update the comparison links at the bottom of `CHANGELOG.md`.
4. Run the local release checks:

   ```bash
   ruff check .
   ruff format --check .
   pytest --cov=claude_code_gateway --cov-report=term-missing --cov-fail-under=75
   claude-gateway doctor
   ```

5. Commit and push `main`. Wait for every GitHub Actions job to pass before tagging.

## Tag the verified commit

From a clean, up-to-date `main` branch:

```bash
git switch main
git pull --ff-only
git status --short
git tag -a v1.0.0 -m "Claude Code Gateway v1.0.0"
git push origin v1.0.0
```

`git status --short` must print nothing. Never move or reuse a published version tag; issue a new
patch version instead.

## Create the GitHub Release

Open the repository's **Releases** page, select **Draft a new release**, choose the existing
`v1.0.0` tag, and use `Claude Code Gateway v1.0.0` as the title. Copy the `1.0.0` changelog notes
into the description, review the rendered result, and publish it as the latest release. Do not
mark a stable release as a prerelease.

The equivalent GitHub CLI command is:

```bash
gh release create v1.0.0 \
  --verify-tag \
  --title "Claude Code Gateway v1.0.0" \
  --generate-notes
```

GitHub automatically attaches source archives. This project does not currently publish to PyPI;
package-index publishing should be added separately with trusted publishing rather than storing
an API token in repository secrets.

## Start the next development cycle

Keep `[Unreleased]` at the top of `CHANGELOG.md` and replace `No unreleased changes.` when the next
user-visible change is merged.
