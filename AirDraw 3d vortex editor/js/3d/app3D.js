/**
 * 3D Application Module
 * Handles 3D cube interaction with hand gestures
 */

import { SETTINGS } from '../settings.js';
import { Scene3D } from './scene3D.js';
import { CubeManager } from './cubeManager.js';
import { HandTracker } from '../tracking/handTracker.js';
import { GestureDetector, InteractionMode, getGestureName, getInteractionModeName } from '../tracking/gestureDetector.js';

export class App3D {
  constructor(container) {
    this.container = container;
    
    // Core modules
    this.scene3D = null;
    this.cubeManager = null;
    this.handTracker = null;
    this.gestureDetector = null;
    
    // State
    this.isRunning = false;
    this.mode = '3d';  // '3d' or '2d'
    
    // Interaction state
    this.currentInteraction = InteractionMode.NONE;
    this.previousInteraction = InteractionMode.NONE;
    this.isDragging = false;
    this.isResizing = false;
    this.deleteHoldTime = 0;
    this.deleteThreshold = 500;  // ms to hold for delete
    
    // Cursor tracking
    this.cursor = { x: 0, y: 0 };
    this.cursorTrail = [];
    
    // FPS tracking
    this.fps = 0;
    this.frameCount = 0;
    this.lastFPSUpdate = performance.now();
    
    // Video element reference
    this.videoElement = null;
    
    // Animation frame ID
    this.animationFrameId = null;
    
    // UI elements
    this.hudCanvas = null;
    this.hudCtx = null;
    
    // Gesture info for display
    this.gestureInfo = {
      gesture: 'None',
      mode: 'HOVER',
      pinchScale: 1.0,
    };
    
    // Bind methods
    this.mainLoop = this.mainLoop.bind(this);
    this.handleKeyboard = this.handleKeyboard.bind(this);
  }

  /**
   * Initialize the 3D application
   */
  async initialize(videoElement) {
    console.log('🎮 AirDraw 3D Mode - Initializing...');
    
    this.videoElement = videoElement;
    
    // Initialize 3D scene
    this.scene3D = new Scene3D(this.container);
    
    // Initialize cube manager
    this.cubeManager = new CubeManager(this.scene3D);
    
    // Initialize gesture detector
    this.gestureDetector = new GestureDetector();
    
    // Initialize hand tracker
    this.handTracker = new HandTracker();
    this.handTracker.onResults = (results) => this.onHandResults(results);
    
    // Create HUD canvas for overlays
    this.createHUDCanvas();
    
    // Set up keyboard controls
    document.addEventListener('keydown', this.handleKeyboard);
    
    // Initialize hand tracking
    try {
      await this.handTracker.initialize(videoElement);
      console.log('✅ Hand tracking initialized for 3D mode');
    } catch (error) {
      console.error('❌ Failed to initialize hand tracking:', error);
      throw error;
    }
    
    // Create some initial cubes for demonstration
    this.createDemoCubes();
    
    // Start main loop
    this.isRunning = true;
    this.mainLoop();
    
    console.log('✅ AirDraw 3D Mode - Ready!');
  }

  /**
   * Create HUD canvas overlay
   */
  createHUDCanvas() {
    this.hudCanvas = document.createElement('canvas');
    this.hudCanvas.id = 'hud-canvas';
    this.hudCanvas.width = SETTINGS.canvas.width;
    this.hudCanvas.height = SETTINGS.canvas.height;
    this.hudCanvas.style.position = 'absolute';
    this.hudCanvas.style.top = '0';
    this.hudCanvas.style.left = '0';
    this.hudCanvas.style.pointerEvents = 'none';
    this.container.appendChild(this.hudCanvas);
    this.hudCtx = this.hudCanvas.getContext('2d');
  }

  /**
   * Create demo cubes
   */
  createDemoCubes() {
    // Create a few starter cubes
    this.cubeManager.createCube({ x: 0, y: 0, z: 0 }, 1);
    this.cubeManager.createCube({ x: 2, y: 0, z: 0 }, 1);
    this.cubeManager.createCube({ x: -2, y: 0, z: 0 }, 1);
  }

  /**
   * Handle hand tracking results
   */
  onHandResults(results) {
    const { landmarks, smoothedCursor } = results;
    
    // Update cursor
    this.cursor = { ...smoothedCursor };
    this.cursorTrail = this.handTracker.getTrail();
    
    if (!landmarks) {
      this.gestureInfo.gesture = 'None';
      this.gestureInfo.mode = 'NONE';
      this.endInteractions();
      return;
    }
    
    // Detect gesture
    const gestureResult = this.gestureDetector.detect(
      landmarks,
      SETTINGS.canvas.width,
      SETTINGS.canvas.height
    );
    
    // Update gesture info
    this.gestureInfo.gesture = getGestureName(gestureResult.gesture);
    this.gestureInfo.mode = getInteractionModeName(gestureResult.interactionMode);
    this.gestureInfo.pinchScale = gestureResult.pinchScaleFactor;
    
    // Update 3D scene pointer for raycasting
    this.scene3D.updatePointer(this.cursor.x, this.cursor.y);
    
    // Handle 3D interactions
    this.handle3DInteraction(gestureResult);
  }

  /**
   * Handle 3D cube interactions based on gesture
   */
  handle3DInteraction(gestureResult) {
    const { interactionMode, pinchScaleFactor, isThumbsDown } = gestureResult;
    
    // Get cube under cursor
    const cubeUnderCursor = this.cubeManager.getCubeAtCursor();
    
    // Update hover state
    if (cubeUnderCursor && interactionMode === InteractionMode.HOVER) {
      this.cubeManager.setHoveredCube(cubeUnderCursor);
    } else if (!this.isDragging && !this.isResizing) {
      this.cubeManager.setHoveredCube(null);
    }
    
    // Handle interaction mode changes
    switch (interactionMode) {
      case InteractionMode.HOVER:
        this.handleHoverMode(cubeUnderCursor);
        break;
        
      case InteractionMode.DRAG:
        this.handleDragMode(cubeUnderCursor);
        break;
        
      case InteractionMode.RESIZE:
        this.handleResizeMode(pinchScaleFactor);
        break;
        
      case InteractionMode.DELETE:
        this.handleDeleteMode(cubeUnderCursor);
        break;
        
      default:
        this.handleIdleMode();
        break;
    }
    
    this.previousInteraction = interactionMode;
  }

  /**
   * Handle hover/selection mode
   */
  handleHoverMode(cubeUnderCursor) {
    // End any ongoing drag/resize
    if (this.isDragging) {
      this.cubeManager.endDrag();
      this.isDragging = false;
    }
    this.isResizing = false;
    this.deleteHoldTime = 0;
    
    // Select cube on point
    if (cubeUnderCursor && this.previousInteraction !== InteractionMode.HOVER) {
      this.cubeManager.selectCube(cubeUnderCursor);
    }
  }

  /**
   * Handle drag mode (fist gesture)
   */
  handleDragMode(cubeUnderCursor) {
    this.deleteHoldTime = 0;
    this.isResizing = false;
    
    // Start dragging if we have a selected cube or hovering over one
    if (!this.isDragging) {
      if (cubeUnderCursor) {
        this.cubeManager.selectCube(cubeUnderCursor);
      }
      if (this.cubeManager.selectedCube) {
        this.cubeManager.startDrag();
        this.isDragging = true;
      }
    }
    
    // Update drag position
    if (this.isDragging) {
      const groundPoint = this.scene3D.getGroundPoint();
      this.cubeManager.updateDrag(groundPoint);
    }
  }

  /**
   * Handle resize mode (pinch/spread)
   */
  handleResizeMode(pinchScaleFactor) {
    this.deleteHoldTime = 0;
    
    // End drag if we were dragging
    if (this.isDragging) {
      this.cubeManager.endDrag();
      this.isDragging = false;
    }
    
    this.isResizing = true;
    
    // Apply resize to selected cube
    if (this.cubeManager.selectedCube && Math.abs(pinchScaleFactor - 1.0) > 0.001) {
      this.cubeManager.resizeCube(pinchScaleFactor);
    }
  }

  /**
   * Handle delete mode (thumbs down)
   */
  handleDeleteMode(cubeUnderCursor) {
    // End other interactions
    if (this.isDragging) {
      this.cubeManager.endDrag();
      this.isDragging = false;
    }
    this.isResizing = false;
    
    // Show delete preview
    if (cubeUnderCursor) {
      this.cubeManager.previewDelete(cubeUnderCursor);
      
      // Track hold time for delete confirmation
      this.deleteHoldTime += 16;  // Approximate frame time
      
      if (this.deleteHoldTime >= this.deleteThreshold) {
        this.cubeManager.deleteCube(cubeUnderCursor);
        this.deleteHoldTime = 0;
        console.log('🗑️ Cube deleted');
      }
    } else {
      this.deleteHoldTime = 0;
    }
  }

  /**
   * Handle idle mode
   */
  handleIdleMode() {
    this.endInteractions();
  }

  /**
   * End all interactions
   */
  endInteractions() {
    if (this.isDragging) {
      this.cubeManager.endDrag();
      this.isDragging = false;
    }
    this.isResizing = false;
    this.deleteHoldTime = 0;
    this.cubeManager.cancelDeletePreview();
  }

  /**
   * Main render loop
   */
  mainLoop() {
    if (!this.isRunning) return;
    
    // Update FPS
    this.updateFPS();
    
    // Render 3D scene
    this.scene3D.render();
    
    // Render HUD overlay
    this.renderHUD();
    
    // Schedule next frame
    this.animationFrameId = requestAnimationFrame(this.mainLoop);
  }

  /**
   * Render HUD overlay
   */
  renderHUD() {
    const ctx = this.hudCtx;
    ctx.clearRect(0, 0, this.hudCanvas.width, this.hudCanvas.height);
    
    // Draw cursor
    this.drawCursor(ctx);
    
    // Draw HUD info
    this.drawHUDInfo(ctx);
    
    // Draw delete progress if in delete mode
    if (this.deleteHoldTime > 0) {
      this.drawDeleteProgress(ctx);
    }
  }

  /**
   * Draw cursor on HUD
   */
  drawCursor(ctx) {
    const { x, y } = this.cursor;
    
    // Draw trail
    if (this.cursorTrail.length > 1) {
      ctx.beginPath();
      ctx.moveTo(this.cursorTrail[0].x, this.cursorTrail[0].y);
      for (let i = 1; i < this.cursorTrail.length; i++) {
        const alpha = i / this.cursorTrail.length;
        ctx.strokeStyle = `rgba(0, 255, 136, ${alpha * 0.5})`;
        ctx.lineWidth = alpha * 3;
        ctx.lineTo(this.cursorTrail[i].x, this.cursorTrail[i].y);
      }
      ctx.stroke();
    }
    
    // Cursor color based on mode
    let cursorColor = '#00ff88';  // Default green
    if (this.isDragging) {
      cursorColor = '#ffaa00';  // Orange for drag
    } else if (this.isResizing) {
      cursorColor = '#00aaff';  // Blue for resize
    } else if (this.deleteHoldTime > 0) {
      cursorColor = '#ff4444';  // Red for delete
    }
    
    // Outer glow
    ctx.beginPath();
    ctx.arc(x, y, 12, 0, Math.PI * 2);
    ctx.strokeStyle = cursorColor.replace(')', ', 0.3)').replace('rgb', 'rgba');
    ctx.lineWidth = 3;
    ctx.stroke();
    
    // Inner cursor
    ctx.beginPath();
    ctx.arc(x, y, 8, 0, Math.PI * 2);
    ctx.fillStyle = cursorColor;
    ctx.fill();
    
    // Center dot
    ctx.beginPath();
    ctx.arc(x, y, 2, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fill();
  }

  /**
   * Draw HUD information
   */
  drawHUDInfo(ctx) {
    const padding = 15;
    let y = padding;
    
    // Background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(5, 5, 200, 150);
    
    ctx.font = '12px monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    
    // Mode
    ctx.fillStyle = '#00d4ff';
    ctx.fillText('🎮 3D CUBE MODE', padding, y);
    y += 20;
    
    // Gesture
    ctx.fillStyle = '#ffffff';
    ctx.fillText(`Gesture: ${this.gestureInfo.gesture}`, padding, y);
    y += 18;
    
    // Interaction mode
    const modeColor = {
      'HOVER': '#64ff64',
      'DRAG': '#ffaa00',
      'RESIZE': '#00aaff',
      'DELETE': '#ff4444',
      'NONE': '#888888',
    }[this.gestureInfo.mode] || '#ffffff';
    ctx.fillStyle = modeColor;
    ctx.fillText(`Mode: ${this.gestureInfo.mode}`, padding, y);
    y += 18;
    
    // FPS
    const fpsColor = this.fps >= 25 ? '#64ff64' : (this.fps >= 15 ? '#ffff64' : '#ff6464');
    ctx.fillStyle = fpsColor;
    ctx.fillText(`FPS: ${this.fps}`, padding, y);
    y += 18;
    
    // Cube count
    ctx.fillStyle = '#aaaaaa';
    ctx.fillText(`Cubes: ${this.cubeManager.getCubeCount()}`, padding, y);
    y += 18;
    
    // Selected cube
    if (this.cubeManager.selectedCube) {
      ctx.fillStyle = '#ff6464';
      ctx.fillText(`Selected: Cube ${this.cubeManager.selectedCube.id}`, padding, y);
    }
  }

  /**
   * Draw delete progress indicator
   */
  drawDeleteProgress(ctx) {
    const progress = this.deleteHoldTime / this.deleteThreshold;
    const x = this.cursor.x;
    const y = this.cursor.y;
    const radius = 25;
    
    // Background arc
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255, 0, 0, 0.3)';
    ctx.lineWidth = 4;
    ctx.stroke();
    
    // Progress arc
    ctx.beginPath();
    ctx.arc(x, y, radius, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
    ctx.strokeStyle = '#ff0000';
    ctx.lineWidth = 4;
    ctx.stroke();
    
    // Delete icon
    ctx.fillStyle = '#ff0000';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('🗑️', x, y - 35);
  }

  /**
   * Update FPS counter
   */
  updateFPS() {
    this.frameCount++;
    const now = performance.now();
    const elapsed = now - this.lastFPSUpdate;
    
    if (elapsed >= 500) {
      this.fps = Math.round((this.frameCount * 1000) / elapsed);
      this.frameCount = 0;
      this.lastFPSUpdate = now;
    }
  }

  /**
   * Handle keyboard input
   */
  handleKeyboard(event) {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
      return;
    }
    
    switch (event.key.toLowerCase()) {
      case 'n':
        // New cube at cursor
        const newCube = this.cubeManager.spawnCubeAtCursor();
        if (newCube) {
          console.log('➕ New cube created');
          this.cubeManager.selectCube(newCube);
        }
        break;
      
      case 'delete':
      case 'backspace':
        // Delete selected cube
        this.cubeManager.deleteSelectedCube();
        console.log('🗑️ Deleted selected cube');
        break;
      
      case 'z':
        // Undo
        if (this.cubeManager.undo()) {
          console.log('↩️ Undo');
        }
        break;
      
      case 'c':
        // Clear all
        this.cubeManager.clearAll();
        console.log('🧹 Cleared all cubes');
        break;
      
      case 'escape':
        // Deselect
        this.cubeManager.deselectCube();
        break;
      
      case '+':
      case '=':
        // Grow selected cube
        if (this.cubeManager.selectedCube) {
          this.cubeManager.resizeCube(1.2);
        }
        break;
      
      case '-':
      case '_':
        // Shrink selected cube
        if (this.cubeManager.selectedCube) {
          this.cubeManager.resizeCube(0.8);
        }
        break;
    }
  }

  /**
   * Stop the application
   */
  stop() {
    this.isRunning = false;
    
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    
    if (this.handTracker) {
      this.handTracker.stop();
    }
    
    if (this.scene3D) {
      this.scene3D.dispose();
    }
    
    document.removeEventListener('keydown', this.handleKeyboard);
    
    console.log('👋 AirDraw 3D Mode - Stopped');
  }
}
