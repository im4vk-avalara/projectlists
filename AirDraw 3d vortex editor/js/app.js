/**
 * AirDraw Blueprint - Main Application
 * Ties together all modules for the hand-tracking CAD drawing experience
 * Supports both 2D drawing and 3D cube manipulation modes
 */

import { SETTINGS } from './settings.js';
import { HandTracker } from './tracking/handTracker.js';
import { GestureDetector, GestureState, getGestureName, getStateName } from './tracking/gestureDetector.js';
import { SnapSystem } from './drawing/snapSystem.js';
import { ShapeRecognizer } from './drawing/shapeRecognizer.js';
import { BlueprintRenderer } from './drawing/blueprintRenderer.js';
import { EditorState } from './state/editorState.js';
import { App3D } from './3d/app3D.js';

// Application modes
export const AppMode = {
  MODE_2D: '2d',
  MODE_3D: '3d',
};

export class AirDrawApp {
  constructor() {
    // DOM elements
    this.videoElement = null;
    this.canvasElement = null;
    this.appContainer = null;
    
    // Current mode
    this.currentMode = AppMode.MODE_2D;
    
    // 2D Modules
    this.handTracker = null;
    this.gestureDetector = null;
    this.snapSystem = null;
    this.shapeRecognizer = null;
    this.renderer = null;
    this.state = null;
    
    // 3D Module
    this.app3D = null;
    
    // App state
    this.isRunning = false;
    this.showHelp = true;
    
    // Animation frame ID
    this.animationFrameId = null;
    
    // Bind methods
    this.mainLoop = this.mainLoop.bind(this);
    this.handleKeyboard = this.handleKeyboard.bind(this);
  }

  /**
   * Initialize the application
   */
  async initialize() {
    console.log('🎨 AirDraw Blueprint - Initializing...');
    
    // Get DOM elements
    this.videoElement = document.getElementById('webcam');
    this.canvasElement = document.getElementById('canvas');
    this.appContainer = document.getElementById('app');
    
    if (!this.videoElement || !this.canvasElement) {
      throw new Error('Required DOM elements not found (webcam, canvas)');
    }
    
    // Check selected mode from UI
    this.currentMode = this.getSelectedMode();
    
    // Set up mode selector buttons
    this.setupModeSelector();
    
    // Set up keyboard controls
    document.addEventListener('keydown', this.handleKeyboard);
    
    if (this.currentMode === AppMode.MODE_3D) {
      await this.initialize3DMode();
    } else {
      await this.initialize2DMode();
    }
    
    console.log(`✅ AirDraw Blueprint - Ready in ${this.currentMode.toUpperCase()} mode!`);
  }

  /**
   * Get selected mode from UI
   */
  getSelectedMode() {
    const mode3dBtn = document.getElementById('mode-3d-btn');
    if (mode3dBtn && mode3dBtn.classList.contains('active')) {
      return AppMode.MODE_3D;
    }
    return AppMode.MODE_2D;
  }

  /**
   * Set up mode selector buttons
   */
  setupModeSelector() {
    const mode2dBtn = document.getElementById('mode-2d-btn');
    const mode3dBtn = document.getElementById('mode-3d-btn');
    
    if (mode2dBtn) {
      mode2dBtn.addEventListener('click', () => {
        mode2dBtn.classList.add('active');
        mode3dBtn?.classList.remove('active');
        this.currentMode = AppMode.MODE_2D;
      });
    }
    
    if (mode3dBtn) {
      mode3dBtn.addEventListener('click', () => {
        mode3dBtn.classList.add('active');
        mode2dBtn?.classList.remove('active');
        this.currentMode = AppMode.MODE_3D;
      });
    }
  }

  /**
   * Initialize 2D drawing mode
   */
  async initialize2DMode() {
    console.log('📝 Initializing 2D Drawing Mode...');
    
    // Initialize 2D modules
    this.state = new EditorState();
    this.gestureDetector = new GestureDetector();
    this.snapSystem = new SnapSystem();
    this.shapeRecognizer = new ShapeRecognizer();
    this.renderer = new BlueprintRenderer(this.canvasElement);
    this.handTracker = new HandTracker();
    
    // Set up hand tracking callback
    this.handTracker.onResults = (results) => this.onHandResults(results);
    
    // Set up gesture state change callback
    this.gestureDetector.onStateChange = (change) => this.onGestureStateChange(change);
    
    // Initialize hand tracking (requests webcam access)
    try {
      await this.handTracker.initialize(this.videoElement);
      console.log('✅ Hand tracking initialized');
      
      // Pass video element to renderer for background display
      this.renderer.setVideoElement(this.videoElement);
    } catch (error) {
      console.error('❌ Failed to initialize hand tracking:', error);
      this.showError('Failed to access webcam. Please allow camera access and refresh.');
      throw error;
    }
    
    // Hide 3D tutorial, show 2D elements
    this.toggle3DTutorial(false);
    this.canvasElement.style.display = 'block';
    
    // Start the main loop
    this.isRunning = true;
    this.mainLoop();
  }

  /**
   * Initialize 3D cube mode
   */
  async initialize3DMode() {
    console.log('🎮 Initializing 3D Cube Mode...');
    
    // Hide 2D canvas
    this.canvasElement.style.display = 'none';
    
    // Initialize 3D app
    this.app3D = new App3D(this.appContainer);
    
    try {
      await this.app3D.initialize(this.videoElement);
      console.log('✅ 3D Mode initialized');
      
      // Show 3D tutorial
      this.toggle3DTutorial(true);
    } catch (error) {
      console.error('❌ Failed to initialize 3D mode:', error);
      this.showError('Failed to initialize 3D mode. Please refresh.');
      throw error;
    }
  }

  /**
   * Switch between modes
   */
  async switchMode(newMode) {
    if (newMode === this.currentMode) return;
    
    console.log(`🔄 Switching to ${newMode.toUpperCase()} mode...`);
    
    // Stop current mode
    this.stop();
    
    // Clean up current mode
    if (this.currentMode === AppMode.MODE_3D && this.app3D) {
      this.app3D.stop();
      // Remove 3D canvas
      const canvas3d = document.getElementById('canvas3d');
      if (canvas3d) canvas3d.remove();
      const hudCanvas = document.getElementById('hud-canvas');
      if (hudCanvas) hudCanvas.remove();
      this.app3D = null;
    }
    
    // Reset state
    this.handTracker = null;
    this.gestureDetector = null;
    this.state = null;
    this.renderer = null;
    
    // Set new mode
    this.currentMode = newMode;
    
    // Initialize new mode
    if (newMode === AppMode.MODE_3D) {
      await this.initialize3DMode();
    } else {
      await this.initialize2DMode();
    }
    
    console.log(`✅ Switched to ${newMode.toUpperCase()} mode`);
  }

  /**
   * Toggle 3D tutorial visibility
   */
  toggle3DTutorial(show) {
    const tutorial3d = document.getElementById('tutorial-3d');
    if (tutorial3d) {
      if (show) {
        tutorial3d.classList.add('visible');
      } else {
        tutorial3d.classList.remove('visible');
      }
    }
  }

  /**
   * Handle hand tracking results
   */
  onHandResults(results) {
    const { landmarks, smoothedCursor, timestamp } = results;
    
    // Update hand detection status
    this.state.setHandDetected(landmarks !== null);
    this.state.setLandmarks(landmarks);
    
    if (!landmarks) {
      // No hand detected - cancel current stroke if any
      if (this.state.isDrawing) {
        this.state.cancelStroke();
      }
      this.state.setPenState(false);
      return;
    }
    
    // Detect gesture
    const gestureResult = this.gestureDetector.detect(
      landmarks,
      SETTINGS.canvas.width,
      SETTINGS.canvas.height
    );
    
    // Update state with gesture info
    this.state.setGesture(getGestureName(gestureResult.gesture));
    this.state.setPenState(gestureResult.state === GestureState.PEN_DOWN);
    
    // Get cursor position with snapping
    let cursorPosition = { ...smoothedCursor };
    const anchor = this.state.getStrokeAnchor();
    
    // Apply snapping
    const snapped = this.snapSystem.snap(cursorPosition, anchor);
    cursorPosition = { x: snapped.x, y: snapped.y };
    this.state.setSnapInfo(snapped.snapInfo);
    
    // Update ghost preview for angle snapping
    if (this.state.isDrawing && anchor) {
      const angleLine = this.snapSystem.getAnglePreviewLine(anchor, cursorPosition);
      this.state.setGhostPreview(angleLine ? { angleLine } : null);
    } else {
      this.state.setGhostPreview(null);
    }
    
    // Update cursor in state
    this.state.setCursor(cursorPosition, this.handTracker.getTrail());
    
    // Handle drawing state transitions
    this.handleDrawingLogic(cursorPosition);
  }

  /**
   * Handle gesture state changes
   */
  onGestureStateChange(change) {
    // This is called when pen goes up or down
    // console.log('Gesture state change:', change);
  }

  /**
   * Handle drawing logic based on pen state
   */
  handleDrawingLogic(cursorPosition) {
    // Pen just went down - start new stroke
    if (this.state.didPenGoDown()) {
      this.state.startStroke(cursorPosition);
    }
    
    // Currently drawing - add points
    if (this.state.isDrawing && this.state.isPenDown) {
      this.state.addStrokePoint(cursorPosition);
      
      // Update preview shape periodically
      if (this.state.currentStroke.length >= SETTINGS.shapeRecognition.minPoints) {
        const preview = this.shapeRecognizer.recognize(this.state.currentStroke);
        this.state.setPreviewShape(preview);
      }
    }
    
    // Pen just went up - finalize stroke
    if (this.state.didPenGoUp() && this.state.isDrawing) {
      this.finalizeStroke();
    }
  }

  /**
   * Finalize the current stroke and recognize shape
   */
  finalizeStroke() {
    // Get stroke points
    const strokePoints = this.state.endStroke();
    
    // Check if stroke is valid
    if (strokePoints.length < SETTINGS.shapeRecognition.minPoints) {
      console.log('Stroke too short, ignoring');
      return;
    }
    
    // Calculate stroke length
    let totalLength = 0;
    for (let i = 1; i < strokePoints.length; i++) {
      const dx = strokePoints[i].x - strokePoints[i-1].x;
      const dy = strokePoints[i].y - strokePoints[i-1].y;
      totalLength += Math.sqrt(dx * dx + dy * dy);
    }
    
    if (totalLength < SETTINGS.drawing.minStrokeLength) {
      console.log('Stroke too short, ignoring');
      return;
    }
    
    // Recognize the shape
    const shape = this.shapeRecognizer.recognize(strokePoints);
    
    // Add shape to state
    this.state.addShape(shape);
    
    // Add endpoints for snapping
    this.snapSystem.addShapeEndpoints(shape);
    
    console.log(`✨ Recognized: ${this.shapeRecognizer.describeShape(shape)}`);
  }

  /**
   * Main render loop (2D mode only)
   */
  mainLoop() {
    if (!this.isRunning || this.currentMode !== AppMode.MODE_2D) return;
    
    // Update FPS counter
    if (this.state) {
      this.state.updateFPS();
      
      // Render the scene
      const renderState = this.state.getRenderState();
      this.renderer.render(renderState);
      
      // Draw HUD
      const hudData = this.state.getHUDData(this.snapSystem);
      this.renderer.drawHUD(hudData);
      
      // Draw help if enabled
      if (this.showHelp) {
        this.renderer.drawHelp();
      }
    }
    
    // Schedule next frame
    this.animationFrameId = requestAnimationFrame(this.mainLoop);
  }

  /**
   * Handle keyboard input
   */
  handleKeyboard(event) {
    // Ignore if user is typing in an input field
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
      return;
    }
    
    switch (event.key.toLowerCase()) {
      case 'z':
        // Undo
        if (this.state.undo()) {
          // Rebuild endpoints after undo
          this.snapSystem.rebuildEndpoints(this.state.getShapes());
          console.log('↩️ Undo');
        }
        break;
      
      case 'c':
        // Clear all
        this.state.clearAll();
        this.snapSystem.clearEndpoints();
        console.log('🧹 Cleared all shapes');
        break;
      
      case 'g':
        // Toggle grid snap
        const gridEnabled = this.snapSystem.toggleGrid();
        console.log(`📐 Grid snap: ${gridEnabled ? 'ON' : 'OFF'}`);
        break;
      
      case 'a':
        // Toggle angle snap
        const angleEnabled = this.snapSystem.toggleAngle();
        console.log(`📐 Angle snap: ${angleEnabled ? 'ON' : 'OFF'}`);
        break;
      
      case 'e':
        // Toggle endpoint snap
        const endpointEnabled = this.snapSystem.toggleEndpoint();
        console.log(`📐 Endpoint snap: ${endpointEnabled ? 'ON' : 'OFF'}`);
        break;
      
      case 's':
        // Save to JSON
        this.saveToJSON();
        break;
      
      case 'h':
        // Toggle help display
        this.showHelp = !this.showHelp;
        break;
      
      case 'v':
        // Toggle video background
        const videoEnabled = this.renderer.toggleVideo();
        console.log(`📹 Video background: ${videoEnabled ? 'ON' : 'OFF'}`);
        break;
      
      case 'l':
        // Toggle hand landmarks
        const landmarksEnabled = this.renderer.toggleHandLandmarks();
        console.log(`✋ Hand landmarks: ${landmarksEnabled ? 'ON' : 'OFF'}`);
        break;
      
      case '[':
        // Decrease video opacity
        this.renderer.setVideoOpacity(this.renderer.videoOpacity - 0.1);
        console.log(`📹 Video opacity: ${Math.round(this.renderer.videoOpacity * 100)}%`);
        break;
      
      case ']':
        // Increase video opacity
        this.renderer.setVideoOpacity(this.renderer.videoOpacity + 0.1);
        console.log(`📹 Video opacity: ${Math.round(this.renderer.videoOpacity * 100)}%`);
        break;
      
      case 'escape':
        // Cancel current stroke
        if (this.state && this.state.isDrawing) {
          this.state.cancelStroke();
          console.log('❌ Stroke cancelled');
        }
        break;
      
      case 'm':
        // Switch mode
        const newMode = this.currentMode === AppMode.MODE_2D ? AppMode.MODE_3D : AppMode.MODE_2D;
        this.switchMode(newMode);
        break;
    }
  }

  /**
   * Save current shapes to JSON file
   */
  saveToJSON() {
    const json = this.state.exportToJSON();
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `airdraw-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    console.log('💾 Saved to JSON');
  }

  /**
   * Show error message on screen
   */
  showError(message) {
    const ctx = this.renderer.ctx;
    ctx.fillStyle = 'rgba(255, 0, 0, 0.8)';
    ctx.fillRect(0, 0, this.canvasElement.width, this.canvasElement.height);
    ctx.fillStyle = '#ffffff';
    ctx.font = '24px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(message, this.canvasElement.width / 2, this.canvasElement.height / 2);
  }

  /**
   * Stop the application
   */
  stop() {
    this.isRunning = false;
    
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
    
    if (this.handTracker) {
      this.handTracker.stop();
    }
    
    if (this.app3D) {
      this.app3D.stop();
    }
    
    console.log('👋 AirDraw Blueprint - Stopped');
  }

  /**
   * Full cleanup
   */
  destroy() {
    this.stop();
    document.removeEventListener('keydown', this.handleKeyboard);
  }
}

// Auto-start when DOM is ready
let app = null;

async function startApp() {
  app = new AirDrawApp();
  
  try {
    await app.initialize();
  } catch (error) {
    console.error('Failed to start AirDraw:', error);
  }
}

// Expose for debugging
if (typeof window !== 'undefined') {
  window.AirDrawApp = AirDrawApp;
  window.getApp = () => app;
  
  // Auto-start
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startApp);
  } else {
    startApp();
  }
}
