/**
 * Blueprint Renderer Module
 * Renders the CAD-style blueprint canvas with grid, shapes, and visual effects
 */

import { SETTINGS } from '../settings.js';
import { ShapeType } from './shapeRecognizer.js';
import { distance, toRadians } from '../utils/math.js';

export class BlueprintRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    
    // Set canvas size
    this.width = SETTINGS.canvas.width;
    this.height = SETTINGS.canvas.height;
    canvas.width = this.width;
    canvas.height = this.height;
    
    // Style settings
    this.style = SETTINGS.blueprint;
    this.units = SETTINGS.units;
    
    // Video element reference (set later)
    this.videoElement = null;
    this.showVideo = true;  // Toggle for video background
    this.videoOpacity = 0.4; // Video transparency (0-1)
    
    // Hand landmark visualization
    this.showHandLandmarks = true;  // Show hand skeleton
    
    // Pre-render the grid to an offscreen canvas for performance
    this.gridCanvas = document.createElement('canvas');
    this.gridCanvas.width = this.width;
    this.gridCanvas.height = this.height;
    this.prerenderGrid();
  }

  /**
   * Set the video element for background rendering
   */
  setVideoElement(video) {
    this.videoElement = video;
  }

  /**
   * Toggle video background visibility
   */
  toggleVideo() {
    this.showVideo = !this.showVideo;
    return this.showVideo;
  }

  /**
   * Set video opacity (0-1)
   */
  setVideoOpacity(opacity) {
    this.videoOpacity = Math.max(0, Math.min(1, opacity));
  }

  /**
   * Toggle hand landmark visualization
   */
  toggleHandLandmarks() {
    this.showHandLandmarks = !this.showHandLandmarks;
    return this.showHandLandmarks;
  }

  /**
   * Draw hand landmarks and skeleton
   */
  drawHandLandmarks(landmarks, canvasWidth, canvasHeight) {
    const ctx = this.ctx;
    const w = canvasWidth || this.width;
    const h = canvasHeight || this.height;
    
    // Hand connections (bone structure)
    const connections = [
      // Thumb
      [0, 1], [1, 2], [2, 3], [3, 4],
      // Index
      [0, 5], [5, 6], [6, 7], [7, 8],
      // Middle
      [0, 9], [9, 10], [10, 11], [11, 12],
      // Ring
      [0, 13], [13, 14], [14, 15], [15, 16],
      // Pinky
      [0, 17], [17, 18], [18, 19], [19, 20],
      // Palm
      [5, 9], [9, 13], [13, 17],
    ];
    
    // Convert landmarks to canvas coordinates (mirrored)
    const points = landmarks.map(lm => ({
      x: (1 - lm.x) * w,
      y: lm.y * h,
    }));
    
    // Draw connections (bones)
    ctx.strokeStyle = 'rgba(0, 255, 136, 0.6)';
    ctx.lineWidth = 2;
    
    for (const [i, j] of connections) {
      ctx.beginPath();
      ctx.moveTo(points[i].x, points[i].y);
      ctx.lineTo(points[j].x, points[j].y);
      ctx.stroke();
    }
    
    // Draw landmark points
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      
      // Different colors for fingertips
      if ([4, 8, 12, 16, 20].includes(i)) {
        // Fingertips - larger and brighter
        ctx.fillStyle = '#00ff88';
        ctx.beginPath();
        ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
        ctx.fill();
        
        // Index tip gets special highlight
        if (i === 8) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(p.x, p.y, 10, 0, Math.PI * 2);
          ctx.stroke();
        }
      } else {
        // Other joints
        ctx.fillStyle = 'rgba(0, 255, 136, 0.8)';
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    
    // Label the index fingertip
    ctx.fillStyle = '#ffffff';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('INDEX', points[8].x, points[8].y - 15);
  }

  /**
   * Pre-render the grid to an offscreen canvas
   */
  prerenderGrid() {
    const ctx = this.gridCanvas.getContext('2d');
    const gridSize = SETTINGS.snap.gridSize;
    const majorInterval = this.style.gridMajorInterval;
    
    // Fill background
    ctx.fillStyle = this.style.backgroundColor;
    ctx.fillRect(0, 0, this.width, this.height);
    
    // Draw minor grid lines
    ctx.strokeStyle = this.style.gridColor;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    
    // Vertical lines
    for (let x = 0; x <= this.width; x += gridSize) {
      if (x % (gridSize * majorInterval) !== 0) {
        ctx.moveTo(x, 0);
        ctx.lineTo(x, this.height);
      }
    }
    
    // Horizontal lines
    for (let y = 0; y <= this.height; y += gridSize) {
      if (y % (gridSize * majorInterval) !== 0) {
        ctx.moveTo(0, y);
        ctx.lineTo(this.width, y);
      }
    }
    ctx.stroke();
    
    // Draw major grid lines
    ctx.strokeStyle = this.style.gridMajorColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    
    for (let x = 0; x <= this.width; x += gridSize * majorInterval) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, this.height);
    }
    
    for (let y = 0; y <= this.height; y += gridSize * majorInterval) {
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
    }
    ctx.stroke();
    
    // Draw center axis lines
    ctx.strokeStyle = this.style.axisColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    
    // Horizontal center axis
    const centerY = this.height / 2;
    ctx.moveTo(0, centerY);
    ctx.lineTo(this.width, centerY);
    
    // Vertical center axis
    const centerX = this.width / 2;
    ctx.moveTo(centerX, 0);
    ctx.lineTo(centerX, this.height);
    
    ctx.stroke();
  }

  /**
   * Clear and redraw the canvas
   */
  clear() {
    const ctx = this.ctx;
    
    // Fill with background color first
    ctx.fillStyle = this.style.backgroundColor;
    ctx.fillRect(0, 0, this.width, this.height);
    
    // Draw video background if enabled
    if (this.showVideo && this.videoElement && this.videoElement.readyState >= 2) {
      ctx.save();
      ctx.globalAlpha = this.videoOpacity;
      
      // Mirror the video horizontally for selfie view
      ctx.translate(this.width, 0);
      ctx.scale(-1, 1);
      
      // Draw video scaled to canvas
      ctx.drawImage(this.videoElement, 0, 0, this.width, this.height);
      
      ctx.restore();
    }
    
    // Draw pre-rendered grid on top with transparency
    ctx.globalAlpha = this.showVideo ? 0.7 : 1.0;
    ctx.drawImage(this.gridCanvas, 0, 0);
    ctx.globalAlpha = 1.0;
  }

  /**
   * Render a complete frame
   * @param {Object} state - Current editor state containing shapes, cursor, etc.
   */
  render(state) {
    // Clear and draw grid
    this.clear();
    
    // Draw committed shapes
    for (const shape of state.shapes) {
      this.drawShape(shape, false);
    }
    
    // Draw current stroke preview (if drawing)
    if (state.isDrawing && state.currentStroke.length > 0) {
      this.drawStrokePreview(state.currentStroke, state.previewShape);
    }
    
    // Draw snap indicators
    if (state.snapInfo) {
      this.drawSnapIndicators(state.snapInfo, state.cursor);
    }
    
    // Draw ghost preview for snapping
    if (state.ghostPreview) {
      this.drawGhostPreview(state.ghostPreview);
    }
    
    // Draw hand landmarks if available
    if (state.handDetected && state.landmarks && this.showHandLandmarks) {
      this.drawHandLandmarks(state.landmarks, state.canvasWidth, state.canvasHeight);
    }
    
    // Draw cursor and trail
    if (state.handDetected) {
      this.drawCursor(state.cursor, state.cursorTrail, state.isPenDown);
    }
    
    // Draw dimensions for all shapes
    for (const shape of state.shapes) {
      this.drawDimensions(shape);
    }
    
    // Draw preview dimensions
    if (state.previewShape) {
      this.drawDimensions(state.previewShape, true);
    }
  }

  /**
   * Draw a committed shape
   */
  drawShape(shape, isPreview = false) {
    const ctx = this.ctx;
    
    // Set style
    ctx.strokeStyle = isPreview ? this.style.previewColor : this.style.strokeColor;
    ctx.lineWidth = this.style.strokeWidth;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    if (isPreview) {
      ctx.setLineDash(this.style.previewDash);
    } else {
      ctx.setLineDash([]);
    }
    
    // Apply glow effect for committed shapes
    if (!isPreview) {
      ctx.shadowColor = this.style.strokeGlow;
      ctx.shadowBlur = this.style.strokeGlowBlur;
    }
    
    ctx.beginPath();
    
    switch (shape.type) {
      case ShapeType.LINE:
        ctx.moveTo(shape.start.x, shape.start.y);
        ctx.lineTo(shape.end.x, shape.end.y);
        break;
      
      case ShapeType.RECTANGLE:
        ctx.moveTo(shape.corners[0].x, shape.corners[0].y);
        for (let i = 1; i < shape.corners.length; i++) {
          ctx.lineTo(shape.corners[i].x, shape.corners[i].y);
        }
        ctx.closePath();
        break;
      
      case ShapeType.CIRCLE:
        ctx.arc(shape.center.x, shape.center.y, shape.radius, 0, Math.PI * 2);
        break;
      
      case ShapeType.ARC:
        const startRad = toRadians(shape.startAngle);
        const endRad = toRadians(shape.endAngle);
        ctx.arc(shape.center.x, shape.center.y, shape.radius, startRad, endRad);
        break;
      
      case ShapeType.POLYLINE:
        if (shape.points.length > 0) {
          ctx.moveTo(shape.points[0].x, shape.points[0].y);
          for (let i = 1; i < shape.points.length; i++) {
            ctx.lineTo(shape.points[i].x, shape.points[i].y);
          }
        }
        break;
    }
    
    ctx.stroke();
    
    // Reset shadow
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.setLineDash([]);
  }

  /**
   * Draw stroke preview during drawing
   */
  drawStrokePreview(strokePoints, previewShape) {
    const ctx = this.ctx;
    
    if (strokePoints.length < 2) return;
    
    // Draw raw stroke with dotted line
    ctx.strokeStyle = this.style.previewColor;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    
    ctx.beginPath();
    ctx.moveTo(strokePoints[0].x, strokePoints[0].y);
    for (let i = 1; i < strokePoints.length; i++) {
      ctx.lineTo(strokePoints[i].x, strokePoints[i].y);
    }
    ctx.stroke();
    
    // Draw recognized shape preview if available
    if (previewShape) {
      this.drawShape(previewShape, true);
    }
    
    ctx.setLineDash([]);
  }

  /**
   * Draw snap indicators (grid dots, angle lines, endpoint markers)
   */
  drawSnapIndicators(snapInfo, cursor) {
    const ctx = this.ctx;
    
    // Grid snap indicator
    if (snapInfo.gridSnapped && snapInfo.snappedPoint) {
      ctx.fillStyle = 'rgba(255, 255, 0, 0.8)';
      ctx.beginPath();
      ctx.arc(snapInfo.snappedPoint.x, snapInfo.snappedPoint.y, 4, 0, Math.PI * 2);
      ctx.fill();
    }
    
    // Endpoint snap indicator
    if (snapInfo.endpointSnapped && snapInfo.nearbyEndpoint) {
      ctx.strokeStyle = 'rgba(255, 100, 100, 0.8)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(snapInfo.nearbyEndpoint.x, snapInfo.nearbyEndpoint.y, 8, 0, Math.PI * 2);
      ctx.stroke();
      
      // Draw connecting line
      ctx.strokeStyle = 'rgba(255, 100, 100, 0.4)';
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(cursor.x, cursor.y);
      ctx.lineTo(snapInfo.nearbyEndpoint.x, snapInfo.nearbyEndpoint.y);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    
    // Angle snap indicator
    if (snapInfo.angleSnapped && snapInfo.snappedAngle !== null) {
      ctx.fillStyle = 'rgba(100, 255, 100, 0.8)';
      ctx.font = '10px monospace';
      ctx.fillText(`${snapInfo.snappedAngle}°`, cursor.x + 15, cursor.y - 15);
    }
  }

  /**
   * Draw ghost preview for snapped shapes
   */
  drawGhostPreview(ghostPreview) {
    const ctx = this.ctx;
    
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    
    // Draw construction lines for angle snapping
    if (ghostPreview.angleLine) {
      ctx.beginPath();
      ctx.moveTo(ghostPreview.angleLine.start.x, ghostPreview.angleLine.start.y);
      ctx.lineTo(ghostPreview.angleLine.end.x, ghostPreview.angleLine.end.y);
      ctx.stroke();
    }
    
    ctx.setLineDash([]);
  }

  /**
   * Draw cursor and trail
   */
  drawCursor(position, trail, isPenDown) {
    const ctx = this.ctx;
    
    // Draw trail
    if (trail && trail.length > 1) {
      ctx.beginPath();
      ctx.moveTo(trail[0].x, trail[0].y);
      
      for (let i = 1; i < trail.length; i++) {
        const alpha = i / trail.length;
        ctx.strokeStyle = `rgba(0, 255, 136, ${alpha * 0.5})`;
        ctx.lineWidth = alpha * 3;
        ctx.lineTo(trail[i].x, trail[i].y);
      }
      ctx.stroke();
    }
    
    // Draw cursor circle
    const cursorRadius = this.style.cursorRadius;
    
    // Outer glow
    ctx.beginPath();
    ctx.arc(position.x, position.y, cursorRadius + 4, 0, Math.PI * 2);
    ctx.strokeStyle = isPenDown ? 'rgba(255, 100, 100, 0.5)' : 'rgba(0, 255, 136, 0.3)';
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // Inner cursor
    ctx.beginPath();
    ctx.arc(position.x, position.y, cursorRadius, 0, Math.PI * 2);
    ctx.fillStyle = isPenDown ? 'rgba(255, 100, 100, 0.8)' : this.style.cursorColor;
    ctx.fill();
    
    // Center dot
    ctx.beginPath();
    ctx.arc(position.x, position.y, 2, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fill();
  }

  /**
   * Draw dimensions for a shape
   */
  drawDimensions(shape, isPreview = false) {
    const ctx = this.ctx;
    const ppu = this.units.pixelsPerUnit;
    const decimals = this.units.displayDecimals;
    const label = this.units.unitLabel;
    const offset = this.style.dimensionOffset;
    
    ctx.fillStyle = isPreview ? 'rgba(255, 255, 255, 0.6)' : this.style.dimensionColor;
    ctx.font = `${this.style.dimensionFontSize}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    
    switch (shape.type) {
      case ShapeType.LINE:
        this.drawLineDimension(shape, ppu, decimals, label, offset);
        break;
      
      case ShapeType.RECTANGLE:
        this.drawRectDimensions(shape, ppu, decimals, label, offset);
        break;
      
      case ShapeType.CIRCLE:
        this.drawCircleDimension(shape, ppu, decimals, label, offset);
        break;
      
      case ShapeType.ARC:
        this.drawArcDimension(shape, ppu, decimals, label, offset);
        break;
      
      case ShapeType.POLYLINE:
        // Just show total length near first point
        if (shape.points.length > 0) {
          const totalLen = (shape.totalLength / ppu).toFixed(decimals);
          ctx.fillText(`${totalLen}${label}`, shape.points[0].x, shape.points[0].y - offset);
        }
        break;
    }
  }

  /**
   * Draw dimension for a line
   */
  drawLineDimension(shape, ppu, decimals, label, offset) {
    const ctx = this.ctx;
    const midX = (shape.start.x + shape.end.x) / 2;
    const midY = (shape.start.y + shape.end.y) / 2;
    
    // Calculate perpendicular offset direction
    const dx = shape.end.x - shape.start.x;
    const dy = shape.end.y - shape.start.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    const nx = -dy / len;  // Normal x
    const ny = dx / len;   // Normal y
    
    const dimX = midX + nx * offset;
    const dimY = midY + ny * offset;
    
    const length = (shape.length / ppu).toFixed(decimals);
    
    // Draw dimension line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(shape.start.x + nx * 5, shape.start.y + ny * 5);
    ctx.lineTo(shape.end.x + nx * 5, shape.end.y + ny * 5);
    ctx.stroke();
    ctx.setLineDash([]);
    
    // Draw text
    ctx.fillText(`${length}${label}`, dimX, dimY);
  }

  /**
   * Draw dimensions for a rectangle
   */
  drawRectDimensions(shape, ppu, decimals, label, offset) {
    const ctx = this.ctx;
    
    const width = (shape.width / ppu).toFixed(decimals);
    const height = (shape.height / ppu).toFixed(decimals);
    
    // Width dimension (top edge)
    const topMidX = (shape.corners[0].x + shape.corners[1].x) / 2;
    const topMidY = Math.min(shape.corners[0].y, shape.corners[1].y) - offset;
    ctx.fillText(`${width}${label}`, topMidX, topMidY);
    
    // Height dimension (right edge)
    const rightMidX = Math.max(shape.corners[1].x, shape.corners[2].x) + offset;
    const rightMidY = (shape.corners[1].y + shape.corners[2].y) / 2;
    ctx.save();
    ctx.translate(rightMidX, rightMidY);
    ctx.rotate(Math.PI / 2);
    ctx.fillText(`${height}${label}`, 0, 0);
    ctx.restore();
  }

  /**
   * Draw dimension for a circle
   */
  drawCircleDimension(shape, ppu, decimals, label, offset) {
    const ctx = this.ctx;
    
    const radius = (shape.radius / ppu).toFixed(decimals);
    const diameter = (shape.diameter / ppu).toFixed(decimals);
    
    // Draw radius line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(shape.center.x, shape.center.y);
    ctx.lineTo(shape.center.x + shape.radius, shape.center.y);
    ctx.stroke();
    ctx.setLineDash([]);
    
    // Radius label
    ctx.fillText(`r=${radius}${label}`, shape.center.x + shape.radius / 2, shape.center.y - offset);
    
    // Diameter label (below center)
    ctx.fillText(`ø${diameter}${label}`, shape.center.x, shape.center.y + shape.radius + offset);
  }

  /**
   * Draw dimension for an arc
   */
  drawArcDimension(shape, ppu, decimals, label, offset) {
    const ctx = this.ctx;
    
    const radius = (shape.radius / ppu).toFixed(decimals);
    const arcAngle = shape.arcAngle.toFixed(0);
    
    // Draw at arc midpoint
    const midAngle = (shape.startAngle + shape.endAngle) / 2;
    const midRad = toRadians(midAngle);
    const labelX = shape.center.x + (shape.radius + offset) * Math.cos(midRad);
    const labelY = shape.center.y + (shape.radius + offset) * Math.sin(midRad);
    
    ctx.fillText(`r=${radius}${label}, ${arcAngle}°`, labelX, labelY);
  }

  /**
   * Draw the HUD (heads-up display)
   */
  drawHUD(hudData) {
    const ctx = this.ctx;
    const padding = 15;
    let y = padding;
    
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    ctx.fillRect(5, 5, 200, 130);
    
    ctx.fillStyle = '#ffffff';
    ctx.font = '12px monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    
    // Mode
    const modeColor = hudData.mode === 'DRAW' ? '#ff6464' : '#64ff64';
    ctx.fillStyle = modeColor;
    ctx.fillText(`Mode: ${hudData.mode}`, padding, y);
    y += 18;
    
    // Gesture
    ctx.fillStyle = '#ffffff';
    ctx.fillText(`Gesture: ${hudData.gesture}`, padding, y);
    y += 18;
    
    // FPS
    const fpsColor = hudData.fps >= 25 ? '#64ff64' : (hudData.fps >= 15 ? '#ffff64' : '#ff6464');
    ctx.fillStyle = fpsColor;
    ctx.fillText(`FPS: ${hudData.fps}`, padding, y);
    y += 18;
    
    // Shape count
    ctx.fillStyle = '#ffffff';
    ctx.fillText(`Shapes: ${hudData.shapeCount}`, padding, y);
    y += 18;
    
    // Snap status
    ctx.fillStyle = '#aaaaaa';
    const snapStatus = [
      hudData.snapStatus.grid ? 'Grid' : '',
      hudData.snapStatus.angle ? 'Angle' : '',
      hudData.snapStatus.endpoint ? 'Endpoint' : '',
    ].filter(s => s).join(', ') || 'None';
    ctx.fillText(`Snap: ${snapStatus}`, padding, y);
    y += 18;
    
    // Hand detected
    ctx.fillStyle = hudData.handDetected ? '#64ff64' : '#ff6464';
    ctx.fillText(`Hand: ${hudData.handDetected ? 'Detected' : 'Not Found'}`, padding, y);
  }

  /**
   * Draw keyboard shortcuts help
   */
  drawHelp() {
    const ctx = this.ctx;
    const x = this.width - 200;
    const y = 5;
    
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    ctx.fillRect(x - 5, y, 200, 195);
    
    ctx.fillStyle = '#aaaaaa';
    ctx.font = '11px monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    
    const shortcuts = [
      'T - Show Tutorial',
      'Z - Undo',
      'C - Clear All',
      'G - Toggle Grid Snap',
      'A - Toggle Angle Snap',
      'E - Toggle Endpoint Snap',
      'V - Toggle Video',
      'L - Toggle Hand Skeleton',
      '[ ] - Video Opacity +/-',
      'H - Toggle This Help',
    ];
    
    let sy = y + 10;
    for (const shortcut of shortcuts) {
      ctx.fillText(shortcut, x, sy);
      sy += 15;
    }
    
    // Show video status
    sy += 5;
    ctx.fillStyle = this.showVideo ? '#64ff64' : '#ff6464';
    ctx.fillText(`Video: ${this.showVideo ? 'ON' : 'OFF'} (${Math.round(this.videoOpacity * 100)}%)`, x, sy);
  }

  /**
   * Resize the canvas
   */
  resize(width, height) {
    this.width = width;
    this.height = height;
    this.canvas.width = width;
    this.canvas.height = height;
    
    this.gridCanvas.width = width;
    this.gridCanvas.height = height;
    this.prerenderGrid();
  }
}
