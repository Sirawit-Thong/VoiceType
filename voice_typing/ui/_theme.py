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
