# Task Context: Perf Functions 1-5

Session ID: 2026-09-04-perf-functions
Created: 2026-09-04T20:01:00+07:00
Status: in_progress

## Current Request
"1+2+3+4+5" — ทำฟังก์ชันเพิ่มประสิทธิภาพทั้ง 5 ข้อที่เสนอ (ทั้งโปรเจกต์ VoiceType)

## Context Files (Standards to Follow)
- C:\Users\thong\.config\opencode\context\core\standards\code-quality.md (MANDATORY: pure, immutable, <50 lines, composition, DI, explicit error handling)
- D:\dev\VoiceType\.opencode\context\project-intelligence\technical-domain.md (stack Python 3.12+, PySide6, providers ABC+Registry, uv run, TDD, keyring-only-in-credential_store, Qt test rules)

## Reference Files (Source Material to Look At)
- voice_typing/app.py (WorkerThread._update_audio_level L139-158, _inject_with_cleanup L431-444, _resolve_final_text L446-479, _save_history L381-390)
- voice_typing/audio/recorder.py (SAMPLE_RATE 16000, CHUNK 100ms, sounddevice callback)
- voice_typing/providers/audio.py (pcm_to_wav_bytes, wav_duration_sec)
- voice_typing/windows/text_injector.py (_send_unicode_char per-char SendInput, delete_chars loop, _clipboard_inject fast path)
- voice_typing/providers/cleanup.py (GeminiCleanupProvider, OpenAIChatCleanupProvider, never-block contract)
- voice_typing/speech/engine.py (TranscriptBuffer)
- voice_typing/history.py (pure helpers: parse_history_list, trim_history)

## External Docs Fetched
- None yet (numpy/sounddevice/PySide6 internal knowledge sufficient; use ExternalScout only if API doubt arises)

## Components
1. calculate_audio_level — numpy vectorized RMS, pure function, replaces Python for-loop on audio thread
2. is_silence_should_skip — VAD gate to skip sending silent chunks to streaming provider
3. build_sendinput_batch — batch SendInput array single syscall + batched delete_chars
4. debounced_save_history — coalesce history.json writes, avoid disk I/O per inject
5. non-blocking cleanup — callback/async cleanup without future.result blocking WorkerThread

## Constraints
- Pure functions where possible, <50 lines, no mutation of inputs
- No new dependencies, no provider protocol change, no SettingsManager change, no new UI
- TDD: verify with `uv run python -m pytest` (265 tests baseline)
- `import keyring` ONLY in config/credential_store.py (do not touch)
- Qt tests: assert isHidden() never isVisible()
- Incremental: ONE step at a time, validate each before next
- Stop on fail: REPORT -> PROPOSE -> APPROVAL -> fix (never auto-fix)

## Exit Criteria
- [ ] 1. audio level vectorized + unit test, pytest green
- [ ] 2. silence skip gate + unit test, pytest green
- [ ] 3. batch injector + unit test, pytest green
- [ ] 4. debounced history save + unit test, pytest green
- [ ] 5. non-blocking cleanup + unit test, pytest green
- [ ] Full suite `uv run python -m pytest` green, no regression
