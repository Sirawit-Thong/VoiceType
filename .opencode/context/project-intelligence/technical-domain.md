<!-- Context: project-intelligence/technical | Priority: critical | Version: 1.0 | Updated: 2026-09-04 -->

# VoiceType Technical Domain

> Windows push-to-talk voice-to-text. Python 3.12+, PySide6, pluggable STT providers.

## Primary Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | >=3.12 | Windows desktop + Qt bindings |
| GUI | PySide6 | >=6.6.0 | Native Windows UI, tray, floating widgets |
| Audio | sounddevice, numpy | >=0.4.6, >=1.26 | Mic capture + level metering |
| Net | websockets, aiohttp | >=12.0, >=3.9.0 | Streaming STT + HTTP batch APIs |
| Secrets | keyring | >=25.0 | Windows Credential Manager vault |
| Env | uv + `.venv` | — | No bare `python` on PATH; use `uv run` |
| Tests | pytest, pytest-asyncio | >=8.0, >=0.23 | `asyncio_mode = "auto"`, 265 suite |
| CI | GitHub Actions | — | `.github/workflows/ci.yml` + README badge |

## Architecture

```
app.py WorkerThread → providers/ (SpeechProvider ABC + Registry)
  ├── streaming: gemini_adapter, openai_realtime, deepgram_adapter (partial results)
  ├── batch: openai_batch, groq / OpenAI-compatible, FreeLLM preset (on release)
  └── cleanup: cleanup.py (Gemini/OpenAI polish) + redaction.py (never log keys)
config/settings.py (SettingsManager + 2 migrations) + config/credential_store.py (sole keyring importer)
speech/ (engine, gemini_live) · audio/recorder.py · ai/text_processor.py (legacy)
windows/ (hotkey, text_injector, startup) · ui/ (settings_window, tray, status_bar)
```

**Worker routing**: streaming providers get live audio; batch providers transcribe on hotkey release; vault keys overlay plaintext via `_settings_dict_with_vault()` (never mutates stored dict); `_emit_final_text()` shared helper owns empty-guard + 0.5s dedup + cleanup→processor→direct precedence for all final paths.

## Naming & Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Vault accounts | `voicetype/{provider_id}/api_key` | `voicetype/groq/api_key` |
| Provider IDs | snake_case | `gemini_live`, `openai_realtime` |
| Tests | `test_<area>.py`, fake keyring + synthetic keys | `test_credential_store.py` |
| Commits | one task = one commit, explicit paths | `feat: ...`, `test: ...`, `docs: ...` |

## Code Standards

- TDD red→green every task; verify with `uv run python -m pytest`
- `docs/` and `uv.lock` NEVER committed (gitignored / untracked by policy)
- `import keyring` allowed ONLY in `config/credential_store.py`
- Qt tests: assert `isHidden()`, never `isVisible()` (unshown windows)
- Never auto-fix red builds — report → propose → approve → fix
- Load `core/standards/code-quality.md` (global) before any implementation

## 📂 Codebase References

**Contracts**: `voice_typing/providers/contracts.py` (SpeechProvider ABC, build_profile) · **Registry**: `voice_typing/providers/registry.py` · **Settings**: `voice_typing/config/settings.py` · **Vault**: `voice_typing/config/credential_store.py` · **Worker**: `voice_typing/app.py` · **Config**: `pyproject.toml`

## Related Files

- `business-tech-bridge.md` — why this architecture
- `decisions-log.md` — decision history
- `living-notes.md` — active work
