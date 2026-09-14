"""hotkey.py — pynput global hotkey listener, push-to-talk. PLATFORM-SPECIFIC.

Passive at idle (event-driven, never polls). Key down -> start capture,
key up -> stop and transcribe. Isolated so the Windows port swaps only this
file and inject.py. Filled in during Phase 3.
"""
