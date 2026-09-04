<!-- Context: project-intelligence/bridge | Priority: medium | Version: 1.0 | Updated: 2026-09-04 -->

# VoiceType Business–Tech Bridge

> How each business need maps to a technical solution.

| Business Need | Technical Solution | Where |
|---------------|-------------------|-------|
| Sub-second transcription | Streaming adapters (Gemini Live, OpenAI Realtime, Deepgram) with partial results | `providers/gemini_adapter.py`, `openai_realtime.py`, `deepgram_adapter.py` |
| Cheap/simple providers | Batch-on-release adapters (Groq, OpenAI-compatible, FreeLLM preset) | `providers/openai_batch.py`, `presets.py` |
| Swap vendors without rewrite | `SpeechProvider` ABC + `ProviderRegistry` + `build_profile()` | `providers/contracts.py`, `registry.py` |
| Pure Thai / Auto language | Strict language modes + custom vocabulary + post cleanup | `providers/cleanup.py`, `ai/text_processor.py` |
| Type into any app instantly | Fast Mode via `TextInjector` + clipboard option | `windows/text_injector.py` |
| API keys never leak | Keyring vault boundary + `redact_text()` + vault-wins resolve | `config/credential_store.py`, `providers/redaction.py` |
| Survive no-vault machines | Plaintext fallback + settings banner (Retry / Learn more) | `ui/settings_window.py` |
| Catch regressions | 32 pytest files + GitHub Actions CI | `tests/`, `.github/workflows/ci.yml` |

## 📂 Codebase References

**Worker routing** (streaming vs batch, vault overlay): `voice_typing/app.py` · **Settings UI gating**: `voice_typing/ui/settings_window.py`

## Related Files

- `business-domain.md` — the needs
- `technical-domain.md` — the solutions in depth
