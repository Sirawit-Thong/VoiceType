# VoiceType — Dual-Mode Capsule UI & System Enhancements Design Spec

**Date:** 2026-08-20  
**Status:** Approved  
**Goal:** Implement a modern, sleek dual-mode floating capsule UI (Dynamic Pill + Ultra-Minimal Dot/Orb) and enhance settings/tray functionality.

---

## 1. Overview & Architecture

VoiceType's floating status bar is redesigned into an ultra-modern, compact, oval capsule with smooth animations and dynamic resizing. Users can switch between two presentation styles:
1. **Dynamic Pill (Default):** Fixed sleek oval pill (~210 × 34px) displaying glowing status, animated waveform, and minimal text hint.
2. **Ultra-Minimal Dot/Orb:** Tiny glowing circle (~34 × 34px) when idle, which smoothly expands into the full pill when recording or hovered, and smoothly collapses when idle.

In addition, the system is enhanced with:
- Quick Language switcher and Fast Mode toggle directly in the System Tray menu.
- Clear History action.
- "Test Connection" button in the Settings window to validate the Gemini API key instantly.
- Real-time animated smooth wave audio visualizer in the capsule.

---

## 2. Floating Capsule Component Design (`ui/status_bar.py`)

### 2.1 Visual Specs
- **Dimensions:**
  - Expanded / Dynamic Pill: `Width: ~210px`, `Height: 34px`, `Border Radius: 17px` (Full oval squircle).
  - Collapsed Dot (Minimal Mode idle): `Width: 34px`, `Height: 34px`, `Border Radius: 17px` (Perfect circular orb).
- **Background & Styling:**
  - Glassmorphic dark slate: `rgba(24, 25, 28, 0.94)`.
  - Border: 1px subtle glow border `rgba(255, 255, 255, 0.10)` or accent glow during recording.
  - Box Shadow / Ambient Glow: Subtle drop shadow for floating elevation.
- **Internal Elements:**
  - **Left:** Status indicator + Microphone icon with glowing state color (Green = Ready, Coral Red = Listening, Amber Yellow = Processing, Gray = Error).
  - **Center:** Smooth 5-bar animated audio wave visualizer + dynamic transcript/status label (auto-truncated).
  - **Right:** Minimal ⋯ menu button (or auto-hidden in tiny dot mode).

### 2.2 Animation & Behavior
- **Expansion / Collapse Animation:**
  - `QPropertyAnimation` targeting widget geometry/width with `QEasingCurve.Type.OutCubic` (duration: 180ms).
- **Waveform Visualizer:**
  - Custom `paintEvent` rendering 5 rounded vertical bars with dynamic height interpolation driven by audio level chunks (`0.0` - `1.0`).
- **Draggability & Position Memory:**
  - Entire capsule can be dragged anywhere on screen. Position is saved in `settings.json` (`status_bar_x`, `status_bar_y`).

---

## 3. Configuration & Settings (`config/settings.py` & `ui/settings_window.py`)

### 3.1 New Configuration Keys
```json
{
  "capsule_style": "pill", // "pill" (Dynamic Pill) or "dot" (Ultra-Minimal Dot)
  "opacity": 0.95
}
```

### 3.2 Settings Window Enhancements
- **Appearance Settings in General Tab:**
  - Capsule Style dropdown: "Dynamic Pill (Always visible capsule)" vs "Ultra-Minimal Dot (Expands on speech/hover)".
- **Gemini Tab:**
  - "Test Connection" button next to API Key input: Verifies the key asynchronously via a lightweight API ping and shows a clear success/error prompt.

---

## 4. System Tray Enhancements (`ui/tray.py`)

- **Quick Language Switcher Submenu:**
  - Submenu "Language (ภาษา)" with choices: `Auto (ไทย/English)`, `Thai (ไทย)`, `English`.
  - Selecting an item updates settings and worker immediately without opening Settings window.
- **Fast Mode Toggle:**
  - Checkable action "Fast Mode (Direct Voice Input)" to quickly toggle AI post-processing on/off.
- **History Management:**
  - "Clear History (ล้างประวัติ)" button inside the Recent History submenu.

---

## 5. Testing & Verification Plan

### 5.1 Automated Unit Tests
- `test_status_bar.py`:
  - Verify switching between `capsule_style="pill"` and `capsule_style="dot"`.
  - Verify expansion on `update_recording_state(True)` and collapse on `update_recording_state(False)`.
  - Verify waveform paint calculations and level clamping.
- `test_settings_window.py` / `test_app.py`:
  - Verify capsule style setting load/save.
  - Verify API Key connection test logic.
- `test_tray.py`:
  - Verify quick language switch signals and menu items.
  - Verify clear history signal and execution.

### 5.2 Verification Evidence
- Full pytest suite execution (100% passing tests).
