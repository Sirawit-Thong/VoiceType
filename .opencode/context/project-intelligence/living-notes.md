<!-- Context: project-intelligence/notes | Priority: high | Version: 1.0 | Updated: 2026-09-04 -->

# VoiceType Living Notes

> Check this file BEFORE writing code — it lists what's in flight.

## Active Work (branch `feat/multi-provider-stt`)

- [ ] **Cred-store Task 11**: full regression + test isolation for live WinVaultKeyring (kill-switch approach approved; Tasks 1–10 committed)
- [ ] **CI Task 6**: push branch + verify GitHub Actions green (no `gh` CLI on this machine — use web UI)
- [ ] **UX-polish plan**: 8 tasks untouched (`docs/superpowers/plans/2026-09-04-ux-polish.md`)
- [ ] **Reviewer pass**: one review over cred-store range after Task 11

## Known Issues

- 4 tests (`test_config`, `test_settings_migration`) fail when a LIVE vault exists — fixture keys migrate to the real vault (Task 11 owns the fix)
- Dev-machine vault must be purged of `voicetype/*` fixture entries after test runs
- README tests badge count (112) is stale vs actual suite (~250+)

## Open Questions

- PR strategy: single PR for multi-provider + cred-store, or split?
- Who purges stray vault entries on contributor machines — document in README?

## 📂 Codebase References

**Plans**: `docs/superpowers/plans/2026-09-04-credential-store.md` (11 tasks), `2026-09-04-ci.md`, `2026-09-04-ux-polish.md` · **Vault tests**: `tests/test_credential_store.py` (32 tests)

## Related Files

- `decisions-log.md` — decided, `technical-domain.md` — conventions to follow
