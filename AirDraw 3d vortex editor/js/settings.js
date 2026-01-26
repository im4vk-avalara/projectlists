/**
 * AirDraw Blueprint - Configuration Settings
 * All tunable parameters for the application
 */

export const SETTINGS = {
  // Canvas dimensions
  canvas: {
    width: 1280,
    height: 720,
  },

  // One Euro Filter parameters for cursor smoothing
  // Lower minCutoff = more smoothing (less jittery)
  // Higher beta = more responsive to fast movements
  oneEuroFilter: {
    minCutoff: 0.4,      // Lower = smoother cursor (was 1.0)
    beta: 0.02,          // Speed coefficient (was 0.007)
    dCutoff: 1.0,        // Derivative cutoff frequency
  },

  // Hand tracking
  tracking: {
    modelComplexity: 1,      // 0, 1, or 2 (higher = more accurate but slower)
    maxHands: 1,             // We only track one hand
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.5,
  },

  // Gesture detection thresholds
  gesture: {
    // Pinch detection: distance between thumb tip and index tip
    pinchThreshold: 0.06,        // Normalized distance (relative to hand size)
    pinchReleaseThreshold: 0.10, // Hysteresis to prevent flicker (wider gap)
    
    // Finger up/down detection (y-difference thresholds)
    fingerUpThreshold: 0.03,     // Tip must be higher than PIP by this amount (more tolerant)
    fingerDownThreshold: -0.02,  // Tip must be lower than PIP
    
    // Gesture stability settings
    gestureDebounceMs: 150,      // Minimum time (ms) before gesture change registers
    modeDebounceMs: 300,         // Minimum time (ms) before interaction mode changes
    consecutiveFrames: 5,        // Number of consecutive frames needed to confirm gesture
  },

  // Snapping system
  snap: {
    gridSize: 20,            // Grid spacing in pixels
    gridEnabled: true,
    
    angleSnapEnabled: true,
    angleSnapAngles: [0, 45, 90, 135, 180, 225, 270, 315], // Degrees
    angleSnapThreshold: 10,  // Degrees tolerance for angle snapping
    
    endpointSnapEnabled: true,
    endpointSnapThreshold: 15, // Pixels distance to snap to endpoint
  },

  // Shape recognition
  shapeRecognition: {
    // Minimum points to attempt recognition
    minPoints: 5,
    
    // Line detection
    lineErrorThreshold: 8,      // Max perpendicular distance for line fit (pixels)
    
    // Rectangle detection
    rectClosureThreshold: 30,   // Max distance between start and end for closed shape
    rectAngleTolerance: 20,     // Degrees tolerance from 90°
    rectMinSideRatio: 0.2,      // Minimum aspect ratio for rectangle sides
    
    // Circle detection
    circleErrorThreshold: 15,   // Max radial error for circle fit (pixels)
    circleClosureThreshold: 40, // Max distance between start and end for closed circle
    arcMinAngle: 45,            // Minimum arc angle to be considered an arc (degrees)
    
    // RDP simplification
    rdpEpsilon: 5,              // Tolerance for Ramer-Douglas-Peucker
  },

  // Blueprint rendering style
  blueprint: {
    backgroundColor: '#0a1628',
    gridColor: 'rgba(30, 80, 150, 0.3)',
    gridMajorColor: 'rgba(50, 120, 200, 0.5)',
    gridMajorInterval: 5,      // Every N lines is a major line
    
    axisColor: 'rgba(100, 180, 255, 0.6)',
    
    strokeColor: '#00d4ff',
    strokeWidth: 2,
    strokeGlow: 'rgba(0, 212, 255, 0.5)',
    strokeGlowBlur: 8,
    
    previewColor: 'rgba(0, 212, 255, 0.5)',
    previewDash: [5, 5],
    
    cursorColor: '#00ff88',
    cursorRadius: 8,
    cursorTrailLength: 15,
    cursorTrailColor: 'rgba(0, 255, 136, 0.3)',
    
    dimensionColor: '#ffffff',
    dimensionFontSize: 12,
    dimensionOffset: 15,
  },

  // Unit system
  units: {
    pixelsPerUnit: 10,          // 1 unit = 10 pixels
    displayDecimals: 1,
    unitLabel: 'u',
  },

  // Performance
  performance: {
    targetFPS: 30,
    fpsUpdateInterval: 500,     // ms between FPS display updates
  },

  // Drawing
  drawing: {
    minStrokeLength: 10,        // Minimum length to register a stroke
    pointSamplingRate: 16,      // ms between point samples (approx 60Hz)
  },
};

// Make settings globally accessible for debugging
if (typeof window !== 'undefined') {
  window.AIRDRAW_SETTINGS = SETTINGS;
}
