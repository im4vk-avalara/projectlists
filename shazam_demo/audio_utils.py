"""
Audio Utilities for Shazam-style Audio Fingerprinting

This module handles audio loading, resampling, and normalization.
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional
import warnings

# Try to import librosa for audio loading
try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    warnings.warn("librosa not installed. Install with: pip install librosa")

# Try scipy.io.wavfile as fallback
try:
    from scipy.io import wavfile
    from scipy import signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# =============================================================================
# Constants
# =============================================================================

DEFAULT_SAMPLE_RATE = 11025  # Hz - sufficient for music fingerprinting
DEFAULT_DURATION = None       # None = load full track


# =============================================================================
# Audio Loading Functions
# =============================================================================

def load_audio(
    filepath: str,
    sr: int = DEFAULT_SAMPLE_RATE,
    mono: bool = True,
    duration: Optional[float] = None,
    offset: float = 0.0
) -> Tuple[np.ndarray, int]:
    """
    Load an audio file and convert to mono at specified sample rate.
    
    Parameters
    ----------
    filepath : str
        Path to audio file (mp3, wav, flac, ogg, etc.)
    sr : int
        Target sample rate in Hz
    mono : bool
        If True, convert to mono
    duration : float or None
        Duration in seconds to load. None = full track.
    offset : float
        Start reading at this time (seconds)
    
    Returns
    -------
    audio : np.ndarray
        Audio samples as float32 array, normalized to [-1, 1]
    sr : int
        Sample rate (same as input sr)
    
    Examples
    --------
    >>> audio, sr = load_audio("song.mp3")
    >>> print(f"Loaded {len(audio)/sr:.2f} seconds at {sr} Hz")
    """
    filepath = str(filepath)
    
    if HAS_LIBROSA:
        # Librosa handles most formats via soundfile/audioread
        audio, sr_loaded = librosa.load(
            filepath,
            sr=sr,
            mono=mono,
            duration=duration,
            offset=offset
        )
        return audio.astype(np.float32), sr
    
    elif HAS_SCIPY and filepath.lower().endswith('.wav'):
        # Fallback for WAV files using scipy
        sr_orig, audio = wavfile.read(filepath)
        
        # Convert to float32
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.int32:
            audio = audio.astype(np.float32) / 2147483648.0
        elif audio.dtype == np.uint8:
            audio = (audio.astype(np.float32) - 128) / 128.0
        else:
            audio = audio.astype(np.float32)
        
        # Convert to mono
        if mono and len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)
        
        # Resample if needed
        if sr_orig != sr:
            num_samples = int(len(audio) * sr / sr_orig)
            audio = signal.resample(audio, num_samples)
        
        # Apply offset and duration
        if offset > 0:
            start_sample = int(offset * sr)
            audio = audio[start_sample:]
        if duration is not None:
            end_sample = int(duration * sr)
            audio = audio[:end_sample]
        
        return audio.astype(np.float32), sr
    
    else:
        raise ImportError(
            "No audio loading library available. "
            "Install librosa: pip install librosa"
        )


def load_audio_segment(
    filepath: str,
    start_time: float,
    duration: float,
    sr: int = DEFAULT_SAMPLE_RATE
) -> Tuple[np.ndarray, int]:
    """
    Load a specific segment of an audio file.
    
    Parameters
    ----------
    filepath : str
        Path to audio file
    start_time : float
        Start time in seconds
    duration : float
        Duration in seconds
    sr : int
        Target sample rate
    
    Returns
    -------
    audio : np.ndarray
        Audio segment
    sr : int
        Sample rate
    """
    return load_audio(filepath, sr=sr, duration=duration, offset=start_time)


# =============================================================================
# Audio Preprocessing
# =============================================================================

def normalize_audio(audio: np.ndarray, target_db: float = -3.0) -> np.ndarray:
    """
    Normalize audio to target peak dB level.
    
    Parameters
    ----------
    audio : np.ndarray
        Input audio
    target_db : float
        Target peak level in dB (default: -3 dB)
    
    Returns
    -------
    audio : np.ndarray
        Normalized audio
    """
    peak = np.max(np.abs(audio))
    if peak > 0:
        target_linear = 10 ** (target_db / 20.0)
        audio = audio * (target_linear / peak)
    return audio


def add_noise(
    audio: np.ndarray,
    snr_db: float = 10.0,
    noise_type: str = 'white'
) -> np.ndarray:
    """
    Add noise to audio for testing robustness.
    
    Parameters
    ----------
    audio : np.ndarray
        Clean audio signal
    snr_db : float
        Signal-to-noise ratio in dB
    noise_type : str
        Type of noise: 'white', 'pink', or 'brown'
    
    Returns
    -------
    noisy_audio : np.ndarray
        Audio with added noise
    """
    # Calculate signal power
    signal_power = np.mean(audio ** 2)
    
    # Generate noise
    if noise_type == 'white':
        noise = np.random.randn(len(audio))
    elif noise_type == 'pink':
        # Simple pink noise approximation
        white = np.random.randn(len(audio))
        # Apply 1/f filter in frequency domain
        fft = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(len(white))
        freqs[0] = 1e-10  # Avoid division by zero
        fft = fft / np.sqrt(freqs)
        noise = np.fft.irfft(fft, n=len(audio))
    elif noise_type == 'brown':
        # Brownian noise (cumulative white noise)
        noise = np.cumsum(np.random.randn(len(audio)))
        noise = noise - np.mean(noise)
    else:
        raise ValueError(f"Unknown noise type: {noise_type}")
    
    # Normalize noise to unit power
    noise = noise / np.sqrt(np.mean(noise ** 2))
    
    # Calculate noise power for desired SNR
    # SNR = 10 * log10(signal_power / noise_power)
    noise_power = signal_power / (10 ** (snr_db / 10.0))
    noise = noise * np.sqrt(noise_power)
    
    return audio + noise


def simulate_recording(
    audio: np.ndarray,
    sr: int = DEFAULT_SAMPLE_RATE,
    snr_db: float = 15.0,
    lowpass_hz: float = 4000.0,
    highpass_hz: float = 100.0
) -> np.ndarray:
    """
    Simulate recording through a microphone (adds noise + frequency filtering).
    
    Parameters
    ----------
    audio : np.ndarray
        Clean audio
    sr : int
        Sample rate
    snr_db : float
        Signal-to-noise ratio
    lowpass_hz : float
        Low-pass filter cutoff (simulates speaker/mic limitations)
    highpass_hz : float
        High-pass filter cutoff (removes DC and low rumble)
    
    Returns
    -------
    recorded : np.ndarray
        Simulated recording
    """
    from scipy import signal as sig
    
    # Apply bandpass filter
    nyquist = sr / 2.0
    low = highpass_hz / nyquist
    high = lowpass_hz / nyquist
    
    # Clamp to valid range
    low = max(0.01, min(low, 0.99))
    high = max(0.01, min(high, 0.99))
    
    if low < high:
        b, a = sig.butter(4, [low, high], btype='band')
        audio = sig.filtfilt(b, a, audio)
    
    # Add noise
    audio = add_noise(audio, snr_db=snr_db, noise_type='white')
    
    # Normalize
    audio = normalize_audio(audio)
    
    return audio.astype(np.float32)


# =============================================================================
# Utility Functions
# =============================================================================

def get_audio_duration(filepath: str) -> float:
    """
    Get the duration of an audio file in seconds.
    
    Parameters
    ----------
    filepath : str
        Path to audio file
    
    Returns
    -------
    duration : float
        Duration in seconds
    """
    if HAS_LIBROSA:
        return librosa.get_duration(path=filepath)
    else:
        audio, sr = load_audio(filepath)
        return len(audio) / sr


def get_supported_formats() -> list:
    """
    Get list of supported audio formats.
    
    Returns
    -------
    formats : list
        List of supported file extensions
    """
    if HAS_LIBROSA:
        return ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.wma', '.aac']
    elif HAS_SCIPY:
        return ['.wav']
    else:
        return []


def is_audio_file(filepath: str) -> bool:
    """
    Check if a file is a supported audio format.
    
    Parameters
    ----------
    filepath : str
        Path to file
    
    Returns
    -------
    is_audio : bool
        True if file is a supported audio format
    """
    ext = Path(filepath).suffix.lower()
    return ext in get_supported_formats()


def find_audio_files(directory: str, recursive: bool = True) -> list:
    """
    Find all audio files in a directory.
    
    Parameters
    ----------
    directory : str
        Directory to search
    recursive : bool
        If True, search subdirectories
    
    Returns
    -------
    files : list
        List of paths to audio files
    """
    directory = Path(directory)
    audio_files = []
    
    pattern = '**/*' if recursive else '*'
    for fmt in get_supported_formats():
        audio_files.extend(directory.glob(f'{pattern}{fmt}'))
    
    return sorted([str(f) for f in audio_files])


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    print("Audio Utilities Module")
    print("=" * 50)
    print(f"librosa available: {HAS_LIBROSA}")
    print(f"scipy available: {HAS_SCIPY}")
    print(f"Supported formats: {get_supported_formats()}")
    print(f"Default sample rate: {DEFAULT_SAMPLE_RATE} Hz")
    
    # Test noise generation
    print("\nTesting noise generation...")
    test_signal = np.sin(2 * np.pi * 440 * np.arange(11025) / 11025)
    noisy = add_noise(test_signal, snr_db=10)
    print(f"  Clean signal RMS: {np.sqrt(np.mean(test_signal**2)):.4f}")
    print(f"  Noisy signal RMS: {np.sqrt(np.mean(noisy**2)):.4f}")
    print("  Noise added successfully!")
