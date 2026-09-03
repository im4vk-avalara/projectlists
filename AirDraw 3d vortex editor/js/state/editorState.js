/**
 * Editor State Module
 * Manages application state including shapes, undo/redo, and current drawing
 */

import { SETTINGS } from '../settings.js';

export class EditorState {
  constructor() {
    // Committed shapes (recognized and finalized)
    this.shapes = [];
    
    // Undo history
    this.undoStack = [];
    this.maxUndoHistory = 50;
    
    // Current stroke being drawn
    this.currentStroke = [];
    this.isDrawing = false;
    this.strokeStartTime = null;
    this.lastPointTime = 0;
    
    // Preview of recognized shape (before commit)
    this.previewShape = null;
    
    // Anchor point for angle snapping (typically first point of current stroke)
    this.strokeAnchor = null;
    
    // Cursor state
    this.cursor = { x: 0, y: 0 };
    this.cursorTrail = [];
    this.handDetected = false;
    this.landmarks = null;  // Raw hand landmarks for visualization
    
    // Pen state
    this.isPenDown = false;
    this.wasPenDown = false;
    
    // Snap info for visual feedback
    this.snapInfo = null;
    
    // Ghost preview for snapping visualization
    this.ghostPreview = null;
    
    // Gesture info for HUD
    this.currentGesture = 'None';
    
    // FPS tracking
    this.fps = 0;
    this.frameCount = 0;
    this.lastFPSUpdate = performance.now();
    
    // Shape counter for IDs
    this.shapeIdCounter = 0;
  }

  /**
   * Start a new stroke
   * @param {Object} point - Starting point {x, y}
   */
  startStroke(point) {
    this.isDrawing = true;
    this.currentStroke = [];
    this.strokeStartTime = performance.now();
    this.lastPointTime = 0;
    
    // Set anchor for angle snapping
    this.strokeAnchor = { ...point };
    
    // Add first point
    this.addStrokePoint(point);
  }

  /**
   * Add a point to the current stroke
   * @param {Object} point - Point to add {x, y}
   */
  addStrokePoint(point) {
    if (!this.isDrawing) return;
    
    const now = performance.now();
    const elapsed = now - this.strokeStartTime;
    
    // Rate limit point sampling
    if (elapsed - this.lastPointTime < SETTINGS.drawing.pointSamplingRate) {
      return;
    }
    
    this.currentStroke.push({
      x: point.x,
      y: point.y,
      timestamp: elapsed,
    });
    
    this.lastPointTime = elapsed;
  }

  /**
   * End the current stroke and return points for recognition
   * @returns {Array} Stroke points
   */
  endStroke() {
    const stroke = this.currentStroke.slice();
    
    this.isDrawing = false;
    this.currentStroke = [];
    this.strokeAnchor = null;
    this.previewShape = null;
    
    return stroke;
  }

  /**
   * Cancel current stroke without committing
   */
  cancelStroke() {
    this.isDrawing = false;
    this.currentStroke = [];
    this.strokeAnchor = null;
    this.previewShape = null;
  }

  /**
   * Set preview shape (shown during drawing before commit)
   */
  setPreviewShape(shape) {
    this.previewShape = shape;
  }

  /**
   * Add a recognized shape
   * @param {Object} shape - Shape object to add
   */
  addShape(shape) {
    // Assign unique ID
    shape.id = ++this.shapeIdCounter;
    
    // Save for undo
    this.pushUndo('add', shape);
    
    // Add to shapes list
    this.shapes.push(shape);
    
    return shape;
  }

  /**
   * Remove the last shape (for undo)
   */
  removeLastShape() {
    if (this.shapes.length > 0) {
      return this.shapes.pop();
    }
    return null;
  }

  /**
   * Push an action to the undo stack
   */
  pushUndo(actionType, shape) {
    this.undoStack.push({
      type: actionType,
      shape: { ...shape },
      timestamp: Date.now(),
    });
    
    // Limit undo history
    while (this.undoStack.length > this.maxUndoHistory) {
      this.undoStack.shift();
    }
  }

  /**
   * Undo the last action
   * @returns {boolean} True if undo was performed
   */
  undo() {
    if (this.undoStack.length === 0) {
      return false;
    }
    
    const action = this.undoStack.pop();
    
    if (action.type === 'add') {
      // Remove the shape that was added
      const idx = this.shapes.findIndex(s => s.id === action.shape.id);
      if (idx !== -1) {
        this.shapes.splice(idx, 1);
        return true;
      }
    }
    
    return false;
  }

  /**
   * Clear all shapes
   */
  clearAll() {
    // Save all shapes for potential undo
    for (const shape of this.shapes) {
      this.pushUndo('add', shape);
    }
    
    this.shapes = [];
  }

  /**
   * Get all shapes
   */
  getShapes() {
    return this.shapes;
  }

  /**
   * Get current drawing state for rendering
   */
  getRenderState() {
    return {
      shapes: this.shapes,
      currentStroke: this.currentStroke,
      isDrawing: this.isDrawing,
      previewShape: this.previewShape,
      cursor: this.cursor,
      cursorTrail: this.cursorTrail,
      handDetected: this.handDetected,
      isPenDown: this.isPenDown,
      snapInfo: this.snapInfo,
      ghostPreview: this.ghostPreview,
      landmarks: this.landmarks,
      canvasWidth: SETTINGS.canvas.width,
      canvasHeight: SETTINGS.canvas.height,
    };
  }

  /**
   * Update cursor position
   */
  setCursor(position, trail) {
    this.cursor = { ...position };
    if (trail) {
      this.cursorTrail = trail;
    }
  }

  /**
   * Update hand detection status
   */
  setHandDetected(detected) {
    this.handDetected = detected;
  }

  /**
   * Set raw hand landmarks for visualization
   */
  setLandmarks(landmarks) {
    this.landmarks = landmarks;
  }

  /**
   * Update pen state
   */
  setPenState(isPenDown) {
    this.wasPenDown = this.isPenDown;
    this.isPenDown = isPenDown;
  }

  /**
   * Check if pen just went down (transition from up to down)
   */
  didPenGoDown() {
    return this.isPenDown && !this.wasPenDown;
  }

  /**
   * Check if pen just went up (transition from down to up)
   */
  didPenGoUp() {
    return !this.isPenDown && this.wasPenDown;
  }

  /**
   * Update snap info for visual feedback
   */
  setSnapInfo(info) {
    this.snapInfo = info;
  }

  /**
   * Set ghost preview for snapping
   */
  setGhostPreview(preview) {
    this.ghostPreview = preview;
  }

  /**
   * Update gesture info
   */
  setGesture(gesture) {
    this.currentGesture = gesture;
  }

  /**
   * Update FPS counter
   */
  updateFPS() {
    this.frameCount++;
    const now = performance.now();
    const elapsed = now - this.lastFPSUpdate;
    
    if (elapsed >= SETTINGS.performance.fpsUpdateInterval) {
      this.fps = Math.round((this.frameCount * 1000) / elapsed);
      this.frameCount = 0;
      this.lastFPSUpdate = now;
    }
  }

  /**
   * Get HUD data for display
   */
  getHUDData(snapSystem) {
    return {
      mode: this.isPenDown ? 'DRAW' : 'HOVER',
      gesture: this.currentGesture,
      fps: this.fps,
      shapeCount: this.shapes.length,
      snapStatus: snapSystem ? snapSystem.getSnapStatus() : { grid: false, angle: false, endpoint: false },
      handDetected: this.handDetected,
    };
  }

  /**
   * Get stroke anchor point
   */
  getStrokeAnchor() {
    return this.strokeAnchor;
  }

  /**
   * Check if current stroke is long enough to be valid
   */
  isStrokeValid() {
    if (this.currentStroke.length < 2) return false;
    
    const first = this.currentStroke[0];
    const last = this.currentStroke[this.currentStroke.length - 1];
    const dx = last.x - first.x;
    const dy = last.y - first.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    
    return length >= SETTINGS.drawing.minStrokeLength;
  }

  /**
   * Export shapes to JSON
   */
  exportToJSON() {
    return JSON.stringify({
      version: '1.0',
      timestamp: Date.now(),
      shapes: this.shapes,
    }, null, 2);
  }

  /**
   * Import shapes from JSON
   */
  importFromJSON(jsonString) {
    try {
      const data = JSON.parse(jsonString);
      if (data.shapes && Array.isArray(data.shapes)) {
        this.shapes = data.shapes;
        // Update ID counter
        for (const shape of this.shapes) {
          if (shape.id && shape.id > this.shapeIdCounter) {
            this.shapeIdCounter = shape.id;
          }
        }
        return true;
      }
    } catch (e) {
      console.error('Failed to import JSON:', e);
    }
    return false;
  }

  /**
   * Reset all state
   */
  reset() {
    this.shapes = [];
    this.undoStack = [];
    this.currentStroke = [];
    this.isDrawing = false;
    this.previewShape = null;
    this.strokeAnchor = null;
    this.shapeIdCounter = 0;
  }
}
