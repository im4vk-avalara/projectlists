/**
 * Snap System Module
 * Provides grid snapping, angle snapping, and endpoint snapping
 */

import { SETTINGS } from '../settings.js';
import { 
  distance, 
  angle, 
  toDegrees, 
  toRadians,
  normalizeAngle,
  snapToGrid,
  snapPointToGrid,
  snapAngle as snapAngleUtil,
} from '../utils/math.js';

export class SnapSystem {
  constructor() {
    // Snap settings (can be toggled)
    this.gridEnabled = SETTINGS.snap.gridEnabled;
    this.angleSnapEnabled = SETTINGS.snap.angleSnapEnabled;
    this.endpointSnapEnabled = SETTINGS.snap.endpointSnapEnabled;
    
    // Reference points for snapping
    this.endpoints = [];  // Array of {x, y} from previous shapes
    
    // Last snap info for visual feedback
    this.lastSnapInfo = {
      gridSnapped: false,
      angleSnapped: false,
      endpointSnapped: false,
      snappedPoint: null,
      snappedAngle: null,
      nearbyEndpoint: null,
    };
  }

  /**
   * Apply all enabled snapping to a point
   * @param {Object} point - {x, y} point to snap
   * @param {Object} anchor - Optional anchor point for angle snapping
   * @returns {{x: number, y: number, snapInfo: Object}} Snapped point and info
   */
  snap(point, anchor = null) {
    let snapped = { ...point };
    
    // Reset snap info
    this.lastSnapInfo = {
      gridSnapped: false,
      angleSnapped: false,
      endpointSnapped: false,
      snappedPoint: null,
      snappedAngle: null,
      nearbyEndpoint: null,
    };

    // 1. First check endpoint snapping (highest priority)
    if (this.endpointSnapEnabled) {
      const endpointResult = this.snapToEndpoint(point);
      if (endpointResult.snapped) {
        this.lastSnapInfo.endpointSnapped = true;
        this.lastSnapInfo.nearbyEndpoint = endpointResult.endpoint;
        snapped = endpointResult.point;
        // Return early - endpoint snap overrides others
        this.lastSnapInfo.snappedPoint = snapped;
        return { ...snapped, snapInfo: { ...this.lastSnapInfo } };
      }
    }

    // 2. Angle snapping (if we have an anchor)
    if (this.angleSnapEnabled && anchor) {
      const angleResult = this.snapToAngle(point, anchor);
      if (angleResult.snapped) {
        this.lastSnapInfo.angleSnapped = true;
        this.lastSnapInfo.snappedAngle = angleResult.angle;
        snapped = angleResult.point;
      }
    }

    // 3. Grid snapping
    if (this.gridEnabled) {
      const gridResult = this.snapToGrid(snapped);
      if (gridResult.snapped) {
        this.lastSnapInfo.gridSnapped = true;
        snapped = gridResult.point;
      }
    }

    this.lastSnapInfo.snappedPoint = snapped;
    return { ...snapped, snapInfo: { ...this.lastSnapInfo } };
  }

  /**
   * Snap point to nearest grid intersection
   */
  snapToGrid(point) {
    const gridSize = SETTINGS.snap.gridSize;
    const snappedPoint = snapPointToGrid(point, gridSize);
    
    const dist = distance(point, snappedPoint);
    const threshold = gridSize / 2;
    
    return {
      point: snappedPoint,
      snapped: dist < threshold,
      distance: dist,
    };
  }

  /**
   * Snap angle to nearest allowed angle
   * Returns a point at the snapped angle from anchor, same distance as original
   */
  snapToAngle(point, anchor) {
    const currentAngle = toDegrees(angle(anchor, point));
    const normalizedAngle = normalizeAngle(currentAngle);
    
    const { angleSnapAngles, angleSnapThreshold } = SETTINGS.snap;
    const { snapped: snappedAngle, didSnap } = snapAngleUtil(
      normalizedAngle,
      angleSnapAngles,
      angleSnapThreshold
    );

    if (!didSnap) {
      return { point, snapped: false, angle: currentAngle };
    }

    // Calculate new point at snapped angle, same distance from anchor
    const dist = distance(anchor, point);
    const angleRad = toRadians(snappedAngle);
    
    const newPoint = {
      x: anchor.x + dist * Math.cos(angleRad),
      y: anchor.y + dist * Math.sin(angleRad),
    };

    return {
      point: newPoint,
      snapped: true,
      angle: snappedAngle,
    };
  }

  /**
   * Snap to nearest endpoint from existing shapes
   */
  snapToEndpoint(point) {
    const threshold = SETTINGS.snap.endpointSnapThreshold;
    
    let nearestEndpoint = null;
    let nearestDistance = Infinity;
    
    for (const endpoint of this.endpoints) {
      const dist = distance(point, endpoint);
      if (dist < nearestDistance && dist < threshold) {
        nearestDistance = dist;
        nearestEndpoint = endpoint;
      }
    }
    
    if (nearestEndpoint) {
      return {
        point: { ...nearestEndpoint },
        snapped: true,
        endpoint: nearestEndpoint,
        distance: nearestDistance,
      };
    }
    
    return { point, snapped: false, endpoint: null };
  }

  /**
   * Add an endpoint to the snap targets
   */
  addEndpoint(point) {
    // Check if endpoint already exists nearby
    const threshold = 5;  // Pixels
    for (const ep of this.endpoints) {
      if (distance(ep, point) < threshold) {
        return;  // Already have this endpoint
      }
    }
    this.endpoints.push({ x: point.x, y: point.y });
  }

  /**
   * Add endpoints from a shape
   */
  addShapeEndpoints(shape) {
    switch (shape.type) {
      case 'line':
        this.addEndpoint(shape.start);
        this.addEndpoint(shape.end);
        break;
      
      case 'rectangle':
        for (const corner of shape.corners) {
          this.addEndpoint(corner);
        }
        break;
      
      case 'circle':
        // Add center and cardinal points
        this.addEndpoint(shape.center);
        this.addEndpoint({ x: shape.center.x + shape.radius, y: shape.center.y });
        this.addEndpoint({ x: shape.center.x - shape.radius, y: shape.center.y });
        this.addEndpoint({ x: shape.center.x, y: shape.center.y + shape.radius });
        this.addEndpoint({ x: shape.center.x, y: shape.center.y - shape.radius });
        break;
      
      case 'arc':
        this.addEndpoint(shape.startPoint);
        this.addEndpoint(shape.endPoint);
        this.addEndpoint(shape.center);
        break;
      
      case 'polyline':
        for (const point of shape.points) {
          this.addEndpoint(point);
        }
        break;
    }
  }

  /**
   * Remove all endpoints for a shape (for undo)
   */
  removeShapeEndpoints(shape) {
    // For simplicity, just rebuild the endpoint list
    // This is called during undo operations
    // We'll rebuild from remaining shapes in the editor state
  }

  /**
   * Clear all endpoints
   */
  clearEndpoints() {
    this.endpoints = [];
  }

  /**
   * Rebuild endpoints from a list of shapes
   */
  rebuildEndpoints(shapes) {
    this.clearEndpoints();
    for (const shape of shapes) {
      this.addShapeEndpoints(shape);
    }
  }

  /**
   * Get preview line for angle snapping
   * Shows construction line at snapped angle
   */
  getAnglePreviewLine(anchor, point) {
    if (!this.angleSnapEnabled || !anchor) return null;
    
    const { angleSnapped, snappedAngle } = this.lastSnapInfo;
    if (!angleSnapped) return null;
    
    // Extend line in both directions for visual feedback
    const dist = distance(anchor, point);
    const extensionFactor = 1.5;
    const angleRad = toRadians(snappedAngle);
    
    return {
      start: {
        x: anchor.x - dist * extensionFactor * Math.cos(angleRad),
        y: anchor.y - dist * extensionFactor * Math.sin(angleRad),
      },
      end: {
        x: anchor.x + dist * extensionFactor * Math.cos(angleRad),
        y: anchor.y + dist * extensionFactor * Math.sin(angleRad),
      },
      angle: snappedAngle,
    };
  }

  /**
   * Toggle grid snapping
   */
  toggleGrid() {
    this.gridEnabled = !this.gridEnabled;
    return this.gridEnabled;
  }

  /**
   * Toggle angle snapping
   */
  toggleAngle() {
    this.angleSnapEnabled = !this.angleSnapEnabled;
    return this.angleSnapEnabled;
  }

  /**
   * Toggle endpoint snapping
   */
  toggleEndpoint() {
    this.endpointSnapEnabled = !this.endpointSnapEnabled;
    return this.endpointSnapEnabled;
  }

  /**
   * Get current snap settings for HUD display
   */
  getSnapStatus() {
    return {
      grid: this.gridEnabled,
      angle: this.angleSnapEnabled,
      endpoint: this.endpointSnapEnabled,
    };
  }

  /**
   * Get last snap info for visual feedback
   */
  getLastSnapInfo() {
    return this.lastSnapInfo;
  }
}
