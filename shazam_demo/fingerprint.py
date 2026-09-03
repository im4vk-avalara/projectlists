"""
Audio Fingerprinting Module

This module implements the core Shazam-style fingerprinting algorithm:
1. Compute spectrogram
2. Find peaks (constellation map)
3. Generate fingerprints by pairing peaks (combinatorial hashing)
"""

import numpy as np
from typing import List, Tuple, Dict, Optional, NamedTuple
from dataclasses import dataclass
from scipy import ndimage
from scipy import signal as sig
import warnings

# =============================================================================
# Configuration
# =============================================================================

@dataclass
class FingerprintConfig:
    """Configuration parameters for fingerprinting."""
    
    # Audio
    sample_rate: int = 11025
    
    # STFT parameters
    n_fft: int = 2048          # FFT window size (~186ms at 11025 Hz)
    hop_length: int = 512      # Hop between windows (~46ms)
    window: str = 'hann'       # Window function
    
    # Peak picking
    peak_neighborhood_time: int = 20    # Frames for local max detection
    peak_neighborhood_freq: int = 20    # Frequency bins for local max
    min_amplitude_db: float = 10.0      # dB above noise floor
    max_peaks_per_frame: int = 5        # Limit peak density
    
    # Combinatorial hashing (fan-out)
    fan_out: int = 15                   # Targets per anchor
    target_t_min: int = 1               # Min time delta (frames)
    target_t_max: int = 100             # Max time delta (frames)
    target_f_range: int = 50            # Frequency range for targets (bins)
    
    # Hash quantization
    freq_bits: int = 10                 # Bits for frequency (0-1023)
    time_bits: int = 10                 # Bits for time delta (0-1023)
    
    @property
    def n_freq_bins(self) -> int:
        """Number of frequency bins in spectrogram."""
        return self.n_fft // 2 + 1
    
    @property
    def frame_duration(self) -> float:
        """Duration of each frame in seconds."""
        return self.hop_length / self.sample_rate
    
    def __repr__(self):
        return (
            f"FingerprintConfig(\n"
            f"  sample_rate={self.sample_rate}, n_fft={self.n_fft}, "
            f"hop_length={self.hop_length}\n"
            f"  peak_neighborhood=({self.peak_neighborhood_time}, "
            f"{self.peak_neighborhood_freq})\n"
            f"  fan_out={self.fan_out}, "
            f"target_t=({self.target_t_min}, {self.target_t_max})\n"
            f")"
        )


# Default configuration
DEFAULT_CONFIG = FingerprintConfig()


# =============================================================================
# Data Structures
# =============================================================================

class Peak(NamedTuple):
    """A peak in the spectrogram."""
    time: int       # Frame index
    freq: int       # Frequency bin index
    amplitude: float  # Magnitude (dB)


class Fingerprint(NamedTuple):
    """A fingerprint (hash + anchor time)."""
    hash: int       # The hash value
    time: int       # Anchor time (frame index)


# =============================================================================
# Spectrogram
# =============================================================================

def compute_spectrogram(
    audio: np.ndarray,
    config: FingerprintConfig = DEFAULT_CONFIG
) -> np.ndarray:
    """
    Compute log-magnitude spectrogram.
    
    Parameters
    ----------
    audio : np.ndarray
        Audio samples (mono, float32)
    config : FingerprintConfig
        Configuration parameters
    
    Returns
    -------
    spectrogram : np.ndarray
        Log-magnitude spectrogram, shape (n_freq_bins, n_frames)
        Values are in dB.
    """
    # Get window function
    if config.window == 'hann':
        window = sig.windows.hann(config.n_fft)
    elif config.window == 'hamming':
        window = sig.windows.hamming(config.n_fft)
    else:
        window = sig.windows.hann(config.n_fft)
    
    # Compute STFT
    # Using scipy.signal.stft
    f, t, Zxx = sig.stft(
        audio,
        fs=config.sample_rate,
        window=window,
        nperseg=config.n_fft,
        noverlap=config.n_fft - config.hop_length,
        nfft=config.n_fft
    )
    
    # Convert to magnitude spectrogram
    magnitude = np.abs(Zxx)
    
    # Convert to dB (log scale)
    # Add small epsilon to avoid log(0)
    eps = 1e-10
    spectrogram_db = 20 * np.log10(magnitude + eps)
    
    return spectrogram_db


def spectrogram_to_image(spectrogram: np.ndarray) -> np.ndarray:
    """
    Normalize spectrogram for visualization.
    
    Parameters
    ----------
    spectrogram : np.ndarray
        Log-magnitude spectrogram in dB
    
    Returns
    -------
    image : np.ndarray
        Normalized spectrogram (0-1 range)
    """
    # Clip to reasonable range
    spec = spectrogram.copy()
    spec = np.clip(spec, -80, 0)  # -80 dB to 0 dB
    
    # Normalize to 0-1
    spec = (spec + 80) / 80
    
    return spec


# =============================================================================
# Peak Picking
# =============================================================================

def find_peaks(
    spectrogram: np.ndarray,
    config: FingerprintConfig = DEFAULT_CONFIG
) -> List[Peak]:
    """
    Find local maxima in the spectrogram (constellation map).
    
    Parameters
    ----------
    spectrogram : np.ndarray
        Log-magnitude spectrogram, shape (n_freq, n_frames)
    config : FingerprintConfig
        Configuration parameters
    
    Returns
    -------
    peaks : List[Peak]
        List of peaks sorted by time
    """
    n_freq, n_frames = spectrogram.shape
    
    # Compute noise floor (e.g., 10th percentile)
    noise_floor = np.percentile(spectrogram, 10)
    threshold = noise_floor + config.min_amplitude_db
    
    # Create local max filter
    # Neighborhood size: (freq, time)
    neighborhood_size = (
        2 * config.peak_neighborhood_freq + 1,
        2 * config.peak_neighborhood_time + 1
    )
    
    # Find local maxima using maximum filter
    local_max = ndimage.maximum_filter(
        spectrogram,
        size=neighborhood_size,
        mode='constant',
        cval=-np.inf
    )
    
    # Points that are local maxima AND above threshold
    is_peak = (spectrogram == local_max) & (spectrogram > threshold)
    
    # Extract peak coordinates
    freq_indices, time_indices = np.where(is_peak)
    
    # Create peak list
    peaks = []
    for f, t in zip(freq_indices, time_indices):
        amp = spectrogram[f, t]
        peaks.append(Peak(time=int(t), freq=int(f), amplitude=float(amp)))
    
    # Sort by time, then by amplitude (descending)
    peaks.sort(key=lambda p: (p.time, -p.amplitude))
    
    # Limit peaks per frame
    if config.max_peaks_per_frame > 0:
        filtered_peaks = []
        current_frame = -1
        frame_count = 0
        
        for peak in peaks:
            if peak.time != current_frame:
                current_frame = peak.time
                frame_count = 0
            
            if frame_count < config.max_peaks_per_frame:
                filtered_peaks.append(peak)
                frame_count += 1
        
        peaks = filtered_peaks
    
    return peaks


# =============================================================================
# Combinatorial Hashing
# =============================================================================

def create_hash(
    f1: int,
    f2: int,
    dt: int,
    config: FingerprintConfig = DEFAULT_CONFIG
) -> int:
    """
    Create a hash from anchor frequency, target frequency, and time delta.
    
    Hash structure (32-bit):
    - Bits 20-29: f1 (anchor frequency, 10 bits)
    - Bits 10-19: f2 (target frequency, 10 bits)
    - Bits 0-9:   dt (time delta, 10 bits)
    
    Parameters
    ----------
    f1 : int
        Anchor frequency bin
    f2 : int
        Target frequency bin
    dt : int
        Time delta in frames
    config : FingerprintConfig
        Configuration parameters
    
    Returns
    -------
    hash : int
        32-bit hash value
    """
    # Quantize to bit ranges
    max_freq = (1 << config.freq_bits) - 1
    max_time = (1 << config.time_bits) - 1
    
    f1_q = min(f1, max_freq)
    f2_q = min(f2, max_freq)
    dt_q = min(max(0, dt), max_time)
    
    # Combine into hash
    hash_val = (f1_q << (config.freq_bits + config.time_bits)) | \
               (f2_q << config.time_bits) | \
               dt_q
    
    return hash_val


def decode_hash(
    hash_val: int,
    config: FingerprintConfig = DEFAULT_CONFIG
) -> Tuple[int, int, int]:
    """
    Decode a hash back to (f1, f2, dt).
    
    Parameters
    ----------
    hash_val : int
        Hash value
    config : FingerprintConfig
        Configuration parameters
    
    Returns
    -------
    f1, f2, dt : Tuple[int, int, int]
        Anchor frequency, target frequency, time delta
    """
    mask_freq = (1 << config.freq_bits) - 1
    mask_time = (1 << config.time_bits) - 1
    
    dt = hash_val & mask_time
    f2 = (hash_val >> config.time_bits) & mask_freq
    f1 = (hash_val >> (config.freq_bits + config.time_bits)) & mask_freq
    
    return f1, f2, dt


def generate_fingerprints(
    peaks: List[Peak],
    config: FingerprintConfig = DEFAULT_CONFIG
) -> List[Fingerprint]:
    """
    Generate fingerprints by pairing peaks (fan-out hashing).
    
    For each anchor peak, find target peaks within the fan-out window
    and create hash pairs.
    
    Parameters
    ----------
    peaks : List[Peak]
        List of peaks from constellation map
    config : FingerprintConfig
        Configuration parameters
    
    Returns
    -------
    fingerprints : List[Fingerprint]
        List of fingerprints (hash, anchor_time)
    """
    fingerprints = []
    n_peaks = len(peaks)
    
    # Sort peaks by time for efficient target search
    peaks_by_time = sorted(peaks, key=lambda p: p.time)
    
    for i, anchor in enumerate(peaks_by_time):
        targets_found = 0
        
        # Search forward for targets
        for j in range(i + 1, n_peaks):
            if targets_found >= config.fan_out:
                break
            
            target = peaks_by_time[j]
            
            # Check time constraint
            dt = target.time - anchor.time
            if dt < config.target_t_min:
                continue
            if dt > config.target_t_max:
                break  # All subsequent peaks are too far
            
            # Check frequency constraint
            df = abs(target.freq - anchor.freq)
            if df > config.target_f_range:
                continue
            
            # Create fingerprint
            hash_val = create_hash(anchor.freq, target.freq, dt, config)
            fp = Fingerprint(hash=hash_val, time=anchor.time)
            fingerprints.append(fp)
            targets_found += 1
    
    return fingerprints


# =============================================================================
# High-Level API
# =============================================================================

def fingerprint_audio(
    audio: np.ndarray,
    config: FingerprintConfig = DEFAULT_CONFIG,
    return_intermediate: bool = False
) -> Dict:
    """
    Compute fingerprints for an audio signal.
    
    Parameters
    ----------
    audio : np.ndarray
        Audio samples (mono, float32)
    config : FingerprintConfig
        Configuration parameters
    return_intermediate : bool
        If True, return spectrogram and peaks as well
    
    Returns
    -------
    result : dict
        Dictionary containing:
        - 'fingerprints': List[Fingerprint]
        - 'spectrogram': np.ndarray (if return_intermediate)
        - 'peaks': List[Peak] (if return_intermediate)
    """
    # Compute spectrogram
    spectrogram = compute_spectrogram(audio, config)
    
    # Find peaks
    peaks = find_peaks(spectrogram, config)
    
    # Generate fingerprints
    fingerprints = generate_fingerprints(peaks, config)
    
    result = {
        'fingerprints': fingerprints,
        'n_fingerprints': len(fingerprints),
        'n_peaks': len(peaks),
        'duration_frames': spectrogram.shape[1],
        'duration_seconds': spectrogram.shape[1] * config.hop_length / config.sample_rate
    }
    
    if return_intermediate:
        result['spectrogram'] = spectrogram
        result['peaks'] = peaks
    
    return result


def fingerprint_file(
    filepath: str,
    config: FingerprintConfig = DEFAULT_CONFIG,
    return_intermediate: bool = False
) -> Dict:
    """
    Compute fingerprints for an audio file.
    
    Parameters
    ----------
    filepath : str
        Path to audio file
    config : FingerprintConfig
        Configuration parameters
    return_intermediate : bool
        If True, return spectrogram and peaks as well
    
    Returns
    -------
    result : dict
        Same as fingerprint_audio()
    """
    from audio_utils import load_audio
    
    audio, sr = load_audio(filepath, sr=config.sample_rate)
    return fingerprint_audio(audio, config, return_intermediate)


# =============================================================================
# Visualization
# =============================================================================

def plot_spectrogram(
    spectrogram: np.ndarray,
    config: FingerprintConfig = DEFAULT_CONFIG,
    ax=None,
    title: str = "Spectrogram"
):
    """
    Plot the spectrogram as a heatmap.
    
    Parameters
    ----------
    spectrogram : np.ndarray
        Log-magnitude spectrogram
    config : FingerprintConfig
        Configuration parameters
    ax : matplotlib.axes.Axes or None
        Axes to plot on
    title : str
        Plot title
    """
    import matplotlib.pyplot as plt
    
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 6))
    
    # Time and frequency axes
    n_freq, n_frames = spectrogram.shape
    times = np.arange(n_frames) * config.hop_length / config.sample_rate
    freqs = np.arange(n_freq) * config.sample_rate / config.n_fft
    
    # Plot
    img = ax.imshow(
        spectrogram,
        aspect='auto',
        origin='lower',
        extent=[times[0], times[-1], freqs[0], freqs[-1]],
        cmap='magma',
        vmin=-80,
        vmax=0
    )
    
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Frequency (Hz)')
    ax.set_title(title)
    
    # Colorbar
    plt.colorbar(img, ax=ax, label='Magnitude (dB)')
    
    return ax


def plot_constellation(
    spectrogram: np.ndarray,
    peaks: List[Peak],
    config: FingerprintConfig = DEFAULT_CONFIG,
    ax=None,
    title: str = "Constellation Map"
):
    """
    Plot the spectrogram with peaks overlaid.
    
    Parameters
    ----------
    spectrogram : np.ndarray
        Log-magnitude spectrogram
    peaks : List[Peak]
        List of peaks
    config : FingerprintConfig
        Configuration parameters
    ax : matplotlib.axes.Axes or None
        Axes to plot on
    title : str
        Plot title
    """
    import matplotlib.pyplot as plt
    
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 6))
    
    # Time and frequency axes
    n_freq, n_frames = spectrogram.shape
    times = np.arange(n_frames) * config.hop_length / config.sample_rate
    freqs = np.arange(n_freq) * config.sample_rate / config.n_fft
    
    # Plot spectrogram
    ax.imshow(
        spectrogram,
        aspect='auto',
        origin='lower',
        extent=[times[0], times[-1], freqs[0], freqs[-1]],
        cmap='gray_r',
        alpha=0.7,
        vmin=-80,
        vmax=0
    )
    
    # Plot peaks
    peak_times = [p.time * config.hop_length / config.sample_rate for p in peaks]
    peak_freqs = [p.freq * config.sample_rate / config.n_fft for p in peaks]
    
    ax.scatter(peak_times, peak_freqs, c='red', s=5, alpha=0.8, marker='o')
    
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Frequency (Hz)')
    ax.set_title(f"{title} ({len(peaks)} peaks)")
    
    return ax


def plot_hash_pairs(
    peaks: List[Peak],
    config: FingerprintConfig = DEFAULT_CONFIG,
    ax=None,
    max_anchors: int = 5,
    title: str = "Hash Pairs (Fan-out)"
):
    """
    Visualize how peaks are paired into hashes.
    
    Parameters
    ----------
    peaks : List[Peak]
        List of peaks
    config : FingerprintConfig
        Configuration parameters
    ax : matplotlib.axes.Axes or None
        Axes to plot on
    max_anchors : int
        Maximum number of anchor points to show connections for
    title : str
        Plot title
    """
    import matplotlib.pyplot as plt
    
    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 6))
    
    # Sort peaks by time
    peaks_by_time = sorted(peaks, key=lambda p: p.time)
    
    # Plot all peaks
    peak_times = [p.time * config.hop_length / config.sample_rate for p in peaks]
    peak_freqs = [p.freq * config.sample_rate / config.n_fft for p in peaks]
    ax.scatter(peak_times, peak_freqs, c='gray', s=20, alpha=0.5, zorder=1)
    
    # Draw connections for first few anchors
    colors = plt.cm.tab10(np.linspace(0, 1, max_anchors))
    anchor_count = 0
    
    for i, anchor in enumerate(peaks_by_time):
        if anchor_count >= max_anchors:
            break
        
        targets_found = 0
        color = colors[anchor_count]
        
        # Find targets
        for j in range(i + 1, len(peaks_by_time)):
            if targets_found >= config.fan_out:
                break
            
            target = peaks_by_time[j]
            dt = target.time - anchor.time
            
            if dt < config.target_t_min:
                continue
            if dt > config.target_t_max:
                break
            
            df = abs(target.freq - anchor.freq)
            if df > config.target_f_range:
                continue
            
            # Draw line from anchor to target
            t1 = anchor.time * config.hop_length / config.sample_rate
            f1 = anchor.freq * config.sample_rate / config.n_fft
            t2 = target.time * config.hop_length / config.sample_rate
            f2 = target.freq * config.sample_rate / config.n_fft
            
            ax.plot([t1, t2], [f1, f2], c=color, alpha=0.6, linewidth=1, zorder=2)
            targets_found += 1
        
        # Mark anchor
        t1 = anchor.time * config.hop_length / config.sample_rate
        f1 = anchor.freq * config.sample_rate / config.n_fft
        ax.scatter([t1], [f1], c=[color], s=100, marker='*', zorder=3, 
                   edgecolors='black', linewidth=0.5)
        
        anchor_count += 1
    
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Frequency (Hz)')
    ax.set_title(title)
    
    return ax


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    print("Fingerprint Module Test")
    print("=" * 50)
    print(f"\nDefault config:\n{DEFAULT_CONFIG}")
    
    # Generate test signal
    sr = DEFAULT_CONFIG.sample_rate
    duration = 5.0  # seconds
    t = np.arange(int(sr * duration)) / sr
    
    # Simple test signal: two tones
    audio = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 880 * t)
    audio = audio.astype(np.float32)
    
    print(f"\nTest signal: {duration}s, {len(audio)} samples")
    
    # Compute fingerprints
    result = fingerprint_audio(audio, return_intermediate=True)
    
    print(f"Spectrogram shape: {result['spectrogram'].shape}")
    print(f"Peaks found: {result['n_peaks']}")
    print(f"Fingerprints generated: {result['n_fingerprints']}")
    
    # Show example hashes
    if result['fingerprints']:
        print("\nExample fingerprints:")
        for fp in result['fingerprints'][:5]:
            f1, f2, dt = decode_hash(fp.hash)
            print(f"  Hash={fp.hash:08x}, anchor_time={fp.time}, "
                  f"decoded=(f1={f1}, f2={f2}, dt={dt})")
