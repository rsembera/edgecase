# Release Checklist

The full ritual for shipping a release, from gates to public verification.
Build details live in Mac_Packaging_Guide.md and Linux_Packaging_Guide.md;
this is the order of operations around them. Written from the 2.0.0/2.0.1
releases (August 2026). MailRepo and sibling projects: copy this file and
adjust names.

## One-time per project (already done for EdgeCase, 2026-08-28)

GitHub repo metadata, so the project is findable and self-describing:

```bash
gh repo edit OWNER/REPO \
  --description "One-line description (what, for whom, the differentiators)" \
  --homepage "https://PROJECT-SITE" \
  --add-topic topic-one --add-topic topic-two ...
```

Topic guidance: audience terms (practice-management, therapy), values terms
(privacy, local-first), stack terms (flask, sqlcipher, python), story terms
(ai-assisted-development). Lowercase, hyphenated. Empty/rare topics are good:
whoever searches them finds you first.

`gh` setup: `brew install gh` (Mac) / `apt install gh` (Debian), then
`gh auth login -w`. Mac stores the token in the Keychain (fine); on Linux,
automation from non-desktop shells needs `--insecure-storage` (plaintext,
mode 600 — a deliberate posture call, and not something to note in public
docs beyond this line).

## Every release

1. **Gates** — full test suite green, ruff silent, tree clean. Regression
   tests proven red against prior code before this point, CHANGELOG current.
2. **Version bump** — pyproject.toml, setup_app.py (CFBundleVersion +
   CFBundleShortVersionString). Grep for the old version string; check the
   About modal.
3. **Tag** — `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
   If late fixes land after tagging, move the tag (`git tag -f`, force-push)
   *before* building, so the bundles match the tagged source exactly.
4. **Mac build** — per Mac_Packaging_Guide.md: py2app, sign all .so/.dylib
   then the bundle, notarize (`notarytool --wait`), staple, `spctl` assess,
   build the dmg. Verify the bundle's Info.plist version and spot-check that
   a recently changed file inside the bundle matches HEAD.
5. **Linux build** — `packaging/build_deb.sh X.Y.Z` on the build machine
   (pulls first; script prints the SHA-256).
6. **Checksums** — `shasum -a 256` both artifacts. Write
   `downloads/SHA256SUMS.txt` (two-space format: `<hash>  <filename>`) and
   update the website's "Verify your download" section. Recompute from the
   actual files being published — never copy hashes from an earlier transcript.
7. **Website** — swap packages in `downloads/` (git rm the old, add the new),
   update version strings (download page, hero), add the what's-new entry.
   `git pull --rebase` FIRST (three clones drift), then push = live deploy.
   Curl the download URLs and one changed page from outside to verify.
8. **GitHub Release** —
   ```bash
   gh release create vX.Y.Z dist/App-X.Y.Z.dmg path/to/app_X.Y.Z_amd64.deb \
     downloads/SHA256SUMS.txt --title "X.Y.Z" --latest --verify-tag \
     --notes-file /tmp/notes.md
   ```
   Notes include a checksum table and a pointer to the website's sums — two
   independent publishers of the same hash is what makes verification real.
   Verify assets: `gh release view vX.Y.Z --json assets`.
9. **Docs** — Project Status (release recorded, open items pruned against
   reality — check the filesystem and sibling repos, not memory), Navigation
   Map counts if structure changed, packaging guides if the process changed.
10. **Install the release yourself** — replace the copy in /Applications with
    the shipped dmg. You should run what users run.
11. **Sibling clones** — `git pull` the website's other working copies
    (or accept the rebase next time; either way, know it's pending).

## Verification habits that earned their place

- Diff shipped-bundle templates against HEAD before calling a build final
  (caught a stale-JS dmg, 2.0.0 build day).
- Static assets must carry `?v=` cache-busting or upgraders run old JS
  (2.0.1's reason for existing).
- The packaging-manifest test only sees imports that happen at import time;
  a module-level import in any test file is what surfaces a function-local
  dependency (how pypdf's undeclared status was caught).
