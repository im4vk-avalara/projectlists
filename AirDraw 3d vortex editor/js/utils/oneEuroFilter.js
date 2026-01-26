/**
 * One Euro Filter Implementation
 * 
 * A simple speed-adaptive low-pass filter for noisy signals.
 * Paper: "1€ Filter: A Simple Speed-based Low-pass Filter for Noisy Input in Interactive Systems"
 * by Géry Casiez, Nicolas Roussel, and Daniel Vogel (CHI 2012)
 * 
 * The key insight: use a higher cutoff frequency when the signal is changing fast (to reduce lag)
 * and a lower cutoff when it's stable (to reduce jitter).
 */

/**
 * Low-pass filter using exponential smoothing
 */
class LowPassFilter {
  constructor(alpha, initVal = 0) {
    this.alpha = alpha;
    this.s = initVal;
    this.initialized = initVal !== 0;
  }

  /**
   * Apply filter to new value
   * @param {number} value - New input value
   * @param {number} alpha - Optional new alpha value
   * @returns {number} Filtered value
   */
  filter(value, alpha = null) {
    if (alpha !== null) {
      this.alpha = alpha;
    }
    
    if (!this.initialized) {
      this.s = value;
      this.initialized = true;
    } else {
      // Exponential moving average: s = alpha * value + (1 - alpha) * s_prev
      this.s = this.alpha * value + (1 - this.alpha) * this.s;
    }
    
    return this.s;
  }

  /**
   * Get last filtered value
   */
  lastValue() {
    return this.s;
  }

  /**
   * Reset the filter
   */
  reset() {
    this.s = 0;
    this.initialized = false;
  }
}

/**
 * One Euro Filter for a single value
 */
export class OneEuroFilter {
  /**
   * @param {number} minCutoff - Minimum cutoff frequency (Hz). Lower = more smoothing but more lag.
   * @param {number} beta - Speed coefficient. Higher = more speed-adaptive.
   * @param {number} dCutoff - Derivative cutoff frequency (Hz). Usually 1.0.
   */
  constructor(minCutoff = 1.0, beta = 0.007, dCutoff = 1.0) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
    
    this.xFilter = new LowPassFilter(1);
    this.dxFilter = new LowPassFilter(1);
    
    this.lastTime = null;
  }

  /**
   * Compute alpha for a given cutoff frequency and time period
   * alpha = 1 / (1 + tau/Te) where tau = 1/(2*pi*fc)
   */
  computeAlpha(cutoff, dt) {
    const tau = 1.0 / (2 * Math.PI * cutoff);
    return 1.0 / (1.0 + tau / dt);
  }

  /**
   * Filter a value
   * @param {number} value - Input value
   * @param {number} timestamp - Current timestamp in seconds (optional, will use Date.now() if not provided)
   * @returns {number} Filtered value
   */
  filter(value, timestamp = null) {
    if (timestamp === null) {
      timestamp = Date.now() / 1000;
    }

    // Initialize on first call
    if (this.lastTime === null) {
      this.lastTime = timestamp;
      this.xFilter.filter(value, 1.0);
      this.dxFilter.filter(0, 1.0);
      return value;
    }

    // Compute time delta
    const dt = timestamp - this.lastTime;
    this.lastTime = timestamp;

    // Prevent division by zero or negative dt
    if (dt <= 0) {
      return this.xFilter.lastValue();
    }

    // Estimate derivative (velocity)
    const dx = (value - this.xFilter.lastValue()) / dt;
    
    // Filter the derivative
    const alphaD = this.computeAlpha(this.dCutoff, dt);
    const dxSmoothed = this.dxFilter.filter(dx, alphaD);

    // Adaptive cutoff based on speed
    // Higher speed = higher cutoff = less lag
    const cutoff = this.minCutoff + this.beta * Math.abs(dxSmoothed);
    
    // Filter the value
    const alpha = this.computeAlpha(cutoff, dt);
    return this.xFilter.filter(value, alpha);
  }

  /**
   * Reset the filter state
   */
  reset() {
    this.lastTime = null;
    this.xFilter.reset();
    this.dxFilter.reset();
  }

  /**
   * Update filter parameters
   */
  setParameters(minCutoff, beta, dCutoff) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
  }
}

/**
 * One Euro Filter for 2D points
 * Applies separate filters to X and Y coordinates
 */
export class OneEuroFilter2D {
  /**
   * @param {number} minCutoff - Minimum cutoff frequency (Hz)
   * @param {number} beta - Speed coefficient
   * @param {number} dCutoff - Derivative cutoff frequency (Hz)
   */
  constructor(minCutoff = 1.0, beta = 0.007, dCutoff = 1.0) {
    this.filterX = new OneEuroFilter(minCutoff, beta, dCutoff);
    this.filterY = new OneEuroFilter(minCutoff, beta, dCutoff);
  }

  /**
   * Filter a 2D point
   * @param {number} x - X coordinate
   * @param {number} y - Y coordinate
   * @param {number} timestamp - Current timestamp in seconds
   * @returns {{x: number, y: number}} Filtered point
   */
  filter(x, y, timestamp = null) {
    return {
      x: this.filterX.filter(x, timestamp),
      y: this.filterY.filter(y, timestamp),
    };
  }

  /**
   * Reset both filters
   */
  reset() {
    this.filterX.reset();
    this.filterY.reset();
  }

  /**
   * Update filter parameters for both axes
   */
  setParameters(minCutoff, beta, dCutoff) {
    this.filterX.setParameters(minCutoff, beta, dCutoff);
    this.filterY.setParameters(minCutoff, beta, dCutoff);
  }
}
