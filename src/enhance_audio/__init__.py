"""Enhance Audio — clean up crappy talking-head source audio.

Engine chain (noise removal, VAD gating, optional speech enhancement /
source separation) runs on a clip's source WAV; the cleaned result is placed
on a dedicated "Enhanced" timeline track, leaving the original untouched.
"""
