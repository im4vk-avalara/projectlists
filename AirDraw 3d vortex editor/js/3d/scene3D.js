/**
 * 3D Scene Module
 * Manages the Three.js scene for 3D cube manipulation
 */

import { SETTINGS } from '../settings.js';

export class Scene3D {
  constructor(container) {
    this.container = container;
    this.width = SETTINGS.canvas.width;
    this.height = SETTINGS.canvas.height;
    
    // Three.js objects
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.raycaster = null;
    
    // Lighting
    this.ambientLight = null;
    this.directionalLight = null;
    
    // Grid helper
    this.gridHelper = null;
    
    // Mouse/cursor position for raycasting
    this.pointer = { x: 0, y: 0 };
    
    // Initialize if Three.js is available
    if (typeof THREE !== 'undefined') {
      this.initialize();
    } else {
      console.error('Three.js not loaded');
    }
  }

  initialize() {
    // Create scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a1628);
    
    // Create camera (perspective for 3D view)
    this.camera = new THREE.PerspectiveCamera(
      60,  // FOV
      this.width / this.height,  // Aspect ratio
      0.1,  // Near
      1000  // Far
    );
    this.camera.position.set(0, 8, 12);
    this.camera.lookAt(0, 0, 0);
    
    // Create renderer
    this.renderer = new THREE.WebGLRenderer({ 
      antialias: true,
      alpha: true 
    });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    
    // Add renderer to container
    this.renderer.domElement.id = 'canvas3d';
    this.renderer.domElement.style.position = 'absolute';
    this.renderer.domElement.style.top = '0';
    this.renderer.domElement.style.left = '0';
    this.container.appendChild(this.renderer.domElement);
    
    // Create raycaster for picking
    this.raycaster = new THREE.Raycaster();
    
    // Add lighting
    this.setupLighting();
    
    // Add grid
    this.setupGrid();
    
    // Add ground plane (for shadows and reference)
    this.setupGround();
  }

  setupLighting() {
    // Ambient light
    this.ambientLight = new THREE.AmbientLight(0x404060, 0.5);
    this.scene.add(this.ambientLight);
    
    // Main directional light (sun)
    this.directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    this.directionalLight.position.set(5, 10, 7);
    this.directionalLight.castShadow = true;
    this.directionalLight.shadow.mapSize.width = 2048;
    this.directionalLight.shadow.mapSize.height = 2048;
    this.directionalLight.shadow.camera.near = 0.5;
    this.directionalLight.shadow.camera.far = 50;
    this.directionalLight.shadow.camera.left = -15;
    this.directionalLight.shadow.camera.right = 15;
    this.directionalLight.shadow.camera.top = 15;
    this.directionalLight.shadow.camera.bottom = -15;
    this.scene.add(this.directionalLight);
    
    // Hemisphere light for natural ambient
    const hemiLight = new THREE.HemisphereLight(0x87ceeb, 0x362c21, 0.3);
    this.scene.add(hemiLight);
    
    // Point light for extra highlights
    const pointLight = new THREE.PointLight(0x00d4ff, 0.5, 20);
    pointLight.position.set(-5, 5, 5);
    this.scene.add(pointLight);
  }

  setupGrid() {
    // Grid helper
    const gridSize = 20;
    const gridDivisions = 20;
    this.gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x00d4ff, 0x1e5090);
    this.gridHelper.position.y = 0.01;  // Slightly above ground to avoid z-fighting
    this.scene.add(this.gridHelper);
    
    // Axis helper (optional)
    // const axisHelper = new THREE.AxesHelper(5);
    // this.scene.add(axisHelper);
  }

  setupGround() {
    // Ground plane for shadows
    const groundGeometry = new THREE.PlaneGeometry(30, 30);
    const groundMaterial = new THREE.ShadowMaterial({ 
      opacity: 0.3 
    });
    const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = 0;
    ground.receiveShadow = true;
    ground.name = 'ground';
    this.scene.add(ground);
  }

  /**
   * Update pointer position for raycasting
   * @param {number} x - Screen X (0 to width)
   * @param {number} y - Screen Y (0 to height)
   */
  updatePointer(x, y) {
    // Convert to normalized device coordinates (-1 to +1)
    this.pointer.x = (x / this.width) * 2 - 1;
    this.pointer.y = -(y / this.height) * 2 + 1;
  }

  /**
   * Get intersection with objects in scene
   * @param {Array} objects - Objects to test against
   * @returns {Array} Intersection results
   */
  getIntersections(objects) {
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(objects, false);
  }

  /**
   * Get point on ground plane at cursor
   * @returns {{x: number, y: number, z: number} | null}
   */
  getGroundPoint() {
    this.raycaster.setFromCamera(this.pointer, this.camera);
    
    // Create a plane at y=0
    const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const intersection = new THREE.Vector3();
    
    if (this.raycaster.ray.intersectPlane(groundPlane, intersection)) {
      return intersection;
    }
    return null;
  }

  /**
   * Render the scene
   */
  render() {
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }

  /**
   * Add object to scene
   */
  add(object) {
    this.scene.add(object);
  }

  /**
   * Remove object from scene
   */
  remove(object) {
    this.scene.remove(object);
  }

  /**
   * Resize the renderer
   */
  resize(width, height) {
    this.width = width;
    this.height = height;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  /**
   * Orbit camera around center (for later use)
   */
  orbitCamera(deltaX, deltaY) {
    const spherical = new THREE.Spherical();
    spherical.setFromVector3(this.camera.position);
    
    spherical.theta -= deltaX * 0.01;
    spherical.phi -= deltaY * 0.01;
    spherical.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.1, spherical.phi));
    
    this.camera.position.setFromSpherical(spherical);
    this.camera.lookAt(0, 0, 0);
  }

  /**
   * Dispose of resources
   */
  dispose() {
    if (this.renderer) {
      this.renderer.dispose();
      if (this.renderer.domElement.parentNode) {
        this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
      }
    }
  }
}
