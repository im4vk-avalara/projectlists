/**
 * Shape Recognizer Module
 * Classifies strokes into geometric primitives: LINE, RECTANGLE, CIRCLE, ARC, POLYLINE
 */

import { SETTINGS } from '../settings.js';
import {
  distance,
  rdpSimplify,
  fitLine,
  fitCircle,
  isPolygonClosed,
  interiorAngle,
  isAngleNear,
  calculateArcAngle,
  boundingBox,
  centroid,
  angle,
  toDegrees,
  toRadians,
} from '../utils/math.js';

// Shape types
export const ShapeType = {
  LINE: 'line',
  RECTANGLE: 'rectangle',
  CIRCLE: 'circle',
  ARC: 'arc',
  POLYLINE: 'polyline',
};

export class ShapeRecognizer {
  constructor() {
    // Configuration
    this.config = SETTINGS.shapeRecognition;
  }

  /**
   * Recognize a shape from raw stroke points
   * @param {Array<{x: number, y: number, timestamp: number}>} rawPoints - Raw stroke points
   * @returns {Object} Recognized shape with type and parameters
   */
  recognize(rawPoints) {
    if (rawPoints.length < this.config.minPoints) {
      // Too few points - return as polyline
      return this.createPolyline(rawPoints);
    }

    // Make a copy without timestamps for geometry operations
    const points = rawPoints.map(p => ({ x: p.x, y: p.y }));
    
    // Try each shape type in order of specificity
    
    // 1. Try line fit first (simplest case)
    const lineResult = this.tryLine(points);
    if (lineResult.isMatch) {
      return this.createLine(lineResult, rawPoints);
    }

    // Check if shape is closed (for rectangle/circle detection)
    const isClosed = isPolygonClosed(points, this.config.rectClosureThreshold);
    
    // 2. Try circle/arc (check before rectangle as circles can be mistaken for squares)
    const circleResult = this.tryCircle(points, isClosed);
    if (circleResult.isMatch) {
      if (circleResult.isFullCircle) {
        return this.createCircle(circleResult, rawPoints);
      } else {
        return this.createArc(circleResult, rawPoints);
      }
    }

    // 3. Try rectangle (closed quadrilateral with ~90° corners)
    if (isClosed) {
      const rectResult = this.tryRectangle(points);
      if (rectResult.isMatch) {
        return this.createRectangle(rectResult, rawPoints);
      }
    }

    // 4. Fallback to polyline (simplified)
    return this.createPolyline(rawPoints);
  }

  /**
   * Attempt to fit a line to points
   */
  tryLine(points) {
    const fit = fitLine(points);
    
    if (!fit) {
      return { isMatch: false };
    }

    const isMatch = fit.error < this.config.lineErrorThreshold;
    
    return {
      isMatch,
      start: fit.start,
      end: fit.end,
      length: fit.length,
      error: fit.error,
    };
  }

  /**
   * Attempt to fit a circle or arc to points
   */
  tryCircle(points, isClosed) {
    const fit = fitCircle(points);
    
    if (!fit) {
      return { isMatch: false };
    }

    const isMatch = fit.error < this.config.circleErrorThreshold;
    
    if (!isMatch) {
      return { isMatch: false };
    }

    // Check if it's a full circle or an arc
    const arcAngle = calculateArcAngle(points, fit.center);
    const isFullCircle = isClosed && arcAngle > 300;  // Allow some tolerance
    
    // For arcs, check minimum angle
    if (!isFullCircle && arcAngle < this.config.arcMinAngle) {
      return { isMatch: false };  // Too small of an arc, probably just a curve
    }

    // Calculate start and end angles for arc
    const startAngle = angle(fit.center, points[0]);
    const endAngle = angle(fit.center, points[points.length - 1]);

    return {
      isMatch: true,
      isFullCircle,
      center: fit.center,
      radius: fit.radius,
      error: fit.error,
      startAngle: toDegrees(startAngle),
      endAngle: toDegrees(endAngle),
      arcAngle,
      startPoint: points[0],
      endPoint: points[points.length - 1],
    };
  }

  /**
   * Attempt to detect a rectangle from points
   */
  tryRectangle(points) {
    // Simplify the polygon to find corners
    const simplified = rdpSimplify(points, this.config.rdpEpsilon);
    
    // For a closed rectangle, we expect 4 or 5 points (4 corners, potentially closing point)
    if (simplified.length < 4 || simplified.length > 6) {
      return { isMatch: false };
    }

    // Remove closing point if present (within threshold of first point)
    let corners = [...simplified];
    if (distance(corners[0], corners[corners.length - 1]) < this.config.rectClosureThreshold) {
      corners.pop();
    }

    // Need exactly 4 corners
    if (corners.length !== 4) {
      return { isMatch: false };
    }

    // Check that all angles are approximately 90 degrees
    const angles = [];
    for (let i = 0; i < 4; i++) {
      const prev = corners[(i - 1 + 4) % 4];
      const curr = corners[i];
      const next = corners[(i + 1) % 4];
      const ang = interiorAngle(prev, curr, next);
      angles.push(ang);
      
      if (!isAngleNear(ang, 90, this.config.rectAngleTolerance)) {
        return { isMatch: false };
      }
    }

    // Check aspect ratio of sides
    const sides = [];
    for (let i = 0; i < 4; i++) {
      sides.push(distance(corners[i], corners[(i + 1) % 4]));
    }
    
    // Opposite sides should be similar length
    const ratio1 = Math.min(sides[0], sides[2]) / Math.max(sides[0], sides[2]);
    const ratio2 = Math.min(sides[1], sides[3]) / Math.max(sides[1], sides[3]);
    
    if (ratio1 < this.config.rectMinSideRatio || ratio2 < this.config.rectMinSideRatio) {
      return { isMatch: false };
    }

    // Calculate width and height
    const width = (sides[0] + sides[2]) / 2;
    const height = (sides[1] + sides[3]) / 2;
    
    // Calculate center
    const center = centroid(corners);

    return {
      isMatch: true,
      corners,
      center,
      width,
      height,
      angles,
      sides,
    };
  }

  /**
   * Create a LINE shape result
   */
  createLine(lineResult, rawPoints) {
    return {
      type: ShapeType.LINE,
      start: { x: lineResult.start.x, y: lineResult.start.y },
      end: { x: lineResult.end.x, y: lineResult.end.y },
      length: lineResult.length,
      error: lineResult.error,
      rawPoints: rawPoints.slice(),  // Keep original for debugging
      timestamp: Date.now(),
    };
  }

  /**
   * Create a RECTANGLE shape result
   */
  createRectangle(rectResult, rawPoints) {
    // Order corners consistently (top-left, top-right, bottom-right, bottom-left)
    const orderedCorners = this.orderRectangleCorners(rectResult.corners);
    
    return {
      type: ShapeType.RECTANGLE,
      corners: orderedCorners,
      center: rectResult.center,
      width: rectResult.width,
      height: rectResult.height,
      rawPoints: rawPoints.slice(),
      timestamp: Date.now(),
    };
  }

  /**
   * Order rectangle corners in consistent order
   */
  orderRectangleCorners(corners) {
    // Find bounding box center
    const center = centroid(corners);
    
    // Categorize corners by quadrant relative to center
    const sorted = corners.slice().sort((a, b) => {
      const angleA = Math.atan2(a.y - center.y, a.x - center.x);
      const angleB = Math.atan2(b.y - center.y, b.x - center.x);
      return angleA - angleB;
    });
    
    // Rotate so top-left is first (most negative x and y from center)
    let minIndex = 0;
    let minSum = Infinity;
    for (let i = 0; i < sorted.length; i++) {
      const sum = sorted[i].x + sorted[i].y;
      if (sum < minSum) {
        minSum = sum;
        minIndex = i;
      }
    }
    
    const ordered = [];
    for (let i = 0; i < 4; i++) {
      ordered.push(sorted[(minIndex + i) % 4]);
    }
    
    return ordered;
  }

  /**
   * Create a CIRCLE shape result
   */
  createCircle(circleResult, rawPoints) {
    return {
      type: ShapeType.CIRCLE,
      center: { x: circleResult.center.x, y: circleResult.center.y },
      radius: circleResult.radius,
      diameter: circleResult.radius * 2,
      error: circleResult.error,
      rawPoints: rawPoints.slice(),
      timestamp: Date.now(),
    };
  }

  /**
   * Create an ARC shape result
   */
  createArc(arcResult, rawPoints) {
    return {
      type: ShapeType.ARC,
      center: { x: arcResult.center.x, y: arcResult.center.y },
      radius: arcResult.radius,
      startAngle: arcResult.startAngle,
      endAngle: arcResult.endAngle,
      arcAngle: arcResult.arcAngle,
      startPoint: { x: arcResult.startPoint.x, y: arcResult.startPoint.y },
      endPoint: { x: arcResult.endPoint.x, y: arcResult.endPoint.y },
      error: arcResult.error,
      rawPoints: rawPoints.slice(),
      timestamp: Date.now(),
    };
  }

  /**
   * Create a POLYLINE shape result (fallback)
   */
  createPolyline(rawPoints) {
    // Simplify the polyline using RDP
    const points = rawPoints.map(p => ({ x: p.x, y: p.y }));
    const simplified = rdpSimplify(points, this.config.rdpEpsilon);
    
    // Calculate total length
    let totalLength = 0;
    for (let i = 1; i < simplified.length; i++) {
      totalLength += distance(simplified[i - 1], simplified[i]);
    }

    return {
      type: ShapeType.POLYLINE,
      points: simplified,
      pointCount: simplified.length,
      totalLength,
      rawPoints: rawPoints.slice(),
      timestamp: Date.now(),
    };
  }

  /**
   * Get the bounding box of a shape
   */
  getShapeBounds(shape) {
    let points;
    
    switch (shape.type) {
      case ShapeType.LINE:
        points = [shape.start, shape.end];
        break;
      
      case ShapeType.RECTANGLE:
        points = shape.corners;
        break;
      
      case ShapeType.CIRCLE:
        return {
          x: shape.center.x - shape.radius,
          y: shape.center.y - shape.radius,
          width: shape.diameter,
          height: shape.diameter,
          center: shape.center,
        };
      
      case ShapeType.ARC:
        // Approximate with start, end, and center points
        points = [shape.startPoint, shape.endPoint, shape.center];
        // Add radius extension
        const arcBounds = boundingBox(points);
        return {
          x: arcBounds.x - shape.radius * 0.1,
          y: arcBounds.y - shape.radius * 0.1,
          width: arcBounds.width + shape.radius * 0.2,
          height: arcBounds.height + shape.radius * 0.2,
          center: arcBounds.center,
        };
      
      case ShapeType.POLYLINE:
        points = shape.points;
        break;
      
      default:
        return null;
    }
    
    return boundingBox(points);
  }

  /**
   * Get human-readable description of shape
   */
  describeShape(shape) {
    const ppu = SETTINGS.units.pixelsPerUnit;
    const decimals = SETTINGS.units.displayDecimals;
    const label = SETTINGS.units.unitLabel;
    
    switch (shape.type) {
      case ShapeType.LINE:
        const lineLength = (shape.length / ppu).toFixed(decimals);
        return `Line: ${lineLength}${label}`;
      
      case ShapeType.RECTANGLE:
        const width = (shape.width / ppu).toFixed(decimals);
        const height = (shape.height / ppu).toFixed(decimals);
        return `Rect: ${width}${label} × ${height}${label}`;
      
      case ShapeType.CIRCLE:
        const radius = (shape.radius / ppu).toFixed(decimals);
        const diameter = (shape.diameter / ppu).toFixed(decimals);
        return `Circle: r=${radius}${label}, d=${diameter}${label}`;
      
      case ShapeType.ARC:
        const arcRadius = (shape.radius / ppu).toFixed(decimals);
        const arcAngle = shape.arcAngle.toFixed(0);
        return `Arc: r=${arcRadius}${label}, ${arcAngle}°`;
      
      case ShapeType.POLYLINE:
        const totalLen = (shape.totalLength / ppu).toFixed(decimals);
        return `Polyline: ${shape.pointCount} pts, ${totalLen}${label}`;
      
      default:
        return 'Unknown shape';
    }
  }
}

/**
 * Get shape type display name
 */
export function getShapeTypeName(type) {
  switch (type) {
    case ShapeType.LINE: return 'Line';
    case ShapeType.RECTANGLE: return 'Rectangle';
    case ShapeType.CIRCLE: return 'Circle';
    case ShapeType.ARC: return 'Arc';
    case ShapeType.POLYLINE: return 'Polyline';
    default: return 'Unknown';
  }
}
