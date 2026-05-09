"""Spectral and dynamics comparison helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np


DISPLAY_BANDS = (
    (60.0, 80.0, "60-80 Hz"),
    (80.0, 160.0, "80-160 Hz"),
    (160.0, 320.0, "160-320 Hz"),
    (320.0, 630.0, "320-630 Hz"),
    (630.0, 1250.0, "630-1.25k"),
    (1250.0, 2500.0, "1.25-2.5k"),
    (2500.0, 5000.0, "2.5-5k"),
    (5000.0, 10000.0, "5-10k"),
    (10000.0, 16000.0, "10-16k"),
)

ISO_THIRD_OCTAVE_CENTERS = (
    63.0,
    80.0,
    100.0,
    125.0,
    160.0,
    200.0,
    250.0,
    315.0,
    400.0,
    500.0,
    630.0,
    800.0,
    1000.0,
    1250.0,
    1600.0,
    2000.0,
    2500.0,
    3150.0,
    4000.0,
    5000.0,
    6300.0,
    8000.0,
    10000.0,
    12500.0,
    16000.0,
)

SUGGESTION_THRESHOLD_DB = 2.0
EPSILON = 1e-12


@dataclass
class BandPower:
    low_hz: float
    high_hz: float
    label: str
    power_db: float
    normalized_db: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BandPower":
        return cls(
            low_hz=float(data["low_hz"]),
            high_hz=float(data["high_hz"]),
            label=str(data["label"]),
            power_db=float(data["power_db"]),
            normalized_db=float(data["normalized_db"]),
        )


@dataclass
class SpectralReport:
    sample_rate: int
    duration_seconds: float
    total_power_db: float
    crest_factor_db: float
    spectral_centroid_hz: float
    spectral_bandwidth_hz: float
    mid_side_ratio: float
    bands: List[BandPower]
    third_octave_bands: List[BandPower]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpectralReport":
        return cls(
            sample_rate=int(data["sample_rate"]),
            duration_seconds=float(data["duration_seconds"]),
            total_power_db=float(data["total_power_db"]),
            crest_factor_db=float(data["crest_factor_db"]),
            spectral_centroid_hz=float(data["spectral_centroid_hz"]),
            spectral_bandwidth_hz=float(data["spectral_bandwidth_hz"]),
            mid_side_ratio=float(data["mid_side_ratio"]),
            bands=[BandPower.from_dict(item) for item in data["bands"]],
            third_octave_bands=[
                BandPower.from_dict(item) for item in data["third_octave_bands"]
            ],
        )


@dataclass
class Suggestion:
    category: str
    action: str
    amount: float
    unit: str
    target: str
    reason: str

    def to_text(self) -> str:
        if self.category == "EQ":
            return f"{self.action} {self.target} by ~{self.amount:.1f} {self.unit} ({self.reason})"
        return f"{self.action}: {self.reason}"


@dataclass
class ComparisonReport:
    yours: SpectralReport
    reference: SpectralReport
    band_differences_db: Dict[str, float]
    third_octave_differences_db: Dict[str, float]
    crest_factor_difference_db: float
    centroid_difference_hz: float
    bandwidth_difference_hz: float
    mid_side_ratio_difference: float
    suggestions: List[Suggestion]
    matched_lufs: Optional[float] = None
    capture_seconds: Optional[float] = None
    saved_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComparisonReport":
        return cls(
            yours=SpectralReport.from_dict(data["yours"]),
            reference=SpectralReport.from_dict(data["reference"]),
            band_differences_db={k: float(v) for k, v in data["band_differences_db"].items()},
            third_octave_differences_db={
                k: float(v) for k, v in data["third_octave_differences_db"].items()
            },
            crest_factor_difference_db=float(data["crest_factor_difference_db"]),
            centroid_difference_hz=float(data["centroid_difference_hz"]),
            bandwidth_difference_hz=float(data["bandwidth_difference_hz"]),
            mid_side_ratio_difference=float(data["mid_side_ratio_difference"]),
            suggestions=[Suggestion(**item) for item in data.get("suggestions", [])],
            matched_lufs=data.get("matched_lufs"),
            capture_seconds=data.get("capture_seconds"),
            saved_to=data.get("saved_to"),
        )


def analyze(audio_array: np.ndarray, sample_rate: int) -> SpectralReport:
    """Analyze tonal balance, dynamics, brightness, and stereo width."""
    audio = _as_float_audio(audio_array)
    if audio.size == 0:
        raise ValueError("audio_array must contain at least one sample")

    mono = _to_mono(audio)
    total_power_db = _power_to_db(float(np.mean(np.square(mono))))
    spectrum_freqs, spectrum_power = _power_spectrum(mono, sample_rate)
    spectrum_total_db = _power_to_db(float(np.sum(spectrum_power)))

    bands = _band_powers(DISPLAY_BANDS, spectrum_freqs, spectrum_power, spectrum_total_db)
    third_octave_bands = _band_powers(
        _third_octave_ranges(),
        spectrum_freqs,
        spectrum_power,
        spectrum_total_db,
    )

    centroid_hz, bandwidth_hz = _spectral_shape(mono, sample_rate)
    return SpectralReport(
        sample_rate=int(sample_rate),
        duration_seconds=float(len(mono) / sample_rate),
        total_power_db=total_power_db,
        crest_factor_db=crest_factor(audio),
        spectral_centroid_hz=centroid_hz,
        spectral_bandwidth_hz=bandwidth_hz,
        mid_side_ratio=mid_side_ratio(audio),
        bands=bands,
        third_octave_bands=third_octave_bands,
    )


def compare(
    report_a: SpectralReport,
    report_b: SpectralReport,
    matched_lufs: Optional[float] = None,
    capture_seconds: Optional[float] = None,
) -> ComparisonReport:
    """Compare user's report (A) against reference report (B)."""
    band_differences = _differences_by_label(report_a.bands, report_b.bands)
    third_octave_differences = _differences_by_label(
        report_a.third_octave_bands,
        report_b.third_octave_bands,
    )
    comparison = ComparisonReport(
        yours=report_a,
        reference=report_b,
        band_differences_db=band_differences,
        third_octave_differences_db=third_octave_differences,
        crest_factor_difference_db=report_a.crest_factor_db - report_b.crest_factor_db,
        centroid_difference_hz=report_a.spectral_centroid_hz - report_b.spectral_centroid_hz,
        bandwidth_difference_hz=report_a.spectral_bandwidth_hz - report_b.spectral_bandwidth_hz,
        mid_side_ratio_difference=report_a.mid_side_ratio - report_b.mid_side_ratio,
        suggestions=[],
        matched_lufs=matched_lufs,
        capture_seconds=capture_seconds,
    )
    comparison.suggestions = suggest_adjustments(comparison)
    return comparison


def suggest_adjustments(comparison: ComparisonReport) -> List[Suggestion]:
    """Map objective differences to deterministic, non-applied suggestions."""
    suggestions: List[Suggestion] = []
    for label, diff_db in comparison.band_differences_db.items():
        if abs(diff_db) < SUGGESTION_THRESHOLD_DB:
            continue
        amount = _rounded_half_db(abs(diff_db))
        action = "Cut" if diff_db > 0 else "Boost"
        suggestions.append(
            Suggestion(
                category="EQ",
                action=action,
                amount=amount,
                unit="dB",
                target=label,
                reason=_band_reason(label, diff_db),
            )
        )

    crest_diff = comparison.crest_factor_difference_db
    if crest_diff > SUGGESTION_THRESHOLD_DB:
        amount = _rounded_half_db(crest_diff)
        suggestions.append(
            Suggestion(
                category="Dynamics",
                action="Apply additional compression",
                amount=amount,
                unit="dB",
                target="crest factor",
                reason=f"target about {amount:.1f} dB more gain reduction",
            )
        )
    elif crest_diff < -SUGGESTION_THRESHOLD_DB:
        amount = _rounded_half_db(abs(crest_diff))
        suggestions.append(
            Suggestion(
                category="Dynamics",
                action="Ease compression or limiting",
                amount=amount,
                unit="dB",
                target="crest factor",
                reason=f"your vocal is about {amount:.1f} dB more compressed than the reference",
            )
        )

    if comparison.mid_side_ratio_difference < -0.10:
        suggestions.append(
            Suggestion(
                category="Stereo",
                action="Reduce width",
                amount=0.75,
                unit="ratio",
                target="vocal group width",
                reason="your vocal is wider / less focused than the reference",
            )
        )
    elif comparison.mid_side_ratio_difference > 0.10:
        suggestions.append(
            Suggestion(
                category="Stereo",
                action="Consider widening",
                amount=1.10,
                unit="ratio",
                target="vocal group width",
                reason="your vocal is more centered than the reference",
            )
        )

    return suggestions


def format_report(comparison: ComparisonReport) -> str:
    seconds = comparison.capture_seconds or comparison.yours.duration_seconds
    capture_context = (
        f"matched at {comparison.matched_lufs:g} LUFS"
        if comparison.matched_lufs is not None
        else "post-FFT normalized loudness"
    )
    lines = [
        f"Spectral comparison ({capture_context}, {seconds:g}s capture):",
        "",
        "Frequency balance (your stack vs reference, dB difference):",
    ]
    for band in comparison.yours.bands:
        diff = comparison.band_differences_db[band.label]
        note = _format_band_note(band.label, diff)
        lines.append(f"  {band.label + ':':<13} {diff:+6.1f} dB{note}")

    crest_diff = comparison.crest_factor_difference_db
    lines.extend(
        [
            "",
            "Dynamics:",
            f"  Your crest factor:       {comparison.yours.crest_factor_db:.1f} dB",
            f"  Reference crest factor:  {comparison.reference.crest_factor_db:.1f} dB",
            f"  Difference:              {crest_diff:+.1f} dB  ({_crest_note(crest_diff)})",
            "",
            "Stereo:",
            f"  Your mid/side ratio:     {comparison.yours.mid_side_ratio:.2f}  ({_width_note(comparison.yours.mid_side_ratio)})",
            f"  Reference mid/side ratio: {comparison.reference.mid_side_ratio:.2f}  ({_width_note(comparison.reference.mid_side_ratio)})",
            f"  -> {_stereo_difference_note(comparison.mid_side_ratio_difference)}",
            "",
            "Brightness (spectral centroid):",
            f"  Yours:      {comparison.yours.spectral_centroid_hz:,.0f} Hz",
            f"  Reference:  {comparison.reference.spectral_centroid_hz:,.0f} Hz",
            f"  -> {_brightness_note(comparison.centroid_difference_hz)}",
            "",
            "Suggested adjustments (objective, deterministic):",
        ]
    )
    grouped = _suggestions_by_category(comparison.suggestions)
    if grouped:
        for category in ("EQ", "Dynamics", "Stereo"):
            items = grouped.get(category, [])
            if not items:
                continue
            lines.append(f"  {category}:")
            for suggestion in items:
                lines.append(f"    - {suggestion.to_text()}")
    else:
        lines.append("  No deterministic suggestions exceeded the configured thresholds.")

    if comparison.saved_to:
        lines.extend(["", f"Saved to: {comparison.saved_to}"])

    return "\n".join(lines)


def crest_factor(audio_array: np.ndarray) -> float:
    audio = _as_float_audio(audio_array)
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms <= EPSILON or peak <= EPSILON:
        return 0.0
    return float(20.0 * np.log10(peak / rms))


def mid_side_ratio(audio_array: np.ndarray) -> float:
    audio = _as_float_audio(audio_array)
    if audio.ndim == 1 or audio.shape[1] < 2:
        return 1.0
    left = audio[:, 0]
    right = audio[:, 1]
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms = float(np.sqrt(np.mean(np.square(mid))))
    side_rms = float(np.sqrt(np.mean(np.square(side))))
    return float(mid_rms / max(mid_rms + side_rms, EPSILON))


def _as_float_audio(audio_array: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio_array, dtype=np.float64)
    if audio.ndim > 2:
        raise ValueError("audio_array must be mono or stereo")
    return np.nan_to_num(audio)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return np.mean(audio, axis=1)


def _power_spectrum(mono: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    if len(mono) < 2:
        return np.array([0.0]), np.array([EPSILON])
    window = np.hanning(len(mono))
    spectrum = np.fft.rfft(mono * window)
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sample_rate)
    power = np.square(np.abs(spectrum)) + EPSILON
    return freqs, power


def _band_powers(
    bands: Iterable[tuple[float, float, str]],
    freqs: np.ndarray,
    spectrum_power: np.ndarray,
    spectrum_total_db: float,
) -> List[BandPower]:
    result = []
    for low_hz, high_hz, label in bands:
        mask = (freqs >= low_hz) & (freqs < high_hz)
        power = float(np.sum(spectrum_power[mask])) if np.any(mask) else EPSILON
        power_db = _power_to_db(power)
        result.append(
            BandPower(
                low_hz=float(low_hz),
                high_hz=float(high_hz),
                label=label,
                power_db=power_db,
                normalized_db=power_db - spectrum_total_db,
            )
        )
    return result


def _third_octave_ranges() -> List[tuple[float, float, str]]:
    ratio = 2.0 ** (1.0 / 6.0)
    bands = []
    for center in ISO_THIRD_OCTAVE_CENTERS:
        low = center / ratio
        high = center * ratio
        bands.append((low, high, _hz_label(low, high)))
    return bands


def _spectral_shape(mono: np.ndarray, sample_rate: int) -> tuple[float, float]:
    try:
        import librosa

        centroid = librosa.feature.spectral_centroid(y=mono, sr=sample_rate)[0]
        bandwidth = librosa.feature.spectral_bandwidth(y=mono, sr=sample_rate)[0]
        return float(np.mean(centroid)), float(np.mean(bandwidth))
    except Exception:
        freqs, power = _power_spectrum(mono, sample_rate)
        total = float(np.sum(power))
        centroid = float(np.sum(freqs * power) / max(total, EPSILON))
        bandwidth = float(
            np.sqrt(np.sum(np.square(freqs - centroid) * power) / max(total, EPSILON))
        )
        return centroid, bandwidth


def _differences_by_label(a_bands: List[BandPower], b_bands: List[BandPower]) -> Dict[str, float]:
    reference_by_label = {band.label: band for band in b_bands}
    return {
        band.label: float(band.normalized_db - reference_by_label[band.label].normalized_db)
        for band in a_bands
        if band.label in reference_by_label
    }


def _suggestions_by_category(suggestions: List[Suggestion]) -> Dict[str, List[Suggestion]]:
    grouped: Dict[str, List[Suggestion]] = {}
    for suggestion in suggestions:
        grouped.setdefault(suggestion.category, []).append(suggestion)
    return grouped


def _power_to_db(power: float) -> float:
    return float(10.0 * np.log10(max(power, EPSILON)))


def _rounded_half_db(value: float) -> float:
    return round(value * 2.0) / 2.0


def _band_reason(label: str, diff_db: float) -> str:
    more = diff_db > 0
    reasons = {
        "60-80 Hz": ("more sub", "less sub"),
        "80-160 Hz": ("more low-body", "less low-body"),
        "160-320 Hz": ("low-mid build-up", "low-mid dip"),
        "320-630 Hz": ("more mud / box", "less body in the box range"),
        "630-1.25k": ("more midrange", "less midrange"),
        "1.25-2.5k": ("more low presence", "less low presence"),
        "2.5-5k": ("more upper presence", "less upper presence"),
        "5-10k": ("more brilliance", "less brilliance"),
        "10-16k": ("more air", "less air"),
    }
    return reasons.get(label, ("higher than reference", "lower than reference"))[0 if more else 1]


def _format_band_note(label: str, diff_db: float) -> str:
    if abs(diff_db) < SUGGESTION_THRESHOLD_DB:
        return ""
    return f"    ({_band_reason(label, diff_db)})"


def _crest_note(diff_db: float) -> str:
    if diff_db > SUGGESTION_THRESHOLD_DB:
        return "your vocal is significantly less compressed"
    if diff_db < -SUGGESTION_THRESHOLD_DB:
        return "your vocal is significantly more compressed"
    return "similar compression / peak control"


def _width_note(ratio: float) -> str:
    if ratio < 0.65:
        return "notably wide"
    if ratio > 0.85:
        return "mostly centered"
    return "moderately centered"


def _stereo_difference_note(diff: float) -> str:
    if diff < -0.10:
        return "Your vocal is wider / less focused than the reference."
    if diff > 0.10:
        return "Your vocal is narrower / more centered than the reference."
    return "Stereo focus is close to the reference."


def _brightness_note(diff_hz: float) -> str:
    if abs(diff_hz) < 100.0:
        return "Centroid brightness is close to the reference."
    if diff_hz < 0:
        return f"Reference is brighter by ~{abs(diff_hz):,.0f} Hz of centroid shift."
    return f"Yours is brighter by ~{diff_hz:,.0f} Hz of centroid shift."


def _hz_label(low_hz: float, high_hz: float) -> str:
    def fmt(value: float) -> str:
        if value >= 1000:
            return f"{value / 1000:g}k"
        return f"{value:.0f}"

    return f"{fmt(low_hz)}-{fmt(high_hz)} Hz"

