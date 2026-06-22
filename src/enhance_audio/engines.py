"""Audio enhancement engine registry.

Each engine takes an input WAV path and writes a cleaned WAV to ``out_wav``.
Heavy deps are **lazy-imported inside the run function** (mirrors
``src.smartcuts.analyzer.detect_silences_vad``) so importing this module never
pulls torch/DeepFilterNet into the GUI subprocess.

Engines are pure-logic — no Resolve, no widgets. ``strength`` is 0.0–1.0 and is
interpreted per engine (mix / attenuation depth). Engines run in chain order;
the registry preserves insertion order so the UI can list them deterministically.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable

from src.utils.logger import get_logger

log = get_logger(__name__)

# A run function: (in_wav, out_wav, strength) -> None. Writes a WAV to out_wav.
RunFn = Callable[[str, str, float], None]


@dataclass(frozen=True)
class EngineSpec:
    """Metadata + runner for one enhancement engine.

    Attributes:
        id:           Stable key used in settings + chain ordering.
        label:        Human label for the UI checkbox.
        is_core:      Core engines are always installed (no popup).
        pip_pkg:      pip requirement string for on-demand install ("" if core/none).
        install_note: Short CPU/size warning shown in the install-confirm modal.
        run:          The processing function.
    """

    id: str
    label: str
    is_core: bool
    pip_pkg: str
    install_note: str
    run: RunFn

    @property
    def import_name(self) -> str:
        """Top-level module name to probe for is_installed()."""
        return _IMPORT_NAME.get(self.id, self.id)

    @property
    def has_strength(self) -> bool:
        """True if this engine has a meaningful strength parameter."""
        return self.id in _HAS_STRENGTH


# Engines that expose a meaningful strength parameter in their run function.
_HAS_STRENGTH: set[str] = {"vad_gate"}

# Engine id → top-level import module (for the installed-check).
_IMPORT_NAME: dict[str, str] = {
    "deepfilternet": "df",
    "vad_gate": "silero_vad",
    "resemble": "resemble_enhance",
    "demucs": "demucs",
}


# ── Engine implementations ─────────────────────────────────────────────────

def _run_deepfilternet(in_wav: str, out_wav: str, strength: float) -> None:
    """Noise + reverb removal via DeepFilterNet (ONNX-backed, CPU-friendly)."""
    from df.enhance import enhance, init_df, load_audio, save_audio  # type: ignore

    model, df_state, _ = init_df()
    audio, _info = load_audio(in_wav, sr=df_state.sr())
    enhanced = enhance(model, df_state, audio)
    save_audio(out_wav, enhanced, df_state.sr())
    log.info("[enhance] deepfilternet wrote %s", out_wav)


def _run_vad_gate(in_wav: str, out_wav: str, strength: float) -> None:
    """Attenuate non-speech regions using Silero VAD speech timestamps.

    strength 0→1 maps to attenuation depth: 0 = -6 dB on gaps, 1 = full mute.
    """
    from pydub import AudioSegment  # type: ignore
    from src.smartcuts.analyzer import detect_silences_vad

    seg = AudioSegment.from_file(in_wav)
    # Reuse the project's VAD silence detector — it returns non-speech regions.
    regions = detect_silences_vad(in_wav, min_duration_ms=200.0, padding_ms=80.0)

    # Gap attenuation: -6 dB (mild) up to full silence at max strength.
    atten_db = -6.0 - (strength * 60.0)  # -6 dB .. -66 dB
    out = seg
    for r in regions:
        start, end = int(r.start_ms), int(r.end_ms)
        if end <= start:
            continue
        before, gap, after = out[:start], out[start:end], out[end:]
        out = before + gap.apply_gain(atten_db) + after

    out.export(out_wav, format="wav")
    log.info("[enhance] vad_gate wrote %s (%d gaps, %.0f dB)", out_wav, len(regions), atten_db)


def _run_resemble(in_wav: str, out_wav: str, strength: float) -> None:
    """Speech enhancement + denoise via resemble-enhance (heavy, GPU-ideal)."""
    import torch  # type: ignore
    import torchaudio  # type: ignore
    from resemble_enhance.enhancer.inference import enhance as re_enhance  # type: ignore

    dwav, sr = torchaudio.load(in_wav)
    dwav = dwav.mean(dim=0)  # mono
    device = "cuda" if torch.cuda.is_available() else "cpu"
    wav, new_sr = re_enhance(dwav, sr, device, solver="midpoint", nfe=64)
    torchaudio.save(out_wav, wav.unsqueeze(0).cpu(), new_sr)
    log.info("[enhance] resemble wrote %s (device=%s)", out_wav, device)


def _run_demucs(in_wav: str, out_wav: str, strength: float) -> None:
    """Source separation — keep the vocals stem, drop music/background."""
    import torch  # type: ignore
    import torchaudio  # type: ignore
    from demucs.pretrained import get_model  # type: ignore
    from demucs.apply import apply_model  # type: ignore
    from demucs.audio import convert_audio  # type: ignore

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = get_model("htdemucs")
    model.to(device)
    model.eval()

    wav, sr = torchaudio.load(in_wav)
    wav = convert_audio(wav, sr, model.samplerate, model.audio_channels)
    wav = wav.unsqueeze(0).to(device)

    with torch.no_grad():
        sources = apply_model(model, wav, device=device)[0]  # (sources, channels, samples)

    source_names = model.sources if hasattr(model, "sources") else model.models[0].sources
    vocals_idx = source_names.index("vocals")
    vocals = sources[vocals_idx].cpu()
    torchaudio.save(out_wav, vocals, model.samplerate)
    log.info("[enhance] demucs wrote %s (vocals stem)", out_wav)


# ── Registry (insertion order = display + chain order) ──────────────────────

_REGISTRY: dict[str, EngineSpec] = {
    spec.id: spec
    for spec in (
        EngineSpec(
            id="deepfilternet",
            label="Noise & reverb removal",
            is_core=False,
            pip_pkg="deepfilternet",
            install_note=(
                "Requires deepfilterlib (Rust-compiled extension).\n\n"
                "• Python 3.10 / 3.11: installs directly with pip — no Rust needed.\n"
                "• Python 3.12+: no pre-built wheel exists yet. You must first install "
                "the Rust toolchain (https://rustup.rs), then re-run the install.\n\n"
                "CPU-friendly (ONNX-backed). Removes both noise AND reverb."
            ),
            run=_run_deepfilternet,
        ),
        EngineSpec(
            id="vad_gate",
            label="Attenuate non-speech gaps  (not for pre-cut timelines — see ⓘ)",
            is_core=False,
            pip_pkg="",
            install_note=(
                "Uses silero-vad, already installed with Clautter.\n\n"
                "Ducks audio between words where no speech is detected — useful for "
                "reducing background noise without cutting the timeline.\n\n"
                "⚠  NOT for timelines already cut with Smart Cuts:\n"
                "Smart Cuts removes silence clips entirely. If you already ran Smart Cuts, "
                "the gaps are gone and this engine has nothing to attenuate. "
                "Use this engine INSTEAD of Smart Cuts when you want to keep a continuous "
                "take on the timeline but reduce noise in the quiet parts."
            ),
            run=_run_vad_gate,
        ),
        EngineSpec(
            id="resemble",
            label="Speech restoration (Linux/macOS only)",
            is_core=False,
            pip_pkg="resemble-enhance",
            install_note=(
                "NOT AVAILABLE ON WINDOWS\n\n"
                "Requires deepspeed, which fails to build on Windows due to "
                "a symlink permission error in its setup.py. There are no Windows wheels.\n\n"
                "Linux/macOS only. CPU-heavy — GPU recommended."
            ),
            run=_run_resemble,
        ),
        EngineSpec(
            id="demucs",
            label="Isolate voice from music/background",
            is_core=False,
            pip_pkg="demucs",
            install_note=(
                "Installs demucs + downloads the htdemucs model (~1 GB).\n\n"
                "CPU-heavy — expect slow processing without a CUDA GPU. "
                "Separates the vocals stem from background music and noise."
            ),
            run=_run_demucs,
        ),
    )
}


# pip packages that cannot be installed on specific platforms.
_PLATFORM_BLOCKED: dict[str, set[str]] = {
    "resemble-enhance": {"win32"},
}


def is_available(spec: EngineSpec) -> bool:
    """False if the engine's pip package is blocked on the current platform."""
    return sys.platform not in _PLATFORM_BLOCKED.get(spec.pip_pkg, set())


def all_engines() -> list[EngineSpec]:
    """All engines in display/chain order."""
    return list(_REGISTRY.values())


def get_engine(engine_id: str) -> EngineSpec | None:
    return _REGISTRY.get(engine_id)


def ordered(engine_ids: list[str]) -> list[EngineSpec]:
    """Resolve a set of engine ids to specs in canonical chain order."""
    wanted = set(engine_ids)
    return [spec for spec in _REGISTRY.values() if spec.id in wanted]
