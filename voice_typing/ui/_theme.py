"""Shared UI theme constants for VoiceType."""

MENU_STYLESHEET = (
    "QMenu {"
    "    background-color: #1a1b1e;"
    "    color: #e8eaed;"
    "    border: 1px solid #3c4043;"
    "    border-radius: 8px;"
    "    padding: 4px;"
    "    font-family: 'Segoe UI', sans-serif;"
    "    font-size: 11px;"
    "}"
    "QMenu::item {"
    "    padding: 6px 20px;"
    "    border-radius: 4px;"
    "    margin: 1px 4px;"
    "}"
    "QMenu::item:selected {"
    "    background-color: #303134;"
    "}"
    "QMenu::item:disabled {"
    "    color: #5f6368;"
    "}"
    "QMenu::separator {"
    "    height: 1px;"
    "    background-color: #3c4043;"
    "    margin: 4px 8px;"
    "}"
)

CHECKBOX_STYLE = (
    "QCheckBox { color: #e8eaed; spacing: 8px; font-size: 11px; background: transparent; border: none; }"
    "QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid #5f6368; background: transparent; }"
    "QCheckBox::indicator:hover { border-color: #8ab4f8; }"
    "QCheckBox::indicator:checked { background: #8ab4f8; border-color: #8ab4f8; }"
    "QCheckBox::indicator:checked:hover { background: #aecbfa; border-color: #aecbfa; }"
    "QCheckBox:disabled { color: #5f6368; }"
    "QCheckBox:disabled::indicator { border-color: #3c4043; background: transparent; }"
    "QCheckBox:disabled::indicator:checked { background: #3c4043; border-color: #3c4043; }"
)

SECTION_TITLE_STYLE = (
    "color: #e8eaed; font-size: 12px; font-weight: 600; background: transparent; border: none;"
)

HINT_STYLE = (
    "color: #9aa0a6; font-size: 10px; background: transparent; border: none;"
)

WARNING_STYLE = (
    "color: #fbbc04; font-size: 10px; background: transparent; border: none;"
)

AUDIO_TRACK_STYLE = (
    "QProgressBar {"
    "    background: #2b2d31; border: 1px solid #3c4043; border-radius: 4px;"
    "    text-align: center; color: #9aa0a6; font-size: 10px; max-height: 16px; min-height: 16px;"
    "}"
    "QProgressBar::chunk { background: #8ab4f8; border-radius: 3px; }"
)

# ── UX Phase A: capsule design tokens ─────────────────────────────────
# Canonical capsule states: idle / listening / processing / reconnecting /
# error-dead. Aliases (handled in status_bar.set_state): ready -> idle,
# error -> error-dead. `processing` is retained as its own state.

COLOR_READY = "#34a853"
COLOR_LISTENING = "#ea4335"
COLOR_PROCESSING = "#fbbc04"
# RECONNECTING choice: #fb8c00 (vivid amber/orange).
# Why: PROCESSING already uses golden yellow #fbbc04 to mean "working".
# Reconnecting must be visually distinct (amber/orange vs yellow) so users
# can tell "transient network retry" apart from "working", including for
# red-green color-vision deficiency where red/green alone is ambiguous.
# #fb8c00 is dark enough for contrast on the dark capsule and far enough
# in hue from both #fbbc04 (yellow) and #ea4335 (red).
COLOR_RECONNECTING = "#fb8c00"
COLOR_ERROR_DEAD = "#9aa0a6"

COLOR_CAPSULE_BG = "rgba(26, 27, 30, 0.95)"
COLOR_CAPSULE_BORDER = "#3c4043"
COLOR_TEXT_PRIMARY = "#e8eaed"
COLOR_TEXT_MUTED = "#9aa0a6"
COLOR_FOCUS_RING = "#8ab4f8"
COLOR_DISABLED = "#5f6368"

# ── Overlay / tray fallback tokens (values preserve existing visuals) ──
# Canonical HEX sources for transcript_overlay + tray so they import tokens
# instead of hardcoding. Values are intentionally identical to the previous
# literals: _BG "#1a1b1e", overlay dim text "#888888", hover wash, tray blue.
COLOR_OVERLAY_BG = "#1a1b1e"
COLOR_OVERLAY_BORDER = "#3c4043"
COLOR_OVERLAY_TEXT_BRIGHT = "#e8eaed"
COLOR_OVERLAY_TEXT_DIM = "#888888"
COLOR_OVERLAY_HOVER_BG = "rgba(255, 255, 255, 0.08)"
COLOR_TRAY_FALLBACK_BLUE = "#1a73e8"

FONT_FAMILY = "'Segoe UI', sans-serif"
FONT_SIZE_STATUS = 13
FONT_SIZE_MENU = 11
FONT_SIZE_HINT = 10
FONT_SIZES = {
    "status": FONT_SIZE_STATUS,
    "menu": FONT_SIZE_MENU,
    "hint": FONT_SIZE_HINT,
}
FONT_WEIGHT_NORMAL = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
FONT_WEIGHT_STATUS = FONT_WEIGHT_MEDIUM
FONT_WEIGHTS = {
    "normal": FONT_WEIGHT_NORMAL,
    "medium": FONT_WEIGHT_MEDIUM,
    "semibold": FONT_WEIGHT_SEMIBOLD,
}

RADIUS_CAPSULE = 18
CAPSULE_HEIGHT = 36
TOUCH_TARGET_MIN = 28
OPACITY_DEFAULT = 0.94
OPACITY_IDLE_WAVE_DIM = 0.45

# ── UX Phase B: shared status-hint substrings ─────────────────────────
# Single source for reconnect/transient hint matching (lowercased status
# text → amber dot/capsule). Imported by ui.tray (status_dot_color) and
# app._on_status/_on_error. Keep in sync here only — do not duplicate in
# tray.py or app.py.
#
# - RECONNECT_HINTS → amber reconnecting dot/capsule (tray + status_bar).
#   "attempt " has a trailing space to avoid over-matching words like
#   "attempted"/"attempts" (only "attempt 1/5" / "attempt 1 of N" match).
#   "server busy"/"ready to retry" map the 5xx retryable-idle status
#   ("Server busy, ready to retry — press hotkey again") to amber instead
#   of green so users see it is not healthy-idle.
# - TRANSIENT_ERROR_HINTS → one-off mic/inject nudges. Toast stays
#   transient AND capsule/tray go amber (processing/yellow capsule +
#   amber tray dot) instead of error-dead gray, so a single mic/inject
#   blip never looks permanently dead. Persistent errors (connection/key/
#   quota/model) stay error-dead + gray. "inject" subsumes
#   "injection failed" (every "injection failed" contains "inject").
RECONNECT_HINTS = (
    "reconnecting",
    "reconnect ",
    "connection lost",
    "attempt ",
    "trying next key",
    "will start automatically",
    "retrying",
    "server busy",
    "ready to retry",
)
TRANSIENT_ERROR_HINTS = (
    "microphone",
    "inject",
)

# ── UX Phase B: toast design tokens ───────────────────────────────────
# Toasts reuse the existing palette so transient/persistent states stay
# visually consistent with the capsule (processing yellow vs error red).
# - transient accent reuses COLOR_PROCESSING (#fbbc04, "working" yellow)
# - persistent accent reuses COLOR_LISTENING (#ea4335, attention red)
# - bg/border/text reuse the overlay/menu dark tokens (#1a1b1e / #3c4043)
# Tray dot mapping (tray.set_status) mirrors capsule states:
#   green  COLOR_READY        Ready / Recording (healthy)
#   amber  COLOR_RECONNECTING reconnecting (vivid amber, distinct from yellow)
#   gray   COLOR_ERROR_DEAD   error / dead
COLOR_TOAST_BG = COLOR_OVERLAY_BG
COLOR_TOAST_BORDER = COLOR_OVERLAY_BORDER
COLOR_TOAST_TEXT = COLOR_TEXT_PRIMARY
COLOR_TOAST_TEXT_MUTED = COLOR_TEXT_MUTED
COLOR_TOAST_TRANSIENT_ACCENT = COLOR_PROCESSING
COLOR_TOAST_PERSISTENT_ACCENT = COLOR_LISTENING

TOAST_RADIUS = 8
TOAST_OPACITY = 0.95
TOAST_FADE_IN_MS = 150
TOAST_FADE_OUT_MS = 120
TOAST_TRANSIENT_MS = 3000


# ── UX Phase C: transcript overlay redesign tokens ────────────────────
# Partial text uses focus-blue so streaming text is distinguishable from
# committed finals (white). Caret reuses the same blue for visual unity.
# Progress bar is a 3px determinate bar (blue fill on dark track) showing
# auto-dismiss countdown; hidden while pinned. Caret blink matches the
# ~530ms console convention.
COLOR_OVERLAY_PARTIAL_BLUE = "#8ab4f8"
COLOR_OVERLAY_CARET = "#8ab4f8"
COLOR_OVERLAY_PROGRESS_BG = "#2b2d31"
COLOR_OVERLAY_PROGRESS_FILL = "#8ab4f8"

OVERLAY_PROGRESS_HEIGHT = 3
OVERLAY_CARET_BLINK_MS = 530

def capsule_stylesheet(accent_color: str | None = None) -> str:
    """Build the capsule container stylesheet.

    Args:
        accent_color: When given, the capsule border is highlighted with a
            1.5px accent border (used for listening/reconnecting). When None,
            the default 1px neutral border is used.
    """
    if accent_color:
        border_css = f"border: 1.5px solid {accent_color};"
    else:
        border_css = f"border: 1px solid {COLOR_CAPSULE_BORDER};"
    return (
        f"#capsule {{ background-color: {COLOR_CAPSULE_BG}; "
        f"border-radius: {RADIUS_CAPSULE}px; {border_css} }}"
    )


def control_button_stylesheet(border_radius: int = 12) -> str:
    """Build the mic/tray/menu control-button stylesheet.

    Includes hover, keyboard-focus ring, and disabled states so touch
    targets meet TOUCH_TARGET_MIN and keyboard focus is always visible.
    """
    return (
        "QPushButton {"
        f" background: transparent; color: {COLOR_TEXT_MUTED}; border: none;"
        f" border-radius: {border_radius}px;"
        "}"
        "QPushButton:hover {"
        " background-color: rgba(255, 255, 255, 0.08);"
        f" color: {COLOR_TEXT_PRIMARY};"
        "}"
        "QPushButton:focus {"
        f" border: 1.5px solid {COLOR_FOCUS_RING};"
        " background-color: rgba(138, 180, 248, 0.12);"
        " outline: none;"
        "}"
        "QPushButton:disabled {"
        f" color: {COLOR_DISABLED}; background: transparent; border: none;"
        "}"
    )


def focus_ring_stylesheet(color: str = COLOR_FOCUS_RING) -> str:
    """Build a standalone focus-ring snippet for QPushButton."""
    return (
        f"QPushButton:focus {{ border: 1.5px solid {color}; "
        "background-color: rgba(138, 180, 248, 0.12); outline: none; }}"
    )


def toast_stylesheet(accent_color: str) -> str:
    """Build the toast container + button stylesheet for an accent color.

    Args:
        accent_color: left accent bar color — COLOR_TOAST_TRANSIENT_ACCENT
            for auto-dismissing notices, COLOR_TOAST_PERSISTENT_ACCENT for
            sticky errors.
    """
    return (
        f"#toastRoot {{ background-color: {COLOR_TOAST_BG}; "
        f"border: 1px solid {COLOR_TOAST_BORDER}; "
        f"border-left: 3px solid {accent_color}; "
        f"border-radius: {TOAST_RADIUS}px; }}"
        "QLabel#toastMsg {"
        f" color: {COLOR_TOAST_TEXT}; font-family: {FONT_FAMILY};"
        f" font-size: {FONT_SIZE_STATUS}px; background: transparent; border: none;"
        "}"
        "QPushButton#toastBtn {"
        f" background: transparent; color: {COLOR_TOAST_TEXT_MUTED}; border: none;"
        f" border-radius: {TOAST_RADIUS - 2}px; padding: 6px 10px;"
        f" font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_MENU}px;"
        "}"
        "QPushButton#toastBtn:hover {"
        " background-color: rgba(255, 255, 255, 0.08);"
        f" color: {COLOR_TOAST_TEXT};"
        "}"
        f"QPushButton#toastBtn:focus {{ border: 1.5px solid {COLOR_FOCUS_RING}; "
        "background-color: rgba(138, 180, 248, 0.12); outline: none; }}"
    )
