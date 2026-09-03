# Shazam-Style Audio Fingerprinting Demo

An educational implementation of the Shazam audio recognition algorithm. This demo fingerprints audio files, stores them in a database, and can recognize short clips even with noise or recording artifacts.

![Algorithm Overview](https://upload.wikimedia.org/wikipedia/commons/thumb/a/a0/Audio_fingerprinting.svg/500px-Audio_fingerprinting.svg.png)

## How It Works

The algorithm follows these steps:

### 1. Spectrogram Computation
Convert audio to a time-frequency representation using Short-Time Fourier Transform (STFT).

```
Audio Waveform → STFT → Log-Magnitude Spectrogram
```

### 2. Peak Picking (Constellation Map)
Find local maxima in the spectrogram. These peaks represent prominent frequency components.

```
Spectrogram → Local Max Filter → Peak Coordinates (time, frequency)
```

### 3. Combinatorial Hashing
Pair each peak with nearby peaks (fan-out pattern) to create fingerprints.

```
Anchor Peak + Target Peak → Hash = (f1, f2, Δt)
```

Each hash encodes:
- `f1`: Anchor frequency
- `f2`: Target frequency  
- `Δt`: Time difference between peaks

### 4. Database Storage
Store fingerprints with their source track and time offset:

```
Hash → [(track_id, anchor_time), ...]
```

### 5. Recognition (Offset Voting)
For a query:
1. Compute fingerprints from query audio
2. Look up each hash in database
3. Vote on `(track_id, offset)` where `offset = db_time - query_time`
4. Track with most votes at consistent offset wins

## Quick Start

### Installation

```bash
cd shazam_demo
pip install -r requirements.txt
```

### Run the Demo

```bash
# Run with synthetic audio (no files needed)
python demo.py

# Run with your audio files
python demo.py --music_dir /path/to/music
```

### Build a Database

```bash
python build_db.py --music_dir /path/to/music --db_path songs.db
```

### Recognize Audio

```bash
python recognize.py --query recording.wav --db_path songs.db
```

## Files

| File | Description |
|------|-------------|
| `audio_utils.py` | Audio loading, resampling, noise simulation |
| `fingerprint.py` | Spectrogram, peak picking, hash generation |
| `db.py` | SQLite and in-memory database storage |
| `build_db.py` | CLI to index audio files into database |
| `recognize.py` | CLI to match query audio against database |
| `demo.py` | Visual walkthrough with plots |
| `DESIGN.md` | Detailed algorithm documentation |

## Algorithm Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Sample Rate | 11025 Hz | Downsampled for efficiency |
| FFT Size | 2048 | ~186ms window |
| Hop Length | 512 | ~46ms between frames |
| Peak Neighborhood | 20×20 | Local max detection window |
| Fan-out | 15 | Target peaks per anchor |
| Target Time Range | 1-100 frames | ~46ms to 4.6s |

See `DESIGN.md` for detailed parameter explanations.

## Example Usage

### Python API

```python
from audio_utils import load_audio
from fingerprint import fingerprint_audio, DEFAULT_CONFIG
from db import SQLiteDatabase, match_fingerprints

# Load and fingerprint audio
audio, sr = load_audio("song.mp3")
result = fingerprint_audio(audio)
print(f"Generated {len(result['fingerprints'])} fingerprints")

# Store in database
db = SQLiteDatabase("songs.db")
db.add_track(result['fingerprints'], "song.mp3")

# Query
query_audio, _ = load_audio("query.wav")
query_result = fingerprint_audio(query_audio)
matches = match_fingerprints(query_result['fingerprints'], db)

if matches:
    best = matches[0]
    print(f"Match: {best.track_info.filename}")
    print(f"Confidence: {best.confidence:.2f}")
```

### Visualization

```python
from fingerprint import (
    compute_spectrogram, find_peaks, 
    plot_spectrogram, plot_constellation, plot_hash_pairs
)
import matplotlib.pyplot as plt

audio, sr = load_audio("song.mp3")
spec = compute_spectrogram(audio)
peaks = find_peaks(spec)

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
plot_spectrogram(spec, ax=axes[0])
plot_constellation(spec, peaks, ax=axes[1])
plot_hash_pairs(peaks, ax=axes[2])
plt.show()
```

## Robustness

The algorithm is designed to handle:

- **Noise**: Works with SNR down to ~5-10 dB
- **Compression**: MP3, AAC, etc.
- **Recording**: Through speakers/microphone
- **Short clips**: 5-15 seconds typically sufficient

### Limitations

- **Pitch shifting**: Even small changes break matching
- **Tempo changes**: Alters time deltas
- **Very noisy**: < 0 dB SNR may fail
- **Short queries**: < 3 seconds may not have enough fingerprints

## Performance

| Metric | Typical Value |
|--------|--------------|
| Fingerprints per track | ~10,000 per minute |
| Build time | 1-3 seconds per 3-min track |
| Query time | 50-200ms |
| Database size | ~360 KB per track |

## References

1. Wang, A. (2003). "An Industrial-Strength Audio Search Algorithm." ISMIR.
2. Ellis, D. (2009). "Robust Landmark-Based Audio Fingerprinting."
3. [How Shazam Works](https://www.toptal.com/algorithms/shazam-it-music-processing-fingerprinting-and-recognition)

## License

This is an educational demo for learning purposes only. Not for commercial use.

## Troubleshooting

### "No audio files found"
- Check that librosa is installed: `pip install librosa`
- Supported formats: .mp3, .wav, .flac, .ogg, .m4a

### "No fingerprints generated"
- Audio may be too short (< 3 seconds)
- Audio may be too quiet (try normalizing)

### "No matches found"
- Build database first with `build_db.py`
- Ensure query is long enough (5+ seconds)
- Check that track is in the database

### Import errors
```bash
pip install numpy scipy matplotlib librosa soundfile
```
