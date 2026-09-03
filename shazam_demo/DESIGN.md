# Shazam-Style Audio Fingerprinting: Design Document

## Overview

This document describes the algorithm and parameters for an educational audio fingerprinting system inspired by the Shazam algorithm (Wang, 2003).

## Algorithm Pipeline

```
Audio File → Mono/Resample → Spectrogram → Peak Picking → Constellation Map
                                                              ↓
                                                    Combinatorial Hashing
                                                              ↓
                                               Hash → (track_id, anchor_time)
                                                              ↓
                                                         Database
```

## Default Parameters

### Audio Preprocessing

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `SAMPLE_RATE` | 11025 Hz | Sufficient for music (covers up to ~5.5 kHz). Lower than CD quality (44.1 kHz) for efficiency. Matches original Shazam. |
| `MONO` | True | Fingerprinting doesn't need stereo information |

### Spectrogram (STFT)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `N_FFT` | 2048 | ~186ms window at 11025 Hz. Good frequency resolution (~5.4 Hz/bin). Power of 2 for FFT efficiency. |
| `HOP_LENGTH` | 512 | 75% overlap. ~46ms hop. Gives ~21 frames/second. |
| `WINDOW` | Hann | Standard choice to reduce spectral leakage |
| `FREQ_BINS` | 1025 | N_FFT/2 + 1 bins from DC to Nyquist |

### Peak Picking

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `NEIGHBORHOOD_TIME` | 20 frames | ~0.9 seconds. Peak must be local max in this time window. |
| `NEIGHBORHOOD_FREQ` | 20 bins | ~108 Hz. Peak must be local max in this frequency window. |
| `MIN_AMPLITUDE` | 10 (dB above noise floor) | Threshold to ignore quiet regions |
| `MAX_PEAKS_PER_FRAME` | 5 | Limit peak density to avoid too many fingerprints |

### Combinatorial Hashing (Fan-out)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `FAN_OUT` | 15 | Number of target peaks to pair with each anchor. Trade-off between robustness and database size. |
| `TARGET_T_MIN` | 1 frame | Minimum time offset (~46ms). Avoid pairing same-time peaks. |
| `TARGET_T_MAX` | 100 frames | Maximum time offset (~4.6s). Captures local structure. |
| `TARGET_F_RANGE` | ±50 bins | Frequency range for targets (~270 Hz above/below anchor) |

### Hash Structure

```
Hash = (f_anchor, f_target, delta_t)
     = (10 bits,   10 bits,  10 bits) = 30-bit hash

Where:
- f_anchor: frequency bin of anchor peak (0-1024, quantized to 10 bits)
- f_target: frequency bin of target peak (0-1024, quantized to 10 bits)  
- delta_t:  time difference in frames (0-1023, clamped)
```

In practice, we use a 32-bit integer: `hash = (f1 << 20) | (f2 << 10) | dt`

### Database Schema

```sql
CREATE TABLE fingerprints (
    hash INTEGER,
    track_id INTEGER,
    anchor_time INTEGER  -- frame number where anchor occurs
);
CREATE INDEX idx_hash ON fingerprints(hash);
```

## Complexity Analysis

### Build Time (per track)

| Step | Complexity | For 3-min song |
|------|------------|----------------|
| Load audio | O(duration × sample_rate) | ~2M samples |
| STFT | O(n_frames × N_FFT × log(N_FFT)) | ~4000 frames × 2K × 11 |
| Peak picking | O(n_frames × n_freq_bins × neighborhood) | ~4000 × 1K × 400 |
| Hashing | O(n_peaks × FAN_OUT) | ~2000 peaks × 15 |
| DB insert | O(n_fingerprints) | ~30K fingerprints |

**Total**: ~1-3 seconds per 3-minute track on modern hardware.

### Query Time

| Step | Complexity | For 10s query |
|------|------------|---------------|
| Fingerprint query | O(query_length) | ~200 frames |
| DB lookup | O(n_query_hashes × avg_matches_per_hash) | ~3K hashes × ~10 matches |
| Offset voting | O(total_matches) | ~30K matches |
| Find max | O(n_tracks × n_offsets) | ~200 tracks × ~1K offsets |

**Total**: ~100-500ms for 10s query against 200-track database.

### Storage

- ~30,000 fingerprints per 3-minute track
- ~12 bytes per fingerprint (hash + track_id + time)
- ~360 KB per track
- ~72 MB for 200 tracks

## Matching Algorithm

### Offset Voting

For each query fingerprint hash that matches a database entry:

```python
offset = db_anchor_time - query_anchor_time
votes[(track_id, offset)] += 1
```

The correct track will show a sharp peak at the correct time offset.

### Confidence Metric

```python
confidence = best_vote_count / second_best_vote_count
```

A confidence > 2.0 typically indicates a reliable match.

## Known Failure Modes

### 1. Pitch Shifting
- **Problem**: Changing pitch shifts all frequencies, breaking hash matches
- **Severity**: High - even small pitch changes break matching
- **Mitigation**: None in this demo (production systems use pitch-invariant features)

### 2. Tempo Changes
- **Problem**: Changing tempo shifts all delta_t values
- **Severity**: High - breaks hash matching
- **Mitigation**: None in this demo

### 3. Very Noisy Recordings
- **Problem**: Noise creates false peaks, overwhelms true peaks
- **Severity**: Medium - works up to ~-10dB SNR
- **Mitigation**: Magnitude thresholding, local max filtering

### 4. Very Short Queries
- **Problem**: < 3 seconds may not have enough fingerprints
- **Severity**: Medium
- **Mitigation**: Require minimum 5-second queries

### 5. Music with Sparse Spectra
- **Problem**: Simple sine waves, solo instruments have few peaks
- **Severity**: Low - most music is complex enough
- **Mitigation**: Lower amplitude threshold

### 6. Clock Drift
- **Problem**: Small timing differences between recordings
- **Severity**: Low
- **Mitigation**: Allow offset tolerance of ±1-2 frames when counting votes

### 7. Repeated Patterns
- **Problem**: Choruses, loops create multiple offset peaks
- **Severity**: Low - usually correct offset still wins
- **Mitigation**: Look for highest peak, not just any peak

## References

1. Wang, A. (2003). "An Industrial-Strength Audio Search Algorithm." ISMIR.
2. Ellis, D. (2009). "Robust Landmark-Based Audio Fingerprinting." Columbia University.
3. https://www.ee.columbia.edu/~dpwe/resources/matlab/fingerprint/

## Parameter Tuning Guide

### For More Robustness (at cost of speed/storage)
- Increase `FAN_OUT` to 20-30
- Decrease `MIN_AMPLITUDE` threshold
- Increase `NEIGHBORHOOD_*` sizes

### For Faster Matching (at cost of accuracy)
- Decrease `FAN_OUT` to 5-10
- Increase `MIN_AMPLITUDE` threshold
- Decrease `TARGET_T_MAX`

### For Better Differentiation
- Decrease `NEIGHBORHOOD_*` sizes (more peaks)
- Increase `TARGET_T_MAX` (longer patterns)
