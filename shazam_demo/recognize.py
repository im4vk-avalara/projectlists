#!/usr/bin/env python3
"""
Audio Recognition CLI

Match a query audio file against the fingerprint database.

Usage:
    python recognize.py --query <audio_file> [--db_path <path>] [--top_n <n>]

Examples:
    python recognize.py --query recorded_clip.wav
    python recognize.py --query mystery_song.mp3 --db_path songs.db --top_n 5
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from audio_utils import load_audio
from fingerprint import (
    fingerprint_audio, FingerprintConfig, DEFAULT_CONFIG
)
from db import SQLiteDatabase, match_fingerprints, MatchResult


def recognize(
    query_path: str,
    db_path: str = "fingerprints.db",
    config: FingerprintConfig = DEFAULT_CONFIG,
    top_n: int = 5,
    verbose: bool = True,
    plot: bool = False
) -> Optional[MatchResult]:
    """
    Recognize a query audio file against the database.
    
    Parameters
    ----------
    query_path : str
        Path to query audio file
    db_path : str
        Path to fingerprint database
    config : FingerprintConfig
        Fingerprinting configuration
    top_n : int
        Number of top matches to return
    verbose : bool
        Print results
    plot : bool
        Show visualization plots
    
    Returns
    -------
    result : MatchResult or None
        Best match, or None if no matches found
    """
    query_path = Path(query_path)
    if not query_path.exists():
        raise FileNotFoundError(f"Query file not found: {query_path}")
    
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}. "
            "Run build_db.py first to create the database."
        )
    
    # Open database
    db = SQLiteDatabase(str(db_path))
    
    try:
        if verbose:
            print(f"Query: {query_path.name}")
            print(f"Database: {db_path}")
            stats = db.get_stats()
            print(f"Tracks in database: {stats['n_tracks']}")
            print("-" * 60)
        
        # Load query audio
        start = time.time()
        audio, sr = load_audio(str(query_path), sr=config.sample_rate)
        query_duration = len(audio) / sr
        load_time = time.time() - start
        
        if verbose:
            print(f"Query duration: {query_duration:.2f}s")
        
        # Compute fingerprints
        start = time.time()
        result = fingerprint_audio(audio, config)
        query_fps = result['fingerprints']
        fp_time = time.time() - start
        
        if verbose:
            print(f"Query fingerprints: {len(query_fps)}")
        
        if len(query_fps) == 0:
            print("WARNING: No fingerprints generated from query. "
                  "Audio may be too short or too quiet.")
            return None
        
        # Match against database
        start = time.time()
        matches = match_fingerprints(query_fps, db, config)
        match_time = time.time() - start
        
        if verbose:
            print(f"Matching time: {match_time*1000:.1f}ms")
            print("-" * 60)
        
        if not matches:
            if verbose:
                print("No matches found.")
            return None
        
        # Display results
        if verbose:
            print(f"Top {min(top_n, len(matches))} matches:\n")
            for i, match in enumerate(matches[:top_n]):
                track_name = match.track_info.filename if match.track_info else f"Track {match.track_id}"
                print(f"  {i+1}. {track_name}")
                print(f"     Score: {match.score} matching fingerprints")
                print(f"     Confidence: {match.confidence:.2f}")
                print(f"     Time offset: {match.offset_seconds:.2f}s")
                print()
            
            # Final answer
            best = matches[0]
            track_name = best.track_info.filename if best.track_info else f"Track {best.track_id}"
            
            if best.confidence > 2.0:
                print("=" * 60)
                print(f"MATCH: {track_name}")
                print(f"The query matches at {best.offset_seconds:.1f}s into the track")
                print("=" * 60)
            elif best.confidence > 1.5:
                print("=" * 60)
                print(f"LIKELY MATCH: {track_name}")
                print(f"Confidence is moderate ({best.confidence:.2f})")
                print("=" * 60)
            else:
                print("=" * 60)
                print(f"UNCERTAIN: Best guess is {track_name}")
                print(f"Low confidence ({best.confidence:.2f}) - may be incorrect")
                print("=" * 60)
        
        # Plot if requested
        if plot and matches:
            import matplotlib.pyplot as plt
            from db import plot_match_histogram
            
            fig, axes = plt.subplots(min(3, len(matches)), 1, figsize=(12, 4*min(3, len(matches))))
            if len(matches) == 1:
                axes = [axes]
            
            for ax, match in zip(axes, matches[:3]):
                plot_match_histogram(match, config, ax)
            
            plt.tight_layout()
            plt.show()
        
        return matches[0] if matches else None
    
    finally:
        db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Recognize audio against fingerprint database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python recognize.py --query recorded_clip.wav
  python recognize.py --query mystery.mp3 --db_path songs.db --top_n 10
  python recognize.py --query clip.wav --plot

Note: Run build_db.py first to create the fingerprint database.
        """
    )
    
    parser.add_argument(
        "--query", "-q",
        required=True,
        help="Path to query audio file"
    )
    
    parser.add_argument(
        "--db_path", "-d",
        default="fingerprints.db",
        help="Path to fingerprint database (default: fingerprints.db)"
    )
    
    parser.add_argument(
        "--top_n", "-n",
        type=int,
        default=5,
        help="Number of top matches to show (default: 5)"
    )
    
    parser.add_argument(
        "--plot", "-p",
        action="store_true",
        help="Show visualization plots"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output (just return result)"
    )
    
    # Output format
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )
    
    args = parser.parse_args()
    
    try:
        result = recognize(
            query_path=args.query,
            db_path=args.db_path,
            top_n=args.top_n,
            verbose=not args.quiet and not args.json,
            plot=args.plot
        )
        
        if args.json:
            import json
            if result:
                output = {
                    'matched': True,
                    'track': result.track_info.filename if result.track_info else None,
                    'track_id': result.track_id,
                    'score': result.score,
                    'confidence': result.confidence,
                    'offset_seconds': result.offset_seconds
                }
            else:
                output = {'matched': False}
            print(json.dumps(output, indent=2))
        
        return 0 if result else 1
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
