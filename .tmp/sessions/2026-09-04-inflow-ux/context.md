# Task Context: In-flow UX (preview, undo, auto-update, history v2)

Session ID: 2026-09-04-inflow-ux
Created: 2026-09-04T18:55:00+07:00
Status: in_progress

## Current Request
Add 4 in-flow UX features to VoiceType: (1) preview-before-inject popup, (2) undo-last-injection hotkey, (3) auto-update check from GitHub Releases, (4) history pin/favorite + search. User-approved scope 1+2+3+4.

## Locked Decisions (user-approved)
- Preview OFF by default (opt-in in settings; Fast Mode unchanged)
- Undo default hotkey: Ctrl+Shift+Z (configurable in Hotkey tab)
- Update check: manual button (tray/About) + weekly auto-check, opt-in (no silent network by default)

## Context Files (Standards to Follow)
- D:\dev\VoiceType\.opencode\context\project-intelligence\technical-domain.md
- D:\dev\VoiceType\.opencode\context\project-intelligence\business-tech-bridge.md
- D:\dev\VoiceType\.opencode\context\project-intelligence\decisions-log.md
- D:\dev\VoiceType\.opencode\context\project-intelligence\living-notes.md
- D:\dev\VoiceType\.opencode\context\project-intelligence\business-domain.md
- C:\Users\thong\.config\opencode\context\core\standards\code-quality.md (MANDATORY: pure fns, <50 lines, DI)
- C:\Users\thong\.config\opencode\context\core\standards\test-coverage.md
- C:\Users\thong\.config\opencode\context\core\standards\security-patterns.md
- C:\Users\thong\.config\opencode\context\core\workflows\feature-breakdown.md

## Reference Files (Source Material to Look At)
- voice_typing/app.py (`_emit_final_text` ~L401, `_inject` ~L304, `_re_inject`, history ~L49/115/327-352, startup ~L776, `main`)
- voice_typing/windows/text_injector.py (`inject`, `_clipboard_inject`, `_sendinput_inject`)
- voice_typing/windows/hotkey.py (`HOTKEY_OPTIONS`, `_message_loop`, `registration_failures`)
- voice_typing/config/settings.py (`DEFAULT_SETTINGS`, `get_asset_path`, migration pattern)
- voice_typing/ui/settings_window.py (5 tabs, `_save_and_close`, About tab hardcoded v1.0.0 ~L511)
- voice_typing/ui/tray.py (`_build_menu`, history_menu, signals)
- voice_typing/ui/status_bar.py (floating-widget style reference)
- voice_typing/providers/cleanup.py + voice_typing/ai/text_processor.py (aiohttp pattern for update check)
- pyproject.toml (version 0.1.0 — vs About tab v1.0.0 mismatch; single-source needed)
- tests/ (32 files; kill-switch fixtures in 6 files; synthetic keys only)

## External Docs Fetched
None needed (ContextScout: PySide6/aiohttp patterns covered internally; GitHub Releases = plain REST via existing aiohttp pattern).

## Components
1. PreviewDialog (new QDialog: Insert/Edit/Discard; hooks `_emit_final_text` pre-inject; off by default)
2. Undo (track last injected text+length; Ctrl+Shift+Z deletes via SendInput backspaces; configurable VK)
3. UpdateChecker (compare local version vs `api.github.com/repos/Sirawit-Thong/VoiceType/releases/latest`; tray/About surface; weekly opt-in)
4. History v2 (`history.json` list[str] → list[{text,pinned,created_at}] + migration; pin exempt from MAX_HISTORY trim; search UI)

## Constraints
- TDD red→green; `uv run python -m pytest`; 265-test suite must stay green; ruff clean
- `docs/` + `uv.lock` never committed; explicit-path commits; one task = one commit
- Version truth: resolve pyproject 0.1.0 vs About v1.0.0 before update-compare logic
- Preview must hook the single `_emit_final_text` path, not fork it (decisions-log Fix A)
- No new keyring imports; no real network in tests (mock aiohttp)

## Exit Criteria
- [ ] Spec written (docs/superpowers/specs/2026-09-04-inflow-ux.md)
- [ ] Plan written with atomic tasks (docs/superpowers/plans/2026-09-04-inflow-ux.md)
- [ ] All tasks implemented, full suite green (265+ new tests), ruff clean
- [ ] Reviewer pass clean; living-notes + decisions-log updated; pushed to feat branch
