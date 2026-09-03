#!/usr/bin/env python3
"""
Shazam-Style Audio Fingerprinting Demo

This script provides a visual walkthrough of the audio fingerprinting algorithm:
1. Load audio and compute spectrogram
2. Find peaks (constellation map)
3. Generate fingerprint hashes
4. Build a small database
5. Test recognition with noisy query

Usage:
    python demo.py                          # Run with synthetic audio
    python demo.py --music_dir ./music      # Run with your audio files
    python demo.py --audio_file song.mp3    # Analyze a single file
"""

import argparse
import sys
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import random

# Local imports
from audio_utils import (
    load_audio, add_noise, simulate_recording, 
    find_audio_files, DEFAULT_SAMPLE_RATE
)
from fingerprint import (
    compute_spectrogram, find_peaks, generate_fingerprints,
    fingerprint_audio, FingerprintConfig, DEFAULT_CONFIG,
    plot_spectrogram, plot_constellation, plot_hash_pairs,
    decode_hash
)
from db import (
    InMemoryDatabase, SQLiteDatabase, match_fingerprints,
    plot_match_histogram
)


# =============================================================================
# Synthetic Audio Generation
# =============================================================================

def generate_synthetic_track(
    duration: float = 30.0,
    sr: int = DEFAULT_SAMPLE_RATE,
    n_harmonics: int = 5,
    seed: int = None
) -> np.ndarray:
    """
    Generate a synthetic audio track with harmonic content.
    
    Creates music-like audio by combining:
    - Multiple harmonic series with different fundamentals
    - Time-varying amplitudes (envelopes)
    - Some noise for texture
    
    Parameters
    ----------
    duration : float
        Duration in seconds
    sr : int
        Sample rate
    n_harmonics : int
        Number of harmonics per note
    seed : int or None
        Random seed for reproducibility
    
    Returns
    -------
    audio : np.ndarray
        Synthetic audio signal
    """
    if seed is not None:
        np.random.seed(seed)
    
    n_samples = int(duration * sr)
    t = np.arange(n_samples) / sr
    audio = np.zeros(n_samples, dtype=np.float32)
    
    # Generate several "notes" with different start times and frequencies
    n_notes = int(duration * 2)  # ~2 notes per second
    
    for _ in range(n_notes):
        # Random note parameters
        start = np.random.uniform(0, duration - 1)
        note_duration = np.random.uniform(0.5, 2.0)
        fundamental = np.random.uniform(100, 800)  # Hz
        amplitude = np.random.uniform(0.1, 0.3)
        
        # Generate note samples
        start_idx = int(start * sr)
        end_idx = min(start_idx + int(note_duration * sr), n_samples)
        note_t = np.arange(end_idx - start_idx) / sr
        
        # Create envelope (attack-decay-sustain-release)
        env_len = len(note_t)
        attack = int(env_len * 0.1)
        decay = int(env_len * 0.2)
        release = int(env_len * 0.3)
        
        envelope = np.ones(env_len)
        envelope[:attack] = np.linspace(0, 1, attack)
        envelope[attack:attack+decay] = np.linspace(1, 0.7, decay)
        envelope[-release:] = np.linspace(0.7, 0, release)
        
        # Generate harmonics
        note = np.zeros(env_len)
        for h in range(1, n_harmonics + 1):
            freq = fundamental * h
            if freq < sr / 2:  # Below Nyquist
                harm_amp = amplitude / h  # Decreasing amplitude for higher harmonics
                note += harm_amp * np.sin(2 * np.pi * freq * note_t)
        
        # Apply envelope and add to audio
        audio[start_idx:end_idx] += note * envelope
    
    # Normalize
    audio = audio / (np.max(np.abs(audio)) + 1e-10) * 0.8
    
    return audio.astype(np.float32)


def generate_synthetic_dataset(
    n_tracks: int = 5,
    duration: float = 30.0,
    sr: int = DEFAULT_SAMPLE_RATE
) -> dict:
    """
    Generate a dataset of synthetic tracks.
    
    Returns
    -------
    dataset : dict
        Dictionary with track names as keys and audio arrays as values
    """
    dataset = {}
    
    for i in range(n_tracks):
        name = f"synthetic_track_{i+1:02d}"
        audio = generate_synthetic_track(duration=duration, sr=sr, seed=i*42)
        dataset[name] = audio
    
    return dataset


# =============================================================================
# Demo Functions
# =============================================================================

def demo_single_track(audio: np.ndarray, name: str = "track", config: FingerprintConfig = DEFAULT_CONFIG):
    """
    Demonstrate fingerprinting on a single track with visualizations.
    
    Shows:
    1. Spectrogram
    2. Constellation map (peaks)
    3. Hash pair visualization
    4. Example fingerprints
    """
    print(f"\n{'='*60}")
    print(f"FINGERPRINTING: {name}")
    print(f"{'='*60}")
    
    duration = len(audio) / config.sample_rate
    print(f"Duration: {duration:.2f}s")
    print(f"Samples: {len(audio):,}")
    
    # Compute spectrogram
    print("\n[1] Computing spectrogram...")
    spectrogram = compute_spectrogram(audio, config)
    print(f"    Shape: {spectrogram.shape} (freq_bins x frames)")
    print(f"    Time resolution: {config.hop_length/config.sample_rate*1000:.1f}ms per frame")
    print(f"    Frequency resolution: {config.sample_rate/config.n_fft:.1f}Hz per bin")
    
    # Find peaks
    print("\n[2] Finding peaks (constellation map)...")
    peaks = find_peaks(spectrogram, config)
    print(f"    Peaks found: {len(peaks)}")
    print(f"    Peak density: {len(peaks)/duration:.1f} peaks/second")
    
    # Show some example peaks
    print("\n    Example peaks:")
    for peak in peaks[:5]:
        time_sec = peak.time * config.hop_length / config.sample_rate
        freq_hz = peak.freq * config.sample_rate / config.n_fft
        print(f"      t={time_sec:.2f}s, f={freq_hz:.0f}Hz, amp={peak.amplitude:.1f}dB")
    
    # Generate fingerprints
    print("\n[3] Generating fingerprints (hash pairs)...")
    fingerprints = generate_fingerprints(peaks, config)
    print(f"    Fingerprints generated: {len(fingerprints)}")
    print(f"    Fingerprint density: {len(fingerprints)/duration:.1f} fps/second")
    
    # Show example fingerprints
    print("\n    Example fingerprints:")
    for fp in fingerprints[:5]:
        f1, f2, dt = decode_hash(fp.hash, config)
        f1_hz = f1 * config.sample_rate / config.n_fft
        f2_hz = f2 * config.sample_rate / config.n_fft
        dt_sec = dt * config.hop_length / config.sample_rate
        print(f"      hash={fp.hash:08x}: anchor_f={f1_hz:.0f}Hz, "
              f"target_f={f2_hz:.0f}Hz, dt={dt_sec:.2f}s, anchor_t={fp.time}")
    
    # Create visualization
    print("\n[4] Creating visualizations...")
    
    fig = plt.figure(figsize=(16, 12))
    
    # Spectrogram
    ax1 = fig.add_subplot(2, 2, 1)
    plot_spectrogram(spectrogram, config, ax=ax1, title=f"Spectrogram: {name}")
    
    # Constellation map
    ax2 = fig.add_subplot(2, 2, 2)
    plot_constellation(spectrogram, peaks, config, ax=ax2, 
                       title=f"Constellation Map: {name}")
    
    # Hash pairs (first 3 seconds only for clarity)
    ax3 = fig.add_subplot(2, 2, 3)
    # Filter peaks to first 3 seconds
    max_time = int(3.0 * config.sample_rate / config.hop_length)
    early_peaks = [p for p in peaks if p.time < max_time]
    plot_hash_pairs(early_peaks, config, ax=ax3, max_anchors=8,
                    title="Hash Pairs (first 3s, 8 anchors)")
    
    # Fingerprint statistics
    ax4 = fig.add_subplot(2, 2, 4)
    
    # Histogram of hash values (mod 1000 for visualization)
    hash_mod = [fp.hash % 1000 for fp in fingerprints]
    ax4.hist(hash_mod, bins=50, alpha=0.7, color='blue')
    ax4.set_xlabel('Hash value (mod 1000)')
    ax4.set_ylabel('Count')
    ax4.set_title(f'Fingerprint Distribution ({len(fingerprints)} total)')
    
    plt.tight_layout()
    plt.savefig('demo_fingerprint.png', dpi=150, bbox_inches='tight')
    print("    Saved to: demo_fingerprint.png")
    
    return spectrogram, peaks, fingerprints


def demo_recognition(
    dataset: dict,
    config: FingerprintConfig = DEFAULT_CONFIG,
    query_duration: float = 10.0,
    snr_db: float = 15.0
):
    """
    Demonstrate full recognition pipeline.
    
    1. Build database from dataset
    2. Create noisy query from random track
    3. Recognize query
    4. Visualize results
    """
    print(f"\n{'='*60}")
    print("RECOGNITION DEMO")
    print(f"{'='*60}")
    
    # Build database
    print("\n[1] Building fingerprint database...")
    db = InMemoryDatabase()
    
    for name, audio in dataset.items():
        result = fingerprint_audio(audio, config)
        db.add_track(
            result['fingerprints'],
            filename=name,
            duration_seconds=len(audio) / config.sample_rate
        )
        print(f"    Added: {name} ({len(result['fingerprints'])} fingerprints)")
    
    stats = db.get_stats()
    print(f"\n    Total tracks: {stats['n_tracks']}")
    print(f"    Total fingerprints: {stats['n_fingerprints']:,}")
    print(f"    Unique hashes: {stats['n_unique_hashes']:,}")
    
    # Select random track for query
    print("\n[2] Creating query clip...")
    query_track_name = random.choice(list(dataset.keys()))
    query_audio_full = dataset[query_track_name]
    
    # Extract a segment from somewhere in the track
    full_duration = len(query_audio_full) / config.sample_rate
    max_start = max(0, full_duration - query_duration - 1)
    start_time = random.uniform(0, max_start) if max_start > 0 else 0
    
    start_sample = int(start_time * config.sample_rate)
    end_sample = start_sample + int(query_duration * config.sample_rate)
    query_audio_clean = query_audio_full[start_sample:end_sample]
    
    print(f"    Source track: {query_track_name}")
    print(f"    Segment: {start_time:.1f}s to {start_time + query_duration:.1f}s")
    
    # Add noise to simulate recording
    print(f"\n[3] Adding noise (SNR = {snr_db} dB)...")
    query_audio = simulate_recording(query_audio_clean, config.sample_rate, snr_db=snr_db)
    
    # Fingerprint query
    print("\n[4] Fingerprinting query...")
    query_result = fingerprint_audio(query_audio, config, return_intermediate=True)
    query_fps = query_result['fingerprints']
    print(f"    Query fingerprints: {len(query_fps)}")
    
    # Match against database
    print("\n[5] Matching against database...")
    import time
    start = time.time()
    matches = match_fingerprints(query_fps, db, config)
    match_time = (time.time() - start) * 1000
    print(f"    Match time: {match_time:.1f}ms")
    
    # Results
    print(f"\n[6] Results:")
    print("-" * 40)
    
    if matches:
        for i, match in enumerate(matches[:3]):
            print(f"\n    #{i+1}: {match.track_info.filename}")
            print(f"        Score: {match.score}")
            print(f"        Confidence: {match.confidence:.2f}")
            print(f"        Time offset: {match.offset_seconds:.2f}s")
        
        # Check if correct
        best_match = matches[0]
        is_correct = best_match.track_info.filename == query_track_name
        expected_offset = start_time
        offset_error = abs(best_match.offset_seconds - expected_offset)
        
        print("\n" + "=" * 40)
        if is_correct and offset_error < 1.0:
            print("SUCCESS! Correctly identified track and time offset")
            print(f"  Expected offset: {expected_offset:.2f}s")
            print(f"  Detected offset: {best_match.offset_seconds:.2f}s")
            print(f"  Error: {offset_error:.2f}s")
        elif is_correct:
            print("PARTIAL SUCCESS: Correct track, offset may be off")
            print(f"  Expected offset: {expected_offset:.2f}s")
            print(f"  Detected offset: {best_match.offset_seconds:.2f}s")
        else:
            print("FAILED: Wrong track identified")
            print(f"  Expected: {query_track_name}")
            print(f"  Got: {best_match.track_info.filename}")
        print("=" * 40)
        
        # Visualization
        print("\n[7] Creating recognition visualization...")
        
        fig = plt.figure(figsize=(16, 10))
        
        # Query spectrogram
        ax1 = fig.add_subplot(2, 2, 1)
        plot_spectrogram(query_result['spectrogram'], config, ax=ax1,
                        title=f"Query Spectrogram ({query_duration:.0f}s, SNR={snr_db}dB)")
        
        # Query constellation
        ax2 = fig.add_subplot(2, 2, 2)
        plot_constellation(query_result['spectrogram'], query_result['peaks'],
                          config, ax=ax2, title="Query Constellation Map")
        
        # Match histogram for top result
        ax3 = fig.add_subplot(2, 2, 3)
        plot_match_histogram(matches[0], config, ax=ax3,
                            title=f"Offset Votes: {matches[0].track_info.filename}")
        
        # All track scores
        ax4 = fig.add_subplot(2, 2, 4)
        track_names = [m.track_info.filename for m in matches[:5]]
        scores = [m.score for m in matches[:5]]
        colors = ['green' if n == query_track_name else 'gray' for n in track_names]
        
        ax4.barh(range(len(track_names)), scores, color=colors, alpha=0.7)
        ax4.set_yticks(range(len(track_names)))
        ax4.set_yticklabels(track_names)
        ax4.set_xlabel('Score (matching fingerprints)')
        ax4.set_title('Top 5 Matches')
        ax4.invert_yaxis()
        
        plt.tight_layout()
        plt.savefig('demo_recognition.png', dpi=150, bbox_inches='tight')
        print("    Saved to: demo_recognition.png")
    
    else:
        print("    No matches found!")
    
    return matches


def demo_robustness(
    audio: np.ndarray,
    name: str,
    config: FingerprintConfig = DEFAULT_CONFIG
):
    """
    Test fingerprinting robustness at different noise levels.
    """
    print(f"\n{'='*60}")
    print("ROBUSTNESS TEST")
    print(f"{'='*60}")
    
    # Build reference database from clean audio
    db = InMemoryDatabase()
    result = fingerprint_audio(audio, config)
    db.add_track(result['fingerprints'], filename=name, 
                duration_seconds=len(audio)/config.sample_rate)
    
    print(f"Reference track: {name}")
    print(f"Reference fingerprints: {len(result['fingerprints'])}")
    
    # Test at different SNR levels
    snr_levels = [30, 20, 15, 10, 5, 0, -5]
    results = []
    
    print(f"\n{'SNR (dB)':<12} {'Fingerprints':<15} {'Matches':<10} {'Confidence':<12}")
    print("-" * 50)
    
    for snr in snr_levels:
        # Create noisy version (use middle 10 seconds)
        mid = len(audio) // 2
        segment = audio[mid-55125:mid+55125]  # 10 seconds
        noisy = simulate_recording(segment, config.sample_rate, snr_db=snr)
        
        # Fingerprint noisy audio
        noisy_result = fingerprint_audio(noisy, config)
        noisy_fps = noisy_result['fingerprints']
        
        # Match
        matches = match_fingerprints(noisy_fps, db, config)
        
        if matches:
            score = matches[0].score
            confidence = matches[0].confidence
            correct = matches[0].track_info.filename == name
        else:
            score = 0
            confidence = 0
            correct = False
        
        status = "OK" if correct else "FAIL"
        print(f"{snr:<12} {len(noisy_fps):<15} {score:<10} {confidence:<12.2f} {status}")
        
        results.append({
            'snr': snr,
            'n_fps': len(noisy_fps),
            'score': score,
            'confidence': confidence,
            'correct': correct
        })
    
    # Plot robustness curve
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    snrs = [r['snr'] for r in results]
    scores = [r['score'] for r in results]
    confidences = [r['confidence'] for r in results]
    
    ax1.plot(snrs, scores, 'b-o', linewidth=2, markersize=8)
    ax1.set_xlabel('SNR (dB)')
    ax1.set_ylabel('Matching Score')
    ax1.set_title('Recognition Score vs. Noise Level')
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=10, color='r', linestyle='--', label='Min reliable threshold')
    ax1.legend()
    
    ax2.plot(snrs, confidences, 'g-o', linewidth=2, markersize=8)
    ax2.set_xlabel('SNR (dB)')
    ax2.set_ylabel('Confidence')
    ax2.set_title('Recognition Confidence vs. Noise Level')
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=2.0, color='r', linestyle='--', label='Min reliable threshold')
    ax2.legend()
    
    plt.tight_layout()
    plt.savefig('demo_robustness.png', dpi=150, bbox_inches='tight')
    print(f"\nSaved to: demo_robustness.png")
    
    return results


# =============================================================================
# Main Demo
# =============================================================================

def run_demo_with_files(music_dir: str, config: FingerprintConfig = DEFAULT_CONFIG):
    """Run demo with actual audio files."""
    from build_db import build_database
    
    print(f"\nLoading audio files from: {music_dir}")
    audio_files = find_audio_files(music_dir)
    
    if not audio_files:
        print(f"No audio files found in {music_dir}")
        return
    
    print(f"Found {len(audio_files)} files")
    
    # Limit to first 10 files for demo
    audio_files = audio_files[:10]
    
    # Demo first file
    first_file = audio_files[0]
    print(f"\nAnalyzing: {Path(first_file).name}")
    audio, sr = load_audio(first_file, sr=config.sample_rate)
    demo_single_track(audio, Path(first_file).name, config)
    
    # Build database
    print("\n" + "="*60)
    print("Building database from all files...")
    db = build_database(music_dir, "demo.db", config, verbose=True)
    
    # Test recognition
    if len(audio_files) > 0:
        print("\n" + "="*60)
        print("Testing recognition...")
        
        # Pick a random file and segment
        test_file = random.choice(audio_files)
        audio, sr = load_audio(test_file, sr=config.sample_rate)
        
        # Extract 10s segment
        duration = len(audio) / sr
        if duration > 15:
            start = random.uniform(5, duration - 15)
            start_sample = int(start * sr)
            end_sample = start_sample + int(10 * sr)
            query = audio[start_sample:end_sample]
        else:
            query = audio
        
        # Add noise
        query = simulate_recording(query, sr, snr_db=15)
        
        # Save query
        import scipy.io.wavfile as wav
        wav.write('demo_query.wav', sr, (query * 32767).astype(np.int16))
        print(f"Saved query to: demo_query.wav")
        
        # Recognize
        from recognize import recognize
        recognize('demo_query.wav', 'demo.db', plot=True)


def run_demo_synthetic(config: FingerprintConfig = DEFAULT_CONFIG):
    """Run demo with synthetic audio."""
    print("\n" + "="*60)
    print("SHAZAM-STYLE AUDIO FINGERPRINTING DEMO")
    print("="*60)
    print("\nUsing synthetic audio for demonstration.")
    print("For real audio, run: python demo.py --music_dir <folder>")
    
    # Generate synthetic dataset
    print("\n[1] Generating synthetic audio tracks...")
    dataset = generate_synthetic_dataset(n_tracks=5, duration=30.0, sr=config.sample_rate)
    print(f"    Generated {len(dataset)} tracks")
    
    # Demo fingerprinting on first track
    first_name = list(dataset.keys())[0]
    first_audio = dataset[first_name]
    demo_single_track(first_audio, first_name, config)
    
    # Demo recognition
    demo_recognition(dataset, config, query_duration=10.0, snr_db=15.0)
    
    # Demo robustness
    demo_robustness(first_audio, first_name, config)
    
    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nGenerated files:")
    print("  - demo_fingerprint.png  : Fingerprinting visualization")
    print("  - demo_recognition.png  : Recognition visualization")
    print("  - demo_robustness.png   : Robustness test results")
    print("\nNext steps:")
    print("  1. Add your music files to a folder")
    print("  2. Run: python build_db.py --music_dir <folder>")
    print("  3. Run: python recognize.py --query <audio_file>")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Shazam-style audio fingerprinting demo",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--music_dir", "-m",
        help="Directory with audio files to use for demo"
    )
    
    parser.add_argument(
        "--audio_file", "-a",
        help="Single audio file to analyze"
    )
    
    parser.add_argument(
        "--no_plots",
        action="store_true",
        help="Skip generating plots"
    )
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG
    
    try:
        if args.audio_file:
            # Demo single file
            audio, sr = load_audio(args.audio_file, sr=config.sample_rate)
            demo_single_track(audio, Path(args.audio_file).name, config)
            if not args.no_plots:
                plt.show()
        
        elif args.music_dir:
            # Demo with real files
            run_demo_with_files(args.music_dir, config)
            if not args.no_plots:
                plt.show()
        
        else:
            # Demo with synthetic audio
            run_demo_synthetic(config)
            if not args.no_plots:
                plt.show()
        
        return 0
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
