<!-- Context: project-intelligence/nav | Priority: high | Version: 1.0 | Updated: 2026-09-04 -->

# VoiceType Project Intelligence

> Local project context for VoiceType. Start here. Global standards live in `~/.config/opencode/context/` (read-only reference).

## Quick Routes

| What You Need | File | Description |
|---------------|------|-------------|
| Understand the "why" | `business-domain.md` | Problem, users, value proposition |
| Understand the "how" | `technical-domain.md` | Stack, architecture, conventions |
| See the connection | `business-tech-bridge.md` | Business needs → technical solutions |
| Know the context | `decisions-log.md` | Why key decisions were made |
| Current state | `living-notes.md` | Active work, debt, open questions |

## Usage

**New agent joining VoiceType**:
1. Read this file, then `technical-domain.md`
2. Read `business-domain.md` + `business-tech-bridge.md` for the "why"
3. Check `living-notes.md` before writing code (know what's in flight)
4. Follow conventions in `technical-domain.md` (TDD, commit rules, vault rules)

## 📂 Codebase References

**Repo root**: `D:\dev\VoiceType` — `voice_typing/` (app), `tests/` (30 test files), `pyproject.toml`, `.github/workflows/ci.yml`

## Related Files

- Global standards: `~/.config/opencode/context/core/standards/` (code-quality MANDATORY before coding)
- `technical-domain.md` — stack & architecture
- `living-notes.md` — what's active right now
