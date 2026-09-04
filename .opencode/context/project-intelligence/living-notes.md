<!-- Context: project-intelligence/notes | Priority: high | Version: 1.1 | Updated: 2026-09-04 -->

# VoiceType Living Notes

> Check this file BEFORE writing code — it lists what's in flight.

## Active Work (branch `feat/multi-provider-stt`)

- [x] **Cred-store Tasks 1-11**: COMPLETE (kill-switch isolation for live vault; 265 passed)
- [x] **Reviewer pass**: COMPLETE — security/correctness/test-quality all PASS
- [x] **UX-polish Tasks 1-8**: COMPLETE (Fix A: shared helper, Fix B: cleanup-id preservation, Fix C: connection-loss routing)
- [x] **CI Task 6**: branch pushed to `origin/feat/multi-provider-stt`
- [ ] **PR creation**: no `gh` CLI on this machine — create manually at https://github.com/Sirawit-Thong/VoiceType/pull/new/feat/multi-provider-stt

## Known Issues

- README tests badge count (112) is stale vs actual suite (265 passed)
- Dev-machine vault must be purged of `voicetype/*` fixture entries after test runs (kill-switch prevents this now)
- `docs/superpowers/*` plans/specs are working notes, deliberately excluded from commits

## Open Questions

- PR strategy: single PR for multi-provider + cred-store + UX-polish, or split?
- Should README badge update to reflect 265 tests before or after merge?

## 📂 Codebase References

**Plans**: `docs/superpowers/plans/2026-09-04-credential-store.md` (11 tasks), `2026-09-04-ci.md` (7 tasks), `2026-09-04-ux-polish.md` (8 tasks) · **Vault tests**: `tests/test_credential_store.py` (32 tests) · **Kill-switch**: `tests/conftest`-level `_disable_vault_backend` fixtures in 6 test files + `VOICETYPE_CREDSTORE_DISABLED` env var in `credential_store.py`

## Related Files

- `decisions-log.md` — decided, `technical-domain.md` — conventions to follow
