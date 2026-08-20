# build.spec
a = Analysis(
    ["voice_typing/app.py"],
    pathex=[],
    binaries=[],
    datas=[("voice_typing/assets", "voice_typing/assets")],
    hiddenimports=[
        "sounddevice",
        "numpy",
        "websockets",
        "pyperclip",
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VoiceType",
    icon="voice_typing/assets/icon.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

