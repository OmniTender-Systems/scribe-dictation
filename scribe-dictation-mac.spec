# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for building Privacy Scribe on macOS (.app bundle)."""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Collect resources and critical data files
datas = [
    ('scribe_dictation/resources', 'scribe_dictation/resources'),
]

# Collect backend dependency datas
datas += collect_data_files('faster_whisper')
datas += collect_data_files('sounddevice')

binaries = []
binaries += collect_dynamic_libs('sounddevice')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        'pynput.keyboard._uinput',
        'soundfile',
        'numpy',
        'faster_whisper',
        'pyperclip',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PrivacyScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=os.environ.get('APPLE_CODESIGN_IDENTITY', None),
    entitlements_file=None,
    icon='scribe_dictation/resources/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PrivacyScribe',
)

app = BUNDLE(
    coll,
    name='PrivacyScribe.app',
    icon='scribe_dictation/resources/icon.icns',
    bundle_identifier='com.privacyscribe.dictation',
    info_plist={
        'CFBundleName': 'PrivacyScribe',
        'CFBundleDisplayName': 'Privacy Scribe',
        'CFBundleIdentifier': 'com.privacyscribe.dictation',
        'CFBundleVersion': '0.2.0',
        'CFBundleShortVersionString': '0.2.0',
        'NSMicrophoneUsageDescription': 'Privacy Scribe requires microphone access to transcribe audio and voice dictation.',
        'NSSpeechRecognitionUsageDescription': 'Privacy Scribe requires speech recognition access to transcribe dictation.',
        'NSAppleEventsUsageDescription': 'Privacy Scribe uses accessibility to simulate keyboard pasting into active applications.',
        'NSAccessibilityUsageDescription': 'Privacy Scribe requires accessibility access to paste transcribed text into target applications.',
        'LSUIElement': False,
        'NSHighResolutionCapable': True,
    },
)
