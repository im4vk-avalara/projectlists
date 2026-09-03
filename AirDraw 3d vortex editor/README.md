# AirDraw Blueprint - Milestone 1

A real-time "blueprint sketch pad" that uses webcam hand tracking to draw CAD-like primitives in the air and renders them as clean blueprint geometry.

## Features (Milestone 1)

### Hand Tracking
- Uses MediaPipe Hands for real-time hand landmark detection
- Tracks index fingertip as the drawing cursor
- One Euro Filter for smooth, responsive cursor movement
- Gesture-based pen down/up state detection

### Gestures
| Gesture | State | Description |
|---------|-------|-------------|
| **Pointing** | Draw | Index finger up, others down |
| **Pinch** | Draw | Thumb and index finger touching |
| **Open Palm** | Hover | All fingers extended |
| **Two Finger** | Hover | Index and middle fingers up |
| **Fist** | Hover | All fingers closed |

### Shape Recognition
When you lift your finger, the stroke is analyzed and classified:
- **Line**: Straight stroke with low error
- **Rectangle**: Closed quadrilateral with ~90° corners
- **Circle**: Closed curved stroke with consistent radius
- **Arc**: Partial circle
- **Polyline**: Fallback for complex shapes

### Snap System
- **Grid Snap**: Points snap to grid intersections (20px default)
- **Angle Snap**: Lines snap to 0°, 45°, 90°, etc.
- **Endpoint Snap**: Start/end points snap to existing shape endpoints

### Live Dimensions
All shapes display measurements:
- Lines: length in units
- Rectangles: width × height
- Circles: radius and diameter
- Arcs: radius and angle

### Editor Features
- **Undo** (Z key)
- **Clear All** (C key)
- **Toggle Snapping** (G, A, E keys)
- **Save to JSON** (S key)
- **FPS Counter** and status HUD

## Quick Start

### Option 1: Python HTTP Server (Recommended)

```bash
# Navigate to the project directory
cd "AirDraw 3d vortex editor"

# Start a local server
python3 -m http.server 8080

# Open in browser
open http://localhost:8080
```

### Option 2: Node.js HTTP Server

```bash
# Install http-server globally (if not installed)
npm install -g http-server

# Navigate to project directory
cd "AirDraw 3d vortex editor"

# Start server
http-server -p 8080

# Open in browser
open http://localhost:8080
```

### Option 3: VS Code Live Server

1. Install "Live Server" extension in VS Code
2. Open the project folder
3. Right-click `index.html` → "Open with Live Server"

### Browser Requirements
- **Chrome** (recommended) or Firefox
- Webcam access required
- Allow camera permissions when prompted

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Z` | Undo last shape |
| `C` | Clear all shapes |
| `G` | Toggle grid snapping |
| `A` | Toggle angle snapping |
| `E` | Toggle endpoint snapping |
| `S` | Save shapes to JSON |
| `H` | Toggle help overlay |
| `Esc` | Cancel current stroke |

## Project Structure

```
AirDraw 3d vortex editor/
├── index.html              # Main HTML entry
├── styles.css              # Blueprint styling
├── js/
│   ├── settings.js         # Configuration
│   ├── app.js              # Main application
│   ├── utils/
│   │   ├── oneEuroFilter.js    # Cursor smoothing
│   │   └── math.js             # Geometry utilities
│   ├── tracking/
│   │   ├── handTracker.js      # MediaPipe wrapper
│   │   └── gestureDetector.js  # Gesture classification
│   ├── drawing/
│   │   ├── snapSystem.js       # Snapping logic
│   │   ├── shapeRecognizer.js  # Shape fitting
│   │   └── blueprintRenderer.js # Canvas rendering
│   └── state/
│       └── editorState.js      # App state management
└── README.md
```

## Configuration

Edit `js/settings.js` to tune parameters:

```javascript
// Smoothing (One Euro Filter)
oneEuroFilter: {
  minCutoff: 1.0,    // Lower = more smooth
  beta: 0.007,       // Higher = more responsive to speed
}

// Gesture thresholds
gesture: {
  pinchThreshold: 0.05,       // Distance for pinch detection
  fingerUpThreshold: 0.02,    // Y-difference for "finger up"
}

// Snapping
snap: {
  gridSize: 20,               // Grid spacing in pixels
  angleSnapThreshold: 10,     // Degrees tolerance
  endpointSnapThreshold: 15,  // Pixels for endpoint snap
}

// Shape recognition
shapeRecognition: {
  lineErrorThreshold: 8,      // Max error for line fit
  circleErrorThreshold: 15,   // Max error for circle fit
  rectAngleTolerance: 20,     // Degrees from 90° for rectangle
}
```

## How to Test

### Basic Drawing Test
1. Start the app and allow camera access
2. Hold up your index finger (pointing gesture)
3. Move your finger - cursor should follow smoothly
4. Draw a line and lift finger - should recognize as "Line"

### Shape Recognition Test
1. **Line**: Draw a straight stroke
2. **Rectangle**: Draw a closed rectangular shape
3. **Circle**: Draw a closed circular shape
4. **Arc**: Draw a partial circle (don't close it)

### Snap System Test
1. Draw a line, note it snaps to grid
2. Draw another line starting near the first line's endpoint
3. Observe endpoint snap indicator (red circle)
4. Draw a line at ~45° angle - should snap to exactly 45°

### Gesture Test
1. Point with index finger → DRAW mode (red cursor)
2. Open palm → HOVER mode (green cursor)
3. Pinch thumb + index → DRAW mode
4. Two fingers up → HOVER mode

## Debug Checklist

### Camera Issues
- [ ] Browser has camera permissions
- [ ] No other app using webcam
- [ ] Check browser console for errors

### Tracking Issues
- [ ] Hand is visible in frame
- [ ] Good lighting conditions
- [ ] Hand not too close/far from camera
- [ ] Background isn't confusing the tracker

### Performance Issues
- [ ] FPS should be ≥25 (check HUD)
- [ ] Close other heavy browser tabs
- [ ] Try reducing `modelComplexity` in settings

### Shape Recognition Issues
- [ ] Stroke too short? (minimum ~10px)
- [ ] Drawing too fast? (reduce speed slightly)
- [ ] Check `shapeRecognition` thresholds in settings

## Technical Details

### One Euro Filter
Speed-adaptive smoothing filter that reduces jitter while maintaining responsiveness:
- Low speed → high smoothing (reduces jitter)
- High speed → low smoothing (reduces lag)

### Shape Fitting Algorithms
- **Line**: Least squares fit, measures perpendicular distance error
- **Circle**: Kasa algebraic circle fit
- **Rectangle**: RDP simplification → detect 4 corners → check angles

### Coordinate System
- Camera coordinates are mirrored (selfie view)
- Origin is top-left of canvas
- Y increases downward
- All dimensions in pixels (1 unit = 10 pixels default)

## Known Limitations

- Single hand tracking only
- Works best with good lighting
- May struggle with complex backgrounds
- No 3D extrusion (Milestone 1 scope)

## Future Milestones

- [ ] 3D extrusion and viewing
- [ ] Room/wall/door primitives
- [ ] Export to CAD formats
- [ ] Multi-hand support
- [ ] Voice commands

---

Built with MediaPipe Hands and Canvas2D.
