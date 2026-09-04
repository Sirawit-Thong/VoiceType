<!-- Context: project-intelligence/decisions | Priority: medium | Version: 1.1 | Updated: 2026-09-04 -->

# VoiceType Decisions Log

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-09 | Multi-provider via `SpeechProvider` ABC + Registry (branch `feat/multi-provider-stt`, 38 commits) | Vendor freedom, testable contracts | 6 adapters behind one worker |
| 2026-09 | keyring vault + plaintext fallback (not vault-only) | Survive machines without Credential Manager | Banner + Retry UX in settings |
| 2026-09 | `credential_store.py` is the SOLE keyring importer | One audit point for all secret I/O | Enforced by boundary test |
| 2026-09 | Vault-wins resolve + migrate-once-then-blank | Single read path; JSON never holds keys after migration | `migrate_plaintext_keys`, `resolve_profile_key` |
| 2026-09 | Added `numpy>=1.26`, `keyring>=25.0` to `pyproject.toml` | CI failed on missing deps | Green CI on clean runners |
| 2026-09 | `uv.lock` + `docs/` stay out of git | Repro via `uv`, plans are working notes | Commit with explicit paths only |
| 2026-09 | Qt tests assert `isHidden()`, not `isVisible()` | `isVisible()` is False for unshown windows | Fixed banner test blocker |
| 2026-09 | Kill-switch `VOICETYPE_CREDSTORE_DISABLED` in 6 test files | Suite must pass WITH live WinVaultKeyring present | All 265 tests green on any machine |
| 2026-09 | Extract `_emit_final_text()` shared helper (Fix A) | Dedup + cleanup→processor→direct precedence in one place | Streaming + batch + connection-loss share logic |
| 2026-09 | Settings save preserves distinct cleanup provider id (Fix B) | Overwriting cleanup id on save broke cleanup provider memory | `PROVIDER_PRESETS` membership check; unknown/empty fall through |
| 2026-09 | Connection-loss flush routes through shared helper (Fix C) | `_stop_recording_on_connection_lost` bypassed cleanup + dedup | Now same path as hotkey release + batch final |

## Alternatives Considered

- Vault-only storage → rejected: breaks vault-less machines
- `sys.modules` delitem to simulate no-backend → failed with real keyring installed; use `setitem(..., None)` or kill-switch
- conftest.py vault isolation → rejected: would break `test_credential_store.py` fake keyring tests; per-file fixtures chosen instead

## 📂 Codebase References

**Vault**: `voice_typing/config/credential_store.py` · **Migration**: `voice_typing/config/settings.py` (`migrate_keys_to_vault`) · **Helper**: `voice_typing/app.py` (`_emit_final_text`) · **Settings**: `voice_typing/ui/settings_window.py` (`_save_and_close`) · **Deps**: `pyproject.toml` · **CI**: `.github/workflows/ci.yml`

## Related Files

- `living-notes.md` — pending items from these decisions
- `technical-domain.md` — resulting architecture
