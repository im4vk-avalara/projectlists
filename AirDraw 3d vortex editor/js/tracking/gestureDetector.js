/**
 * Gesture Detector Module
 * Detects drawing gestures (pen down/up) from hand landmarks
 */

import { SETTINGS } from '../settings.js';
import { LANDMARKS } from './handTracker.js';
import { distance } from '../utils/math.js';

// Gesture states
export const GestureState = {
  NONE: 'none',           // No hand detected
  PEN_DOWN: 'pen_down',   // Drawing mode
  PEN_UP: 'pen_up',       // Not drawing (hover mode)
};

// Specific gestures detected
export const GestureType = {
  NONE: 'none',
  POINTING: 'pointing',       // Index up, others down
  PINCH: 'pinch',             // Thumb-index pinch (close)
  OPEN_PALM: 'open_palm',     // All fingers extended
  TWO_FINGER: 'two_finger',   // Two fingers up
  FIST: 'fist',               // All fingers down
  GRAB: 'grab',               // All fingers curled (for dragging)
  SPREAD: 'spread',           // Thumb and index spread apart (for resizing)
  THUMBS_DOWN: 'thumbs_down', // Thumb pointing down (for delete)
};

// 3D interaction modes
export const InteractionMode = {
  NONE: 'none',
  HOVER: 'hover',
  DRAG: 'drag',
  RESIZE: 'resize',
  DELETE: 'delete',
};

export class GestureDetector {
  constructor() {
    // Current gesture state
    this.currentState = GestureState.NONE;
    this.currentGesture = GestureType.NONE;
    
    // CONFIRMED states (after debounce)
    this.confirmedState = GestureState.NONE;
    this.confirmedGesture = GestureType.NONE;
    
    // Previous state for hysteresis
    this.previousState = GestureState.NONE;
    
    // Pinch state with hysteresis
    this.isPinching = false;
    
    // Finger states (extended or not)
    this.fingerStates = {
      thumb: false,
      index: false,
      middle: false,
      ring: false,
      pinky: false,
    };
    
    // 3D interaction state
    this.interactionMode = InteractionMode.NONE;
    this.confirmedInteractionMode = InteractionMode.NONE;
    this.previousInteractionMode = InteractionMode.NONE;
    
    // Pinch scale tracking (for resize gesture)
    this.pinchDistance = 0;
    this.previousPinchDistance = 0;
    this.pinchDelta = 0;  // Change in pinch distance per frame
    this.pinchScaleFactor = 1.0;  // Multiplier for resizing
    this.pinchDeltaSmoothed = 0;  // Smoothed delta for stability
    
    // Spread gesture thresholds
    this.spreadThreshold = 0.15;  // Distance to detect spread gesture (was 0.12)
    this.pinchCloseThreshold = 0.06;  // Distance to detect close pinch (was 0.05)
    
    // Thumbs down detection
    this.isThumbsDown = false;
    this.thumbsDownFrames = 0;  // Consecutive frames with thumbs down
    
    // Grab state (fist while over an object)
    this.isGrabbing = false;
    this.grabStarted = false;
    
    // DEBOUNCING: Prevent rapid mode switching
    this.gestureFrameCount = 0;     // Frames with same gesture
    this.pendingGesture = GestureType.NONE;
    this.lastGestureChangeTime = 0;
    
    this.modeFrameCount = 0;        // Frames with same mode
    this.pendingMode = InteractionMode.NONE;
    this.lastModeChangeTime = 0;
    
    // State change callbacks
    this.onStateChange = null;
    this.onInteractionChange = null;
  }

  /**
   * Analyze hand landmarks and determine gesture state
   * @param {Array} landmarks - MediaPipe hand landmarks (21 points)
   * @param {number} canvasWidth - Canvas width for coordinate conversion
   * @param {number} canvasHeight - Canvas height for coordinate conversion
   * @returns {{state: string, gesture: string, confidence: number}}
   */
  detect(landmarks, canvasWidth, canvasHeight) {
    if (!landmarks) {
      const result = {
        state: GestureState.NONE,
        gesture: GestureType.NONE,
        fingerStates: this.fingerStates,
        isPinching: false,
        confidence: 0,
      };
      
      this.updateState(result.state, result.gesture);
      return result;
    }

    // Analyze finger positions
    this.analyzeFingers(landmarks);
    
    // Check for pinch gesture
    const pinchInfo = this.detectPinch(landmarks, canvasWidth, canvasHeight);
    
    // Determine the gesture type
    const gesture = this.classifyGesture(pinchInfo);
    
    // Determine pen down/up state based on gesture
    const state = this.determinePenState(gesture, pinchInfo);
    
    // Detect thumbs down gesture (with frame counting for stability)
    this.detectThumbsDown(landmarks);
    
    // Calculate pinch scale for resizing (smoothed)
    this.calculatePinchScale(pinchInfo.distance);
    
    // DEBOUNCE: Apply gesture debouncing
    const confirmedGesture = this.debounceGesture(gesture);
    const confirmedState = this.determinePenState(confirmedGesture, pinchInfo);
    
    // Determine 3D interaction mode (from confirmed gesture)
    const rawInteractionMode = this.determine3DInteractionMode(confirmedGesture, pinchInfo);
    const confirmedInteractionMode = this.debounceInteractionMode(rawInteractionMode);
    
    const result = {
      state: confirmedState,
      gesture: confirmedGesture,
      fingerStates: { ...this.fingerStates },
      isPinching: this.isPinching,
      pinchDistance: pinchInfo.distance,
      pinchDelta: this.pinchDeltaSmoothed,
      pinchScaleFactor: this.pinchScaleFactor,
      isThumbsDown: this.thumbsDownFrames >= 3,  // Require 3 frames
      isGrabbing: this.isGrabbing,
      interactionMode: confirmedInteractionMode,
      confidence: this.calculateConfidence(landmarks),
    };
    
    this.updateState(confirmedState, confirmedGesture);
    this.updateInteractionMode(confirmedInteractionMode);
    return result;
  }

  /**
   * Debounce gesture changes - require consecutive frames
   */
  debounceGesture(rawGesture) {
    const requiredFrames = SETTINGS.gesture.consecutiveFrames || 5;
    
    if (rawGesture === this.pendingGesture) {
      this.gestureFrameCount++;
    } else {
      this.pendingGesture = rawGesture;
      this.gestureFrameCount = 1;
    }
    
    // Only change confirmed gesture after enough consecutive frames
    if (this.gestureFrameCount >= requiredFrames) {
      this.confirmedGesture = this.pendingGesture;
    }
    
    return this.confirmedGesture;
  }

  /**
   * Debounce interaction mode changes
   */
  debounceInteractionMode(rawMode) {
    const requiredFrames = SETTINGS.gesture.consecutiveFrames || 5;
    
    if (rawMode === this.pendingMode) {
      this.modeFrameCount++;
    } else {
      this.pendingMode = rawMode;
      this.modeFrameCount = 1;
    }
    
    // Only change confirmed mode after enough consecutive frames
    if (this.modeFrameCount >= requiredFrames) {
      this.confirmedInteractionMode = this.pendingMode;
    }
    
    return this.confirmedInteractionMode;
  }

  /**
   * Detect thumbs down gesture for deletion
   * Uses frame counting for stability
   */
  detectThumbsDown(landmarks) {
    const thumbTip = landmarks[LANDMARKS.THUMB_TIP];
    const thumbMcp = landmarks[LANDMARKS.THUMB_MCP];
    const wrist = landmarks[LANDMARKS.WRIST];
    
    // Thumb is pointing down if:
    // 1. Thumb tip is significantly below thumb MCP
    // 2. Thumb tip is below wrist
    // 3. Other fingers are curled
    const thumbPointingDown = thumbTip.y > thumbMcp.y + 0.08 &&  // More strict (was 0.05)
                               thumbTip.y > wrist.y + 0.05;
    
    // Check that other fingers are not extended
    const { index, middle, ring, pinky } = this.fingerStates;
    const othersCurled = !index && !middle && !ring && !pinky;
    
    const isThumbsDownNow = thumbPointingDown && othersCurled;
    
    // Require consecutive frames for stability
    if (isThumbsDownNow) {
      this.thumbsDownFrames++;
    } else {
      this.thumbsDownFrames = Math.max(0, this.thumbsDownFrames - 2);  // Decay slowly
    }
    
    // Cap the frame count
    this.thumbsDownFrames = Math.min(this.thumbsDownFrames, 30);
    
    // Only set true after several consecutive frames
    this.isThumbsDown = this.thumbsDownFrames >= 5;
  }

  /**
   * Calculate pinch scale factor for resizing
   * Uses smoothing to prevent jittery resizing
   */
  calculatePinchScale(currentDistance) {
    this.previousPinchDistance = this.pinchDistance;
    this.pinchDistance = currentDistance;
    
    // Calculate raw delta (change in pinch distance)
    const rawDelta = this.pinchDistance - this.previousPinchDistance;
    
    // Smooth the delta using exponential moving average
    const smoothingFactor = 0.3;  // Lower = smoother (0-1)
    this.pinchDeltaSmoothed = this.pinchDeltaSmoothed * (1 - smoothingFactor) + rawDelta * smoothingFactor;
    this.pinchDelta = this.pinchDeltaSmoothed;
    
    // Only apply scale if delta is significant (dead zone)
    const deadZone = 0.003;  // Ignore tiny movements
    if (Math.abs(this.pinchDeltaSmoothed) > deadZone) {
      // Scale factor based on smoothed delta
      this.pinchScaleFactor = 1 + (this.pinchDeltaSmoothed * 2);  // Reduced multiplier (was 3)
    } else {
      this.pinchScaleFactor = 1.0;
    }
    
    // Clamp scale factor (gentler limits)
    this.pinchScaleFactor = Math.max(0.97, Math.min(1.03, this.pinchScaleFactor));
  }

  /**
   * Determine 3D interaction mode based on gesture
   * Uses confirmed (debounced) gestures for stability
   */
  determine3DInteractionMode(gesture, pinchInfo) {
    // Thumbs down = delete mode (already requires consecutive frames)
    if (this.isThumbsDown && this.thumbsDownFrames >= 8) {
      return InteractionMode.DELETE;
    }
    
    // Pinch gesture with significant movement = resize
    // Only trigger resize if pinch is confirmed and delta is meaningful
    if (gesture === GestureType.PINCH && Math.abs(this.pinchDeltaSmoothed) > 0.005) {
      return InteractionMode.RESIZE;
    }
    
    // Closed fist for dragging (must be confirmed)
    if (gesture === GestureType.FIST) {
      return InteractionMode.DRAG;
    }
    
    // Pointing for selection/hover (default active interaction)
    if (gesture === GestureType.POINTING) {
      return InteractionMode.HOVER;
    }
    
    // Open palm = neutral hover
    if (gesture === GestureType.OPEN_PALM) {
      return InteractionMode.HOVER;
    }
    
    // Two finger = also hover
    if (gesture === GestureType.TWO_FINGER) {
      return InteractionMode.HOVER;
    }
    
    return InteractionMode.NONE;
  }

  /**
   * Update interaction mode and trigger callbacks
   */
  updateInteractionMode(newMode) {
    if (newMode !== this.interactionMode) {
      this.previousInteractionMode = this.interactionMode;
      this.interactionMode = newMode;
      
      if (this.onInteractionChange) {
        this.onInteractionChange({
          mode: newMode,
          previousMode: this.previousInteractionMode,
        });
      }
    }
  }

  /**
   * Analyze which fingers are extended
   * Uses the relative Y positions of fingertips vs PIP joints
   * With hysteresis to prevent flickering
   */
  analyzeFingers(landmarks) {
    const upThreshold = SETTINGS.gesture.fingerUpThreshold;
    const downThreshold = SETTINGS.gesture.fingerDownThreshold;
    
    // Helper function with hysteresis
    const checkFingerUp = (currentState, tipY, pipY) => {
      const diff = pipY - tipY;
      if (currentState) {
        // Currently up - need to go below downThreshold to change
        return diff > downThreshold;
      } else {
        // Currently down - need to exceed upThreshold to change
        return diff > upThreshold;
      }
    };
    
    // Index finger
    const indexTip = landmarks[LANDMARKS.INDEX_TIP];
    const indexPip = landmarks[LANDMARKS.INDEX_PIP];
    this.fingerStates.index = checkFingerUp(this.fingerStates.index, indexTip.y, indexPip.y);
    
    // Middle finger
    const middleTip = landmarks[LANDMARKS.MIDDLE_TIP];
    const middlePip = landmarks[LANDMARKS.MIDDLE_PIP];
    this.fingerStates.middle = checkFingerUp(this.fingerStates.middle, middleTip.y, middlePip.y);
    
    // Ring finger
    const ringTip = landmarks[LANDMARKS.RING_TIP];
    const ringPip = landmarks[LANDMARKS.RING_PIP];
    this.fingerStates.ring = checkFingerUp(this.fingerStates.ring, ringTip.y, ringPip.y);
    
    // Pinky
    const pinkyTip = landmarks[LANDMARKS.PINKY_TIP];
    const pinkyPip = landmarks[LANDMARKS.PINKY_PIP];
    this.fingerStates.pinky = checkFingerUp(this.fingerStates.pinky, pinkyTip.y, pinkyPip.y);
    
    // Thumb: different logic - compare to index MCP and use x-coordinate
    const thumbTip = landmarks[LANDMARKS.THUMB_TIP];
    const indexMcp = landmarks[LANDMARKS.INDEX_MCP];
    
    // Check if thumb is extended (with hysteresis)
    const thumbExtension = Math.abs(thumbTip.x - indexMcp.x);
    if (this.fingerStates.thumb) {
      this.fingerStates.thumb = thumbExtension > 0.08;  // Lower threshold to stay extended
    } else {
      this.fingerStates.thumb = thumbExtension > 0.12;  // Higher threshold to become extended
    }
  }

  /**
   * Detect pinch gesture (thumb-index contact)
   */
  detectPinch(landmarks, canvasWidth, canvasHeight) {
    const thumbTip = landmarks[LANDMARKS.THUMB_TIP];
    const indexTip = landmarks[LANDMARKS.INDEX_TIP];
    
    // Calculate distance in normalized coordinates
    // We use a weighted distance to account for aspect ratio
    const dx = (thumbTip.x - indexTip.x);
    const dy = (thumbTip.y - indexTip.y);
    const normalizedDistance = Math.sqrt(dx * dx + dy * dy);
    
    // Apply hysteresis to prevent flickering
    const { pinchThreshold, pinchReleaseThreshold } = SETTINGS.gesture;
    
    if (this.isPinching) {
      // Currently pinching - need to exceed release threshold to un-pinch
      this.isPinching = normalizedDistance < pinchReleaseThreshold;
    } else {
      // Not pinching - need to go below pinch threshold to start pinch
      this.isPinching = normalizedDistance < pinchThreshold;
    }
    
    return {
      isPinching: this.isPinching,
      distance: normalizedDistance,
      thumbPos: { x: thumbTip.x * canvasWidth, y: thumbTip.y * canvasHeight },
      indexPos: { x: indexTip.x * canvasWidth, y: indexTip.y * canvasHeight },
    };
  }

  /**
   * Classify the current gesture type
   */
  classifyGesture(pinchInfo) {
    const { index, middle, ring, pinky, thumb } = this.fingerStates;
    
    // Pinch: thumb and index close together
    if (pinchInfo.isPinching) {
      return GestureType.PINCH;
    }
    
    // Count extended fingers
    const extendedCount = [index, middle, ring, pinky].filter(f => f).length;
    
    // Open palm: all 4 main fingers up
    if (extendedCount >= 4) {
      return GestureType.OPEN_PALM;
    }
    
    // Two finger: index and middle up, others down
    if (index && middle && !ring && !pinky) {
      return GestureType.TWO_FINGER;
    }
    
    // Pointing: only index up
    if (index && !middle && !ring && !pinky) {
      return GestureType.POINTING;
    }
    
    // Fist: no fingers up
    if (extendedCount === 0) {
      return GestureType.FIST;
    }
    
    return GestureType.NONE;
  }

  /**
   * Determine pen down/up state from gesture
   * Pen Down conditions:
   *   - Pointing gesture (index up, others down)
   *   - Pinch gesture
   * Pen Up conditions:
   *   - Open palm
   *   - Two finger mode
   *   - Fist
   */
  determinePenState(gesture, pinchInfo) {
    switch (gesture) {
      case GestureType.POINTING:
        return GestureState.PEN_DOWN;
      
      case GestureType.PINCH:
        return GestureState.PEN_DOWN;
      
      case GestureType.OPEN_PALM:
        return GestureState.PEN_UP;
      
      case GestureType.TWO_FINGER:
        return GestureState.PEN_UP;
      
      case GestureType.FIST:
        return GestureState.PEN_UP;
      
      default:
        // Keep previous state if gesture is unclear
        return this.currentState === GestureState.NONE ? 
               GestureState.PEN_UP : this.currentState;
    }
  }

  /**
   * Calculate detection confidence based on landmark visibility
   */
  calculateConfidence(landmarks) {
    // MediaPipe provides visibility scores for each landmark
    // We average key landmarks for overall confidence
    const keyLandmarks = [
      LANDMARKS.WRIST,
      LANDMARKS.THUMB_TIP,
      LANDMARKS.INDEX_TIP,
      LANDMARKS.MIDDLE_TIP,
    ];
    
    let totalVisibility = 0;
    for (const idx of keyLandmarks) {
      totalVisibility += landmarks[idx].visibility || 0.5;
    }
    
    return totalVisibility / keyLandmarks.length;
  }

  /**
   * Update state and trigger callbacks
   */
  updateState(newState, newGesture) {
    const stateChanged = newState !== this.currentState;
    const gestureChanged = newGesture !== this.currentGesture;
    
    this.previousState = this.currentState;
    this.currentState = newState;
    this.currentGesture = newGesture;
    
    if ((stateChanged || gestureChanged) && this.onStateChange) {
      this.onStateChange({
        state: newState,
        gesture: newGesture,
        previousState: this.previousState,
      });
    }
  }

  /**
   * Get current pen state
   */
  isPenDown() {
    return this.currentState === GestureState.PEN_DOWN;
  }

  /**
   * Get current gesture state
   */
  getState() {
    return {
      state: this.currentState,
      gesture: this.currentGesture,
      fingerStates: { ...this.fingerStates },
      isPinching: this.isPinching,
    };
  }

  /**
   * Reset detector state
   */
  reset() {
    this.currentState = GestureState.NONE;
    this.currentGesture = GestureType.NONE;
    this.previousState = GestureState.NONE;
    this.isPinching = false;
    this.fingerStates = {
      thumb: false,
      index: false,
      middle: false,
      ring: false,
      pinky: false,
    };
  }
}

// Helper function to get gesture name for display
export function getGestureName(gesture) {
  switch (gesture) {
    case GestureType.POINTING: return 'Pointing';
    case GestureType.PINCH: return 'Pinch';
    case GestureType.OPEN_PALM: return 'Open Palm';
    case GestureType.TWO_FINGER: return 'Two Finger';
    case GestureType.FIST: return 'Fist/Grab';
    case GestureType.GRAB: return 'Grab';
    case GestureType.SPREAD: return 'Spread';
    case GestureType.THUMBS_DOWN: return 'Thumbs Down';
    default: return 'None';
  }
}

export function getStateName(state) {
  switch (state) {
    case GestureState.PEN_DOWN: return 'DRAW';
    case GestureState.PEN_UP: return 'HOVER';
    default: return 'NONE';
  }
}

export function getInteractionModeName(mode) {
  switch (mode) {
    case InteractionMode.HOVER: return 'HOVER';
    case InteractionMode.DRAG: return 'DRAG';
    case InteractionMode.RESIZE: return 'RESIZE';
    case InteractionMode.DELETE: return 'DELETE';
    default: return 'NONE';
  }
}
