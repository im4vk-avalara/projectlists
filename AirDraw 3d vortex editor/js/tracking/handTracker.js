/**
 * Hand Tracker Module
 * Wraps MediaPipe Hands for webcam-based hand landmark detection
 */

import { SETTINGS } from '../settings.js';
import { OneEuroFilter2D } from '../utils/oneEuroFilter.js';

// MediaPipe hand landmark indices
export const LANDMARKS = {
  WRIST: 0,
  THUMB_CMC: 1,
  THUMB_MCP: 2,
  THUMB_IP: 3,
  THUMB_TIP: 4,
  INDEX_MCP: 5,
  INDEX_PIP: 6,
  INDEX_DIP: 7,
  INDEX_TIP: 8,
  MIDDLE_MCP: 9,
  MIDDLE_PIP: 10,
  MIDDLE_DIP: 11,
  MIDDLE_TIP: 12,
  RING_MCP: 13,
  RING_PIP: 14,
  RING_DIP: 15,
  RING_TIP: 16,
  PINKY_MCP: 17,
  PINKY_PIP: 18,
  PINKY_DIP: 19,
  PINKY_TIP: 20,
};

export class HandTracker {
  constructor() {
    this.hands = null;
    this.camera = null;
    this.videoElement = null;
    this.canvasWidth = SETTINGS.canvas.width;
    this.canvasHeight = SETTINGS.canvas.height;
    
    // Smoothing filter for cursor position
    // Using settings values for tunable smoothing
    this.cursorFilter = new OneEuroFilter2D(
      SETTINGS.oneEuroFilter.minCutoff,
      SETTINGS.oneEuroFilter.beta,
      SETTINGS.oneEuroFilter.dCutoff
    );
    
    // Additional smoothing buffer for extra stability
    this.smoothingBuffer = [];
    this.smoothingBufferSize = 3;  // Average last N positions
    
    // Current tracking state
    this.isTracking = false;
    this.lastLandmarks = null;
    this.lastTimestamp = 0;
    
    // Raw and smoothed cursor positions
    this.rawCursor = { x: 0, y: 0 };
    this.smoothedCursor = { x: 0, y: 0 };
    
    // Cursor trail for visual effect
    this.cursorTrail = [];
    
    // Callbacks
    this.onResults = null;
  }

  /**
   * Initialize MediaPipe Hands and webcam
   * @param {HTMLVideoElement} videoElement - Video element for webcam feed
   * @returns {Promise<void>}
   */
  async initialize(videoElement) {
    this.videoElement = videoElement;
    
    // Check if MediaPipe is loaded
    if (typeof Hands === 'undefined') {
      throw new Error('MediaPipe Hands not loaded. Please include the MediaPipe scripts.');
    }

    // Create MediaPipe Hands instance
    this.hands = new Hands({
      locateFile: (file) => {
        return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
      }
    });

    // Configure hand detection
    this.hands.setOptions({
      maxNumHands: SETTINGS.tracking.maxHands,
      modelComplexity: SETTINGS.tracking.modelComplexity,
      minDetectionConfidence: SETTINGS.tracking.minDetectionConfidence,
      minTrackingConfidence: SETTINGS.tracking.minTrackingConfidence,
    });

    // Set up results callback
    this.hands.onResults((results) => this.processResults(results));

    // Initialize webcam
    await this.initCamera();
    
    this.isTracking = true;
  }

  /**
   * Initialize webcam using MediaPipe Camera Utils
   */
  async initCamera() {
    return new Promise((resolve, reject) => {
      if (typeof Camera === 'undefined') {
        // Fall back to manual webcam setup
        this.initCameraManual().then(resolve).catch(reject);
        return;
      }

      this.camera = new Camera(this.videoElement, {
        onFrame: async () => {
          if (this.hands && this.isTracking) {
            await this.hands.send({ image: this.videoElement });
          }
        },
        width: this.canvasWidth,
        height: this.canvasHeight,
      });

      this.camera.start()
        .then(() => resolve())
        .catch((err) => reject(err));
    });
  }

  /**
   * Manual webcam initialization fallback
   */
  async initCameraManual() {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: this.canvasWidth },
        height: { ideal: this.canvasHeight },
        facingMode: 'user',
      }
    });

    this.videoElement.srcObject = stream;
    await this.videoElement.play();

    // Start processing loop
    this.processLoop();
  }

  /**
   * Manual processing loop (fallback when Camera utils not available)
   */
  async processLoop() {
    if (!this.isTracking) return;

    if (this.videoElement.readyState >= 2) {
      await this.hands.send({ image: this.videoElement });
    }

    requestAnimationFrame(() => this.processLoop());
  }

  /**
   * Process hand detection results from MediaPipe
   */
  processResults(results) {
    const timestamp = performance.now() / 1000;
    this.lastTimestamp = timestamp;

    if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
      // Get first hand's landmarks
      const landmarks = results.multiHandLandmarks[0];
      this.lastLandmarks = landmarks;

      // Get index fingertip position (our cursor)
      const indexTip = landmarks[LANDMARKS.INDEX_TIP];
      
      // Convert normalized coordinates to canvas coordinates
      // MediaPipe gives normalized coords (0-1), we need to:
      // 1. Mirror horizontally (selfie view)
      // 2. Scale to canvas dimensions
      const rawX = (1 - indexTip.x) * this.canvasWidth;  // Mirror for selfie view
      const rawY = indexTip.y * this.canvasHeight;
      
      this.rawCursor = { x: rawX, y: rawY };
      
      // Apply One Euro Filter for smoothing
      const filteredPos = this.cursorFilter.filter(rawX, rawY, timestamp);
      
      // Apply additional averaging for extra smoothness
      this.smoothingBuffer.push({ x: filteredPos.x, y: filteredPos.y });
      if (this.smoothingBuffer.length > this.smoothingBufferSize) {
        this.smoothingBuffer.shift();
      }
      
      // Average the buffer
      let avgX = 0, avgY = 0;
      for (const pos of this.smoothingBuffer) {
        avgX += pos.x;
        avgY += pos.y;
      }
      avgX /= this.smoothingBuffer.length;
      avgY /= this.smoothingBuffer.length;
      
      this.smoothedCursor = { x: avgX, y: avgY };
      
      // Update cursor trail
      this.updateCursorTrail(this.smoothedCursor);
    } else {
      // No hand detected
      this.lastLandmarks = null;
    }

    // Call external callback if set
    if (this.onResults) {
      this.onResults({
        landmarks: this.lastLandmarks,
        rawCursor: this.rawCursor,
        smoothedCursor: this.smoothedCursor,
        timestamp,
      });
    }
  }

  /**
   * Update cursor trail for visual feedback
   */
  updateCursorTrail(position) {
    this.cursorTrail.push({ ...position });
    
    // Limit trail length
    const maxLength = SETTINGS.blueprint.cursorTrailLength;
    while (this.cursorTrail.length > maxLength) {
      this.cursorTrail.shift();
    }
  }

  /**
   * Clear the cursor trail
   */
  clearTrail() {
    this.cursorTrail = [];
  }

  /**
   * Get current cursor position (smoothed)
   */
  getCursor() {
    return this.smoothedCursor;
  }

  /**
   * Get raw cursor position (unsmoothed)
   */
  getRawCursor() {
    return this.rawCursor;
  }

  /**
   * Get cursor trail
   */
  getTrail() {
    return this.cursorTrail;
  }

  /**
   * Check if hand is currently detected
   */
  isHandDetected() {
    return this.lastLandmarks !== null;
  }

  /**
   * Get current landmarks
   */
  getLandmarks() {
    return this.lastLandmarks;
  }

  /**
   * Get a specific landmark in canvas coordinates
   */
  getLandmarkPosition(index) {
    if (!this.lastLandmarks) return null;
    
    const landmark = this.lastLandmarks[index];
    return {
      x: (1 - landmark.x) * this.canvasWidth,  // Mirror for selfie view
      y: landmark.y * this.canvasHeight,
      z: landmark.z,  // Depth (relative)
    };
  }

  /**
   * Update smoothing parameters
   */
  updateSmoothingParams(minCutoff, beta, dCutoff) {
    this.cursorFilter.setParameters(minCutoff, beta, dCutoff);
  }

  /**
   * Reset the tracker state
   */
  reset() {
    this.cursorFilter.reset();
    this.cursorTrail = [];
    this.lastLandmarks = null;
  }

  /**
   * Stop tracking and release resources
   */
  stop() {
    this.isTracking = false;
    
    if (this.camera) {
      this.camera.stop();
    }
    
    if (this.videoElement && this.videoElement.srcObject) {
      const tracks = this.videoElement.srcObject.getTracks();
      tracks.forEach(track => track.stop());
    }
  }
}
