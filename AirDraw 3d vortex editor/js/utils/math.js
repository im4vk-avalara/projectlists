/**
 * Math utilities for geometry calculations
 */

/**
 * Calculate Euclidean distance between two points
 */
export function distance(p1, p2) {
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Calculate angle between two points (in radians)
 * Returns angle from p1 to p2
 */
export function angle(p1, p2) {
  return Math.atan2(p2.y - p1.y, p2.x - p1.x);
}

/**
 * Convert radians to degrees
 */
export function toDegrees(radians) {
  return radians * (180 / Math.PI);
}

/**
 * Convert degrees to radians
 */
export function toRadians(degrees) {
  return degrees * (Math.PI / 180);
}

/**
 * Normalize angle to [0, 360) range
 */
export function normalizeAngle(degrees) {
  while (degrees < 0) degrees += 360;
  while (degrees >= 360) degrees -= 360;
  return degrees;
}

/**
 * Calculate perpendicular distance from a point to a line
 * Line defined by two points (lineStart, lineEnd)
 */
export function perpendicularDistance(point, lineStart, lineEnd) {
  const dx = lineEnd.x - lineStart.x;
  const dy = lineEnd.y - lineStart.y;
  const lineLengthSq = dx * dx + dy * dy;
  
  if (lineLengthSq === 0) {
    return distance(point, lineStart);
  }
  
  // Project point onto line
  const t = Math.max(0, Math.min(1, 
    ((point.x - lineStart.x) * dx + (point.y - lineStart.y) * dy) / lineLengthSq
  ));
  
  const projection = {
    x: lineStart.x + t * dx,
    y: lineStart.y + t * dy,
  };
  
  return distance(point, projection);
}

/**
 * Ramer-Douglas-Peucker algorithm for polyline simplification
 * @param {Array<{x: number, y: number}>} points - Input points
 * @param {number} epsilon - Tolerance for simplification
 * @returns {Array<{x: number, y: number}>} Simplified points
 */
export function rdpSimplify(points, epsilon) {
  if (points.length < 3) {
    return points.slice();
  }
  
  // Find the point with the maximum distance from the line between first and last
  let maxDist = 0;
  let maxIndex = 0;
  
  const first = points[0];
  const last = points[points.length - 1];
  
  for (let i = 1; i < points.length - 1; i++) {
    const dist = perpendicularDistance(points[i], first, last);
    if (dist > maxDist) {
      maxDist = dist;
      maxIndex = i;
    }
  }
  
  // If max distance is greater than epsilon, recursively simplify
  if (maxDist > epsilon) {
    const left = rdpSimplify(points.slice(0, maxIndex + 1), epsilon);
    const right = rdpSimplify(points.slice(maxIndex), epsilon);
    
    // Combine results (remove duplicate middle point)
    return left.slice(0, -1).concat(right);
  } else {
    // All points between first and last are within epsilon, so just keep endpoints
    return [first, last];
  }
}

/**
 * Least squares line fit
 * Returns line parameters: slope, intercept, and error metrics
 * @param {Array<{x: number, y: number}>} points
 * @returns {{slope: number, intercept: number, start: {x,y}, end: {x,y}, error: number}}
 */
export function fitLine(points) {
  if (points.length < 2) {
    return null;
  }
  
  const n = points.length;
  
  // Calculate means
  let sumX = 0, sumY = 0;
  for (const p of points) {
    sumX += p.x;
    sumY += p.y;
  }
  const meanX = sumX / n;
  const meanY = sumY / n;
  
  // Calculate covariance and variance
  let covXY = 0, varX = 0, varY = 0;
  for (const p of points) {
    const dx = p.x - meanX;
    const dy = p.y - meanY;
    covXY += dx * dy;
    varX += dx * dx;
    varY += dy * dy;
  }
  
  // Determine if line is more horizontal or vertical
  let lineStart, lineEnd;
  
  if (varX < 0.001 && varY < 0.001) {
    // All points are essentially the same
    return null;
  }
  
  if (varX >= varY) {
    // More horizontal - use y = mx + b form
    const slope = covXY / varX;
    const intercept = meanY - slope * meanX;
    
    // Find extents along x
    let minX = Infinity, maxX = -Infinity;
    for (const p of points) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
    }
    
    lineStart = { x: minX, y: slope * minX + intercept };
    lineEnd = { x: maxX, y: slope * maxX + intercept };
  } else {
    // More vertical - use x = my + b form
    const slope = covXY / varY;
    const intercept = meanX - slope * meanY;
    
    // Find extents along y
    let minY = Infinity, maxY = -Infinity;
    for (const p of points) {
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
    
    lineStart = { x: slope * minY + intercept, y: minY };
    lineEnd = { x: slope * maxY + intercept, y: maxY };
  }
  
  // Calculate mean squared perpendicular distance (error)
  let totalError = 0;
  for (const p of points) {
    const d = perpendicularDistance(p, lineStart, lineEnd);
    totalError += d * d;
  }
  const mse = totalError / n;
  const rmse = Math.sqrt(mse);
  
  return {
    start: lineStart,
    end: lineEnd,
    length: distance(lineStart, lineEnd),
    error: rmse,
  };
}

/**
 * Algebraic circle fit using Kasa method
 * Simple and fast, but can be biased for arcs
 * @param {Array<{x: number, y: number}>} points
 * @returns {{center: {x,y}, radius: number, error: number}}
 */
export function fitCircle(points) {
  if (points.length < 3) {
    return null;
  }
  
  const n = points.length;
  
  // Calculate means
  let sumX = 0, sumY = 0;
  for (const p of points) {
    sumX += p.x;
    sumY += p.y;
  }
  const meanX = sumX / n;
  const meanY = sumY / n;
  
  // Center the data
  const centered = points.map(p => ({
    x: p.x - meanX,
    y: p.y - meanY,
  }));
  
  // Build matrices for least squares: minimize sum((x-a)^2 + (y-b)^2 - r^2)^2
  // This leads to: Suu*a + Suv*b = 0.5*Suuu + 0.5*Suvv, etc.
  let Suu = 0, Suv = 0, Svv = 0;
  let Suuu = 0, Svvv = 0, Suvv = 0, Svuu = 0;
  
  for (const p of centered) {
    const uu = p.x * p.x;
    const vv = p.y * p.y;
    Suu += uu;
    Suv += p.x * p.y;
    Svv += vv;
    Suuu += uu * p.x;
    Svvv += vv * p.y;
    Suvv += p.x * vv;
    Svuu += p.y * uu;
  }
  
  // Solve 2x2 system
  const det = Suu * Svv - Suv * Suv;
  if (Math.abs(det) < 1e-10) {
    return null; // Points are collinear
  }
  
  const a = (Svv * (Suuu + Suvv) - Suv * (Svvv + Svuu)) / (2 * det);
  const b = (Suu * (Svvv + Svuu) - Suv * (Suuu + Suvv)) / (2 * det);
  
  // Calculate radius
  const radius = Math.sqrt(a * a + b * b + (Suu + Svv) / n);
  
  // Transform center back to original coordinates
  const center = {
    x: a + meanX,
    y: b + meanY,
  };
  
  // Calculate error (root mean square of radial distances)
  let totalError = 0;
  for (const p of points) {
    const d = Math.abs(distance(p, center) - radius);
    totalError += d * d;
  }
  const rmse = Math.sqrt(totalError / n);
  
  return {
    center,
    radius,
    error: rmse,
  };
}

/**
 * Calculate the angle subtended by an arc given points
 * @param {Array<{x: number, y: number}>} points
 * @param {{x: number, y: number}} center
 * @returns {number} Angle in degrees
 */
export function calculateArcAngle(points, center) {
  if (points.length < 2) return 0;
  
  // Get angles of first and last points from center
  const startAngle = angle(center, points[0]);
  const endAngle = angle(center, points[points.length - 1]);
  
  // Calculate swept angle
  let swept = Math.abs(toDegrees(endAngle - startAngle));
  
  // For a full traversal, check if points wrap around
  if (swept > 180) {
    swept = 360 - swept;
  }
  
  return swept;
}

/**
 * Check if a polygon is approximately closed
 * @param {Array<{x: number, y: number}>} points
 * @param {number} threshold - Distance threshold
 * @returns {boolean}
 */
export function isPolygonClosed(points, threshold) {
  if (points.length < 3) return false;
  return distance(points[0], points[points.length - 1]) < threshold;
}

/**
 * Calculate interior angle at a vertex in a polygon
 * @param {{x: number, y: number}} prev - Previous point
 * @param {{x: number, y: number}} curr - Current vertex
 * @param {{x: number, y: number}} next - Next point
 * @returns {number} Angle in degrees (0-180)
 */
export function interiorAngle(prev, curr, next) {
  const angle1 = angle(curr, prev);
  const angle2 = angle(curr, next);
  
  let diff = Math.abs(toDegrees(angle2 - angle1));
  if (diff > 180) diff = 360 - diff;
  
  return 180 - diff;
}

/**
 * Check if angles are approximately equal to target (with tolerance)
 */
export function isAngleNear(angle, target, tolerance) {
  let diff = Math.abs(angle - target);
  if (diff > 180) diff = 360 - diff;
  return diff <= tolerance;
}

/**
 * Snap a value to nearest grid point
 */
export function snapToGrid(value, gridSize) {
  return Math.round(value / gridSize) * gridSize;
}

/**
 * Snap a 2D point to grid
 */
export function snapPointToGrid(point, gridSize) {
  return {
    x: snapToGrid(point.x, gridSize),
    y: snapToGrid(point.y, gridSize),
  };
}

/**
 * Snap angle to nearest allowed angle
 * @param {number} currentAngle - Angle in degrees
 * @param {Array<number>} allowedAngles - List of allowed angles
 * @param {number} tolerance - Tolerance in degrees
 * @returns {{snapped: number, didSnap: boolean}}
 */
export function snapAngle(currentAngle, allowedAngles, tolerance) {
  const normalized = normalizeAngle(currentAngle);
  
  for (const target of allowedAngles) {
    let diff = Math.abs(normalized - target);
    if (diff > 180) diff = 360 - diff;
    
    if (diff <= tolerance) {
      return { snapped: target, didSnap: true };
    }
  }
  
  return { snapped: currentAngle, didSnap: false };
}

/**
 * Calculate centroid of points
 */
export function centroid(points) {
  if (points.length === 0) return { x: 0, y: 0 };
  
  let sumX = 0, sumY = 0;
  for (const p of points) {
    sumX += p.x;
    sumY += p.y;
  }
  
  return {
    x: sumX / points.length,
    y: sumY / points.length,
  };
}

/**
 * Calculate bounding box of points
 */
export function boundingBox(points) {
  if (points.length === 0) return null;
  
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;
  
  for (const p of points) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  
  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
    center: { x: (minX + maxX) / 2, y: (minY + maxY) / 2 },
  };
}

/**
 * Linear interpolation
 */
export function lerp(a, b, t) {
  return a + (b - a) * t;
}

/**
 * Clamp value between min and max
 */
export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
