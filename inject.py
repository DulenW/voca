"""inject.py — clipboard + paste. PLATFORM-SPECIFIC layer (macOS).

Copies final text to the clipboard and sends Cmd+V to the focused app,
optionally restoring the previous clipboard. Isolated so the Windows port
later swaps only this file and hotkey.py. Filled in during Phase 4.
"""
