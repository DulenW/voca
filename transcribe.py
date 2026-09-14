"""transcribe.py — mlx-whisper wrapper. Loads the model once and keeps it warm.

Feeds captured audio (numpy float32) directly to the model and injects the
custom vocab as initial_prompt. Filled in across Phases 1, 2 and 6.
"""
