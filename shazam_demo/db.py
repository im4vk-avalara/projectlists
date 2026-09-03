"""
Database Module for Audio Fingerprinting

This module handles storage and retrieval of fingerprints using SQLite.
Also provides an in-memory dict-based database for testing.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
from dataclasses import dataclass, field
import time

from fingerprint import Fingerprint


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class TrackInfo:
    """Information about a track in the database."""
    track_id: int
    filename: str
    filepath: str
    duration_seconds: float
    n_fingerprints: int
    added_time: float = field(default_factory=time.time)


@dataclass 
class MatchResult:
    """Result of matching a query against the database."""
    track_id: int
    track_info: Optional[TrackInfo]
    offset: int                    # Best matching time offset (frames)
    offset_seconds: float          # Best matching time offset (seconds)
    score: int                     # Number of matching fingerprints at this offset
    confidence: float              # score / second_best_score
    all_offsets: Dict[int, int]    # All offset -> count for this track


# =============================================================================
# In-Memory Database
# =============================================================================

class InMemoryDatabase:
    """
    Simple in-memory fingerprint database using Python dicts.
    Good for testing and small datasets.
    """
    
    def __init__(self):
        """Initialize empty database."""
        self.fingerprints: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        # hash -> [(track_id, anchor_time), ...]
        
        self.tracks: Dict[int, TrackInfo] = {}
        # track_id -> TrackInfo
        
        self.next_track_id = 1
    
    def add_track(
        self,
        fingerprints: List[Fingerprint],
        filename: str,
        filepath: str = "",
        duration_seconds: float = 0.0
    ) -> int:
        """
        Add a track to the database.
        
        Parameters
        ----------
        fingerprints : List[Fingerprint]
            Fingerprints for this track
        filename : str
            Name of the track
        filepath : str
            Full path to the file
        duration_seconds : float
            Duration of the track
        
        Returns
        -------
        track_id : int
            Assigned track ID
        """
        track_id = self.next_track_id
        self.next_track_id += 1
        
        # Store track info
        self.tracks[track_id] = TrackInfo(
            track_id=track_id,
            filename=filename,
            filepath=filepath,
            duration_seconds=duration_seconds,
            n_fingerprints=len(fingerprints)
        )
        
        # Store fingerprints
        for fp in fingerprints:
            self.fingerprints[fp.hash].append((track_id, fp.time))
        
        return track_id
    
    def lookup(self, hash_val: int) -> List[Tuple[int, int]]:
        """
        Look up a hash in the database.
        
        Parameters
        ----------
        hash_val : int
            Hash to look up
        
        Returns
        -------
        matches : List[Tuple[int, int]]
            List of (track_id, anchor_time) for matching fingerprints
        """
        return self.fingerprints.get(hash_val, [])
    
    def lookup_batch(self, hashes: List[int]) -> Dict[int, List[Tuple[int, int]]]:
        """
        Look up multiple hashes at once.
        
        Parameters
        ----------
        hashes : List[int]
            Hashes to look up
        
        Returns
        -------
        matches : Dict[int, List[Tuple[int, int]]]
            hash -> [(track_id, anchor_time), ...]
        """
        return {h: self.fingerprints.get(h, []) for h in hashes}
    
    def get_track(self, track_id: int) -> Optional[TrackInfo]:
        """Get track info by ID."""
        return self.tracks.get(track_id)
    
    def get_all_tracks(self) -> List[TrackInfo]:
        """Get all tracks in the database."""
        return list(self.tracks.values())
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        total_fps = sum(len(v) for v in self.fingerprints.values())
        return {
            'n_tracks': len(self.tracks),
            'n_fingerprints': total_fps,
            'n_unique_hashes': len(self.fingerprints),
            'avg_fps_per_track': total_fps / len(self.tracks) if self.tracks else 0
        }
    
    def clear(self):
        """Clear the database."""
        self.fingerprints.clear()
        self.tracks.clear()
        self.next_track_id = 1
    
    def save(self, filepath: str):
        """Save database to JSON file."""
        data = {
            'fingerprints': {str(k): v for k, v in self.fingerprints.items()},
            'tracks': {str(k): {
                'track_id': t.track_id,
                'filename': t.filename,
                'filepath': t.filepath,
                'duration_seconds': t.duration_seconds,
                'n_fingerprints': t.n_fingerprints,
                'added_time': t.added_time
            } for k, t in self.tracks.items()},
            'next_track_id': self.next_track_id
        }
        with open(filepath, 'w') as f:
            json.dump(data, f)
    
    def load(self, filepath: str):
        """Load database from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.fingerprints = defaultdict(list)
        for k, v in data['fingerprints'].items():
            self.fingerprints[int(k)] = [tuple(x) for x in v]
        
        self.tracks = {}
        for k, v in data['tracks'].items():
            self.tracks[int(k)] = TrackInfo(**v)
        
        self.next_track_id = data['next_track_id']


# =============================================================================
# SQLite Database
# =============================================================================

class SQLiteDatabase:
    """
    SQLite-based fingerprint database.
    Better for larger datasets and persistence.
    """
    
    def __init__(self, db_path: str = "fingerprints.db"):
        """
        Initialize SQLite database.
        
        Parameters
        ----------
        db_path : str
            Path to SQLite database file. Use ":memory:" for in-memory DB.
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Tracks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracks (
                track_id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT,
                duration_seconds REAL,
                n_fingerprints INTEGER,
                added_time REAL
            )
        ''')
        
        # Fingerprints table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                anchor_time INTEGER NOT NULL,
                FOREIGN KEY (track_id) REFERENCES tracks(track_id)
            )
        ''')
        
        # Index on hash for fast lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_hash ON fingerprints(hash)
        ''')
        
        # Index on track_id for deleting tracks
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_track_id ON fingerprints(track_id)
        ''')
        
        self.conn.commit()
    
    def add_track(
        self,
        fingerprints: List[Fingerprint],
        filename: str,
        filepath: str = "",
        duration_seconds: float = 0.0
    ) -> int:
        """
        Add a track to the database.
        
        Parameters
        ----------
        fingerprints : List[Fingerprint]
            Fingerprints for this track
        filename : str
            Name of the track
        filepath : str
            Full path to the file
        duration_seconds : float
            Duration of the track
        
        Returns
        -------
        track_id : int
            Assigned track ID
        """
        cursor = self.conn.cursor()
        
        # Insert track
        cursor.execute('''
            INSERT INTO tracks (filename, filepath, duration_seconds, n_fingerprints, added_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (filename, filepath, duration_seconds, len(fingerprints), time.time()))
        
        track_id = cursor.lastrowid
        
        # Insert fingerprints in batch
        fp_data = [(fp.hash, track_id, fp.time) for fp in fingerprints]
        cursor.executemany('''
            INSERT INTO fingerprints (hash, track_id, anchor_time)
            VALUES (?, ?, ?)
        ''', fp_data)
        
        self.conn.commit()
        return track_id
    
    def lookup(self, hash_val: int) -> List[Tuple[int, int]]:
        """
        Look up a hash in the database.
        
        Parameters
        ----------
        hash_val : int
            Hash to look up
        
        Returns
        -------
        matches : List[Tuple[int, int]]
            List of (track_id, anchor_time) for matching fingerprints
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT track_id, anchor_time FROM fingerprints WHERE hash = ?
        ''', (hash_val,))
        
        return [(row['track_id'], row['anchor_time']) for row in cursor.fetchall()]
    
    def lookup_batch(self, hashes: List[int]) -> Dict[int, List[Tuple[int, int]]]:
        """
        Look up multiple hashes at once.
        
        Parameters
        ----------
        hashes : List[int]
            Hashes to look up
        
        Returns
        -------
        matches : Dict[int, List[Tuple[int, int]]]
            hash -> [(track_id, anchor_time), ...]
        """
        if not hashes:
            return {}
        
        cursor = self.conn.cursor()
        
        # Use IN clause for batch lookup
        placeholders = ','.join('?' * len(hashes))
        cursor.execute(f'''
            SELECT hash, track_id, anchor_time FROM fingerprints 
            WHERE hash IN ({placeholders})
        ''', hashes)
        
        result = defaultdict(list)
        for row in cursor.fetchall():
            result[row['hash']].append((row['track_id'], row['anchor_time']))
        
        return dict(result)
    
    def get_track(self, track_id: int) -> Optional[TrackInfo]:
        """Get track info by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tracks WHERE track_id = ?', (track_id,))
        row = cursor.fetchone()
        
        if row:
            return TrackInfo(
                track_id=row['track_id'],
                filename=row['filename'],
                filepath=row['filepath'],
                duration_seconds=row['duration_seconds'],
                n_fingerprints=row['n_fingerprints'],
                added_time=row['added_time']
            )
        return None
    
    def get_all_tracks(self) -> List[TrackInfo]:
        """Get all tracks in the database."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tracks ORDER BY track_id')
        
        return [
            TrackInfo(
                track_id=row['track_id'],
                filename=row['filename'],
                filepath=row['filepath'],
                duration_seconds=row['duration_seconds'],
                n_fingerprints=row['n_fingerprints'],
                added_time=row['added_time']
            )
            for row in cursor.fetchall()
        ]
    
    def delete_track(self, track_id: int):
        """Delete a track and its fingerprints."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM fingerprints WHERE track_id = ?', (track_id,))
        cursor.execute('DELETE FROM tracks WHERE track_id = ?', (track_id,))
        self.conn.commit()
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as n FROM tracks')
        n_tracks = cursor.fetchone()['n']
        
        cursor.execute('SELECT COUNT(*) as n FROM fingerprints')
        n_fps = cursor.fetchone()['n']
        
        cursor.execute('SELECT COUNT(DISTINCT hash) as n FROM fingerprints')
        n_unique = cursor.fetchone()['n']
        
        return {
            'n_tracks': n_tracks,
            'n_fingerprints': n_fps,
            'n_unique_hashes': n_unique,
            'avg_fps_per_track': n_fps / n_tracks if n_tracks else 0
        }
    
    def clear(self):
        """Clear all data from the database."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM fingerprints')
        cursor.execute('DELETE FROM tracks')
        cursor.execute('DELETE FROM sqlite_sequence')  # Reset autoincrement
        self.conn.commit()
    
    def vacuum(self):
        """Reclaim disk space after deletions."""
        self.conn.execute('VACUUM')
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# =============================================================================
# Matching Algorithm
# =============================================================================

def match_fingerprints(
    query_fingerprints: List[Fingerprint],
    db: 'SQLiteDatabase | InMemoryDatabase',
    config=None,
    offset_tolerance: int = 2
) -> List[MatchResult]:
    """
    Match query fingerprints against the database.
    
    Uses offset voting: for each matching hash, compute
    offset = db_anchor_time - query_anchor_time
    
    The correct track will have many fingerprints at the same offset.
    
    Parameters
    ----------
    query_fingerprints : List[Fingerprint]
        Fingerprints from the query audio
    db : SQLiteDatabase or InMemoryDatabase
        Database to search
    config : FingerprintConfig or None
        Configuration (for frame duration calculation)
    offset_tolerance : int
        Allow this many frames of offset variation
    
    Returns
    -------
    results : List[MatchResult]
        Matching tracks sorted by score (descending)
    """
    from fingerprint import DEFAULT_CONFIG
    if config is None:
        config = DEFAULT_CONFIG
    
    # Get unique hashes from query
    query_hashes = list(set(fp.hash for fp in query_fingerprints))
    
    # Batch lookup
    db_matches = db.lookup_batch(query_hashes)
    
    # Create hash -> query times mapping
    hash_to_query_times: Dict[int, List[int]] = defaultdict(list)
    for fp in query_fingerprints:
        hash_to_query_times[fp.hash].append(fp.time)
    
    # Vote on (track_id, offset)
    # votes[track_id][offset] = count
    votes: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    
    for hash_val, db_entries in db_matches.items():
        query_times = hash_to_query_times[hash_val]
        
        for track_id, db_time in db_entries:
            for query_time in query_times:
                offset = db_time - query_time
                
                # Apply tolerance (bin offsets)
                binned_offset = offset // (offset_tolerance + 1) * (offset_tolerance + 1)
                votes[track_id][binned_offset] += 1
    
    # Find best offset for each track
    results = []
    
    for track_id, offset_votes in votes.items():
        if not offset_votes:
            continue
        
        # Find best offset
        best_offset = max(offset_votes.keys(), key=lambda o: offset_votes[o])
        best_score = offset_votes[best_offset]
        
        # Find second best for confidence
        other_scores = [v for o, v in offset_votes.items() if o != best_offset]
        second_best = max(other_scores) if other_scores else 1
        
        confidence = best_score / second_best if second_best > 0 else best_score
        
        # Get track info
        track_info = db.get_track(track_id)
        
        # Convert offset to seconds
        offset_seconds = best_offset * config.hop_length / config.sample_rate
        
        results.append(MatchResult(
            track_id=track_id,
            track_info=track_info,
            offset=best_offset,
            offset_seconds=offset_seconds,
            score=best_score,
            confidence=confidence,
            all_offsets=dict(offset_votes)
        ))
    
    # Sort by score (descending)
    results.sort(key=lambda r: r.score, reverse=True)
    
    return results


# =============================================================================
# Visualization
# =============================================================================

def plot_match_histogram(
    result: MatchResult,
    config=None,
    ax=None,
    title: str = None
):
    """
    Plot histogram of offset votes for a match result.
    
    Parameters
    ----------
    result : MatchResult
        Match result to visualize
    config : FingerprintConfig or None
        Configuration for time conversion
    ax : matplotlib.axes.Axes or None
        Axes to plot on
    title : str or None
        Plot title
    """
    import matplotlib.pyplot as plt
    from fingerprint import DEFAULT_CONFIG
    
    if config is None:
        config = DEFAULT_CONFIG
    
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 4))
    
    # Convert offsets to seconds
    offsets = list(result.all_offsets.keys())
    counts = list(result.all_offsets.values())
    
    offset_seconds = [o * config.hop_length / config.sample_rate for o in offsets]
    
    ax.bar(offset_seconds, counts, width=config.hop_length / config.sample_rate * 2, alpha=0.7)
    
    # Mark the best offset
    best_offset_sec = result.offset_seconds
    ax.axvline(x=best_offset_sec, color='red', linestyle='--', linewidth=2, label='Best offset')
    
    ax.set_xlabel('Time Offset (s)')
    ax.set_ylabel('Vote Count')
    
    if title is None:
        track_name = result.track_info.filename if result.track_info else f"Track {result.track_id}"
        title = f"Offset Histogram: {track_name}"
    
    ax.set_title(f"{title}\nScore: {result.score}, Confidence: {result.confidence:.2f}")
    ax.legend()
    
    return ax


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    print("Database Module Test")
    print("=" * 50)
    
    # Test in-memory database
    print("\nTesting InMemoryDatabase...")
    db = InMemoryDatabase()
    
    # Add some test fingerprints
    fps = [
        Fingerprint(hash=12345, time=10),
        Fingerprint(hash=67890, time=20),
        Fingerprint(hash=12345, time=30),
    ]
    
    track_id = db.add_track(fps, "test_song.mp3", duration_seconds=180.0)
    print(f"Added track {track_id}")
    
    # Lookup
    matches = db.lookup(12345)
    print(f"Lookup hash 12345: {matches}")
    
    # Stats
    print(f"Stats: {db.get_stats()}")
    
    # Test SQLite database
    print("\nTesting SQLiteDatabase...")
    with SQLiteDatabase(":memory:") as sqlite_db:
        track_id = sqlite_db.add_track(fps, "test_song.mp3", duration_seconds=180.0)
        print(f"Added track {track_id}")
        
        matches = sqlite_db.lookup(12345)
        print(f"Lookup hash 12345: {matches}")
        
        print(f"Stats: {sqlite_db.get_stats()}")
