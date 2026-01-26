#!/usr/bin/env python3
"""
Build Fingerprint Database

CLI tool to index a directory of audio files and build a fingerprint database.

Usage:
    python build_db.py --music_dir <directory> [--db_path <path>] [--verbose]
    
Examples:
    python build_db.py --music_dir ./music
    python build_db.py --music_dir ~/Music --db_path my_db.db --verbose
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List

from audio_utils import load_audio, find_audio_files, get_supported_formats
from fingerprint import (
    fingerprint_audio, FingerprintConfig, DEFAULT_CONFIG
)
from db import SQLiteDatabase, InMemoryDatabase


def build_database(
    music_dir: str,
    db_path: str = "fingerprints.db",
    config: FingerprintConfig = DEFAULT_CONFIG,
    verbose: bool = True,
    use_sqlite: bool = True
) -> 'SQLiteDatabase | InMemoryDatabase':
    """
    Build a fingerprint database from a directory of audio files.
    
    Parameters
    ----------
    music_dir : str
        Directory containing audio files
    db_path : str
        Path to output SQLite database
    config : FingerprintConfig
        Fingerprinting configuration
    verbose : bool
        Print progress information
    use_sqlite : bool
        Use SQLite (True) or in-memory database (False)
    
    Returns
    -------
    db : SQLiteDatabase or InMemoryDatabase
        The populated database
    """
    # Find all audio files
    music_dir = Path(music_dir)
    if not music_dir.exists():
        raise FileNotFoundError(f"Directory not found: {music_dir}")
    
    audio_files = find_audio_files(music_dir)
    
    if not audio_files:
        raise ValueError(
            f"No audio files found in {music_dir}. "
            f"Supported formats: {get_supported_formats()}"
        )
    
    if verbose:
        print(f"Found {len(audio_files)} audio files in {music_dir}")
        print(f"Supported formats: {get_supported_formats()}")
        print(f"Database: {db_path}")
        print(f"Config: sample_rate={config.sample_rate}, n_fft={config.n_fft}")
        print("-" * 60)
    
    # Create database
    if use_sqlite:
        db = SQLiteDatabase(db_path)
    else:
        db = InMemoryDatabase()
    
    # Process each file
    total_fingerprints = 0
    total_time = 0
    failed_files = []
    
    for i, filepath in enumerate(audio_files):
        filename = Path(filepath).name
        
        try:
            start = time.time()
            
            # Load audio
            audio, sr = load_audio(filepath, sr=config.sample_rate)
            duration = len(audio) / sr
            
            # Compute fingerprints
            result = fingerprint_audio(audio, config)
            fingerprints = result['fingerprints']
            
            # Add to database
            track_id = db.add_track(
                fingerprints,
                filename=filename,
                filepath=filepath,
                duration_seconds=duration
            )
            
            elapsed = time.time() - start
            total_fingerprints += len(fingerprints)
            total_time += elapsed
            
            if verbose:
                print(
                    f"[{i+1}/{len(audio_files)}] {filename}: "
                    f"{duration:.1f}s, {len(fingerprints)} fps, "
                    f"{elapsed:.2f}s"
                )
        
        except Exception as e:
            failed_files.append((filepath, str(e)))
            if verbose:
                print(f"[{i+1}/{len(audio_files)}] {filename}: FAILED - {e}")
    
    # Summary
    if verbose:
        print("-" * 60)
        stats = db.get_stats()
        print(f"Indexed {stats['n_tracks']} tracks")
        print(f"Total fingerprints: {stats['n_fingerprints']:,}")
        print(f"Unique hashes: {stats['n_unique_hashes']:,}")
        print(f"Avg fps per track: {stats['avg_fps_per_track']:.0f}")
        print(f"Total processing time: {total_time:.1f}s")
        
        if failed_files:
            print(f"\nFailed files ({len(failed_files)}):")
            for path, error in failed_files[:5]:
                print(f"  - {Path(path).name}: {error}")
            if len(failed_files) > 5:
                print(f"  ... and {len(failed_files) - 5} more")
    
    return db


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build fingerprint database from audio files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_db.py --music_dir ./music
  python build_db.py --music_dir ~/Music/Collection --db_path songs.db
  python build_db.py --music_dir ./tracks --verbose --clear

Supported audio formats: .mp3, .wav, .flac, .ogg, .m4a, .wma, .aac
(requires librosa for full format support)
        """
    )
    
    parser.add_argument(
        "--music_dir", "-m",
        required=True,
        help="Directory containing audio files to index"
    )
    
    parser.add_argument(
        "--db_path", "-d",
        default="fingerprints.db",
        help="Output database path (default: fingerprints.db)"
    )
    
    parser.add_argument(
        "--clear", "-c",
        action="store_true",
        help="Clear existing database before building"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=True,
        help="Print progress information (default: True)"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output"
    )
    
    # Advanced options
    parser.add_argument(
        "--sample_rate",
        type=int,
        default=11025,
        help="Sample rate for fingerprinting (default: 11025)"
    )
    
    parser.add_argument(
        "--n_fft",
        type=int,
        default=2048,
        help="FFT window size (default: 2048)"
    )
    
    parser.add_argument(
        "--fan_out",
        type=int,
        default=15,
        help="Fan-out for hashing (default: 15)"
    )
    
    args = parser.parse_args()
    
    # Build config
    config = FingerprintConfig(
        sample_rate=args.sample_rate,
        n_fft=args.n_fft,
        fan_out=args.fan_out
    )
    
    verbose = args.verbose and not args.quiet
    
    try:
        # Check if database exists and should be cleared
        db_path = Path(args.db_path)
        if args.clear and db_path.exists():
            db_path.unlink()
            if verbose:
                print(f"Cleared existing database: {db_path}")
        
        # Build database
        db = build_database(
            music_dir=args.music_dir,
            db_path=args.db_path,
            config=config,
            verbose=verbose
        )
        
        # Close if SQLite
        if hasattr(db, 'close'):
            db.close()
        
        if verbose:
            print(f"\nDatabase saved to: {args.db_path}")
        
        return 0
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
