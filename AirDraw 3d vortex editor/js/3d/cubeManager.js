/**
 * Cube Manager Module
 * Handles 3D cube creation, manipulation, snapping, and deletion
 */

export class CubeManager {
  constructor(scene3D) {
    this.scene3D = scene3D;
    this.cubes = [];  // Array of cube objects
    this.selectedCube = null;
    this.hoveredCube = null;
    this.isDragging = false;
    this.isResizing = false;
    
    // Cube settings
    this.defaultSize = 1;
    this.minSize = 0.3;
    this.maxSize = 4;
    this.snapThreshold = 0.3;  // Distance to snap cubes together
    this.gridSnapSize = 0.5;   // Snap to half-unit grid
    
    // Visual feedback
    this.highlightColor = 0x00ff88;
    this.selectedColor = 0xff6464;
    this.deletePreviewColor = 0xff0000;
    
    // Cube counter for IDs
    this.cubeIdCounter = 0;
    
    // Materials
    this.createMaterials();
    
    // Undo stack
    this.undoStack = [];
  }

  createMaterials() {
    // Default cube material (blueprint style)
    this.defaultMaterial = new THREE.MeshPhongMaterial({
      color: 0x00a8cc,
      transparent: true,
      opacity: 0.85,
      shininess: 60,
    });
    
    // Wireframe overlay for blueprint look
    this.wireframeMaterial = new THREE.LineBasicMaterial({
      color: 0x00d4ff,
      linewidth: 2,
    });
    
    // Hover material
    this.hoverMaterial = new THREE.MeshPhongMaterial({
      color: 0x00ff88,
      transparent: true,
      opacity: 0.9,
      shininess: 80,
    });
    
    // Selected material
    this.selectedMaterial = new THREE.MeshPhongMaterial({
      color: 0xff6464,
      transparent: true,
      opacity: 0.9,
      shininess: 80,
    });
    
    // Delete preview material
    this.deleteMaterial = new THREE.MeshPhongMaterial({
      color: 0xff0000,
      transparent: true,
      opacity: 0.5,
      shininess: 30,
    });
    
    // Ghost/preview material
    this.ghostMaterial = new THREE.MeshPhongMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.3,
      shininess: 30,
    });
  }

  /**
   * Create a new cube at position
   * @param {THREE.Vector3} position - World position
   * @param {number} size - Cube size
   * @returns {Object} Cube data object
   */
  createCube(position, size = null) {
    const cubeSize = size || this.defaultSize;
    
    // Create geometry
    const geometry = new THREE.BoxGeometry(cubeSize, cubeSize, cubeSize);
    
    // Create mesh
    const material = this.defaultMaterial.clone();
    const mesh = new THREE.Mesh(geometry, material);
    
    // Position (snap to grid and lift so it sits on ground)
    const snappedPos = this.snapToGrid(position);
    mesh.position.set(snappedPos.x, cubeSize / 2, snappedPos.z);
    
    // Enable shadows
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    
    // Create wireframe edges
    const edges = new THREE.EdgesGeometry(geometry);
    const wireframe = new THREE.LineSegments(edges, this.wireframeMaterial.clone());
    mesh.add(wireframe);
    
    // Create cube data object
    const cubeData = {
      id: ++this.cubeIdCounter,
      mesh: mesh,
      wireframe: wireframe,
      size: cubeSize,
      originalMaterial: material,
      position: mesh.position.clone(),
    };
    
    // Store reference in mesh
    mesh.userData.cubeData = cubeData;
    mesh.name = `cube_${cubeData.id}`;
    
    // Add to scene and list
    this.scene3D.add(mesh);
    this.cubes.push(cubeData);
    
    // Save for undo
    this.pushUndo('create', cubeData);
    
    return cubeData;
  }

  /**
   * Spawn a new cube at cursor position
   */
  spawnCubeAtCursor() {
    const groundPoint = this.scene3D.getGroundPoint();
    if (groundPoint) {
      return this.createCube(groundPoint);
    }
    return null;
  }

  /**
   * Select a cube for manipulation
   */
  selectCube(cubeData) {
    // Deselect previous
    if (this.selectedCube) {
      this.selectedCube.mesh.material = this.selectedCube.originalMaterial;
    }
    
    this.selectedCube = cubeData;
    
    if (cubeData) {
      cubeData.mesh.material = this.selectedMaterial.clone();
    }
  }

  /**
   * Deselect current cube
   */
  deselectCube() {
    if (this.selectedCube) {
      this.selectedCube.mesh.material = this.selectedCube.originalMaterial;
      this.selectedCube = null;
    }
  }

  /**
   * Update hover state
   */
  setHoveredCube(cubeData) {
    // Reset previous hover
    if (this.hoveredCube && this.hoveredCube !== this.selectedCube) {
      this.hoveredCube.mesh.material = this.hoveredCube.originalMaterial;
    }
    
    this.hoveredCube = cubeData;
    
    // Apply hover material (if not selected)
    if (cubeData && cubeData !== this.selectedCube) {
      cubeData.mesh.material = this.hoverMaterial.clone();
    }
  }

  /**
   * Start dragging selected cube
   */
  startDrag() {
    if (this.selectedCube) {
      this.isDragging = true;
      this.selectedCube.dragStartPos = this.selectedCube.mesh.position.clone();
    }
  }

  /**
   * Update drag position
   * @param {THREE.Vector3} groundPoint - Current ground intersection point
   */
  updateDrag(groundPoint) {
    if (!this.isDragging || !this.selectedCube || !groundPoint) return;
    
    const cube = this.selectedCube;
    const size = cube.size;
    
    // Calculate snapped position
    let newPos = this.snapToGrid(groundPoint);
    
    // Check for snapping to other cubes
    const snapResult = this.snapToCubes(newPos, size, cube);
    if (snapResult.snapped) {
      newPos = snapResult.position;
    }
    
    // Update position (keep Y based on size)
    cube.mesh.position.set(newPos.x, size / 2, newPos.z);
    cube.position.copy(cube.mesh.position);
  }

  /**
   * End dragging
   */
  endDrag() {
    if (this.isDragging && this.selectedCube) {
      this.pushUndo('move', this.selectedCube, this.selectedCube.dragStartPos);
    }
    this.isDragging = false;
  }

  /**
   * Resize selected cube
   * @param {number} scaleFactor - Scale multiplier (>1 to grow, <1 to shrink)
   */
  resizeCube(scaleFactor) {
    if (!this.selectedCube) return;
    
    const cube = this.selectedCube;
    const oldSize = cube.size;
    let newSize = oldSize * scaleFactor;
    
    // Clamp size
    newSize = Math.max(this.minSize, Math.min(this.maxSize, newSize));
    
    if (newSize === oldSize) return;
    
    // Store for undo
    this.pushUndo('resize', cube, oldSize);
    
    // Update geometry
    const newGeometry = new THREE.BoxGeometry(newSize, newSize, newSize);
    cube.mesh.geometry.dispose();
    cube.mesh.geometry = newGeometry;
    
    // Update wireframe
    const newEdges = new THREE.EdgesGeometry(newGeometry);
    cube.wireframe.geometry.dispose();
    cube.wireframe.geometry = newEdges;
    
    // Update position (keep bottom on ground)
    cube.mesh.position.y = newSize / 2;
    cube.size = newSize;
    cube.position.copy(cube.mesh.position);
  }

  /**
   * Preview cube for deletion (visual feedback)
   */
  previewDelete(cubeData) {
    if (cubeData) {
      cubeData.mesh.material = this.deleteMaterial.clone();
    }
  }

  /**
   * Cancel delete preview
   */
  cancelDeletePreview() {
    if (this.hoveredCube && this.hoveredCube !== this.selectedCube) {
      this.hoveredCube.mesh.material = this.hoveredCube.originalMaterial;
    }
  }

  /**
   * Delete a cube
   */
  deleteCube(cubeData) {
    if (!cubeData) return;
    
    // Save for undo
    this.pushUndo('delete', cubeData);
    
    // Remove from scene
    this.scene3D.remove(cubeData.mesh);
    
    // Remove from list
    const idx = this.cubes.indexOf(cubeData);
    if (idx !== -1) {
      this.cubes.splice(idx, 1);
    }
    
    // Clear selection if deleted
    if (this.selectedCube === cubeData) {
      this.selectedCube = null;
    }
    if (this.hoveredCube === cubeData) {
      this.hoveredCube = null;
    }
    
    // Dispose resources
    cubeData.mesh.geometry.dispose();
    cubeData.mesh.material.dispose();
    cubeData.wireframe.geometry.dispose();
    cubeData.wireframe.material.dispose();
  }

  /**
   * Delete selected cube
   */
  deleteSelectedCube() {
    if (this.selectedCube) {
      this.deleteCube(this.selectedCube);
    }
  }

  /**
   * Snap position to grid
   */
  snapToGrid(position) {
    const snap = this.gridSnapSize;
    return {
      x: Math.round(position.x / snap) * snap,
      y: position.y,
      z: Math.round(position.z / snap) * snap,
    };
  }

  /**
   * Snap to nearby cubes
   */
  snapToCubes(position, size, excludeCube = null) {
    const threshold = this.snapThreshold;
    let snappedPos = { x: position.x, z: position.z };
    let didSnap = false;
    let snappedToCube = null;
    
    for (const cube of this.cubes) {
      if (cube === excludeCube) continue;
      
      const otherPos = cube.mesh.position;
      const otherSize = cube.size;
      const halfSize = (size + otherSize) / 2;
      
      const dx = position.x - otherPos.x;
      const dz = position.z - otherPos.z;
      
      // Check X-axis snapping
      if (Math.abs(Math.abs(dx) - halfSize) < threshold && Math.abs(dz) < halfSize) {
        snappedPos.x = otherPos.x + (dx > 0 ? halfSize : -halfSize);
        didSnap = true;
        snappedToCube = cube;
      }
      
      // Check Z-axis snapping
      if (Math.abs(Math.abs(dz) - halfSize) < threshold && Math.abs(dx) < halfSize) {
        snappedPos.z = otherPos.z + (dz > 0 ? halfSize : -halfSize);
        didSnap = true;
        snappedToCube = cube;
      }
      
      // Align on same axis if close
      if (Math.abs(dx) < threshold) {
        snappedPos.x = otherPos.x;
        didSnap = true;
      }
      if (Math.abs(dz) < threshold) {
        snappedPos.z = otherPos.z;
        didSnap = true;
      }
    }
    
    return {
      snapped: didSnap,
      position: snappedPos,
      snappedToCube,
    };
  }

  /**
   * Get cube at screen position
   */
  getCubeAtCursor() {
    const meshes = this.cubes.map(c => c.mesh);
    const intersections = this.scene3D.getIntersections(meshes);
    
    if (intersections.length > 0) {
      return intersections[0].object.userData.cubeData;
    }
    return null;
  }

  /**
   * Push action to undo stack
   */
  pushUndo(action, cubeData, previousValue = null) {
    this.undoStack.push({
      action,
      cubeData: {
        id: cubeData.id,
        position: cubeData.position ? cubeData.position.clone() : null,
        size: cubeData.size,
      },
      previousValue,
      mesh: action === 'delete' ? cubeData.mesh : null,
    });
    
    // Limit stack size
    if (this.undoStack.length > 30) {
      this.undoStack.shift();
    }
  }

  /**
   * Undo last action
   */
  undo() {
    if (this.undoStack.length === 0) return false;
    
    const action = this.undoStack.pop();
    
    switch (action.action) {
      case 'create':
        // Find and delete the cube
        const cubeToDelete = this.cubes.find(c => c.id === action.cubeData.id);
        if (cubeToDelete) {
          this.scene3D.remove(cubeToDelete.mesh);
          const idx = this.cubes.indexOf(cubeToDelete);
          if (idx !== -1) this.cubes.splice(idx, 1);
        }
        break;
        
      case 'delete':
        // Restore deleted cube (complex - would need to store full cube data)
        console.log('Undo delete not fully implemented');
        break;
        
      case 'move':
        const movedCube = this.cubes.find(c => c.id === action.cubeData.id);
        if (movedCube && action.previousValue) {
          movedCube.mesh.position.copy(action.previousValue);
          movedCube.position.copy(action.previousValue);
        }
        break;
        
      case 'resize':
        const resizedCube = this.cubes.find(c => c.id === action.cubeData.id);
        if (resizedCube && action.previousValue) {
          this.selectedCube = resizedCube;
          const factor = action.previousValue / resizedCube.size;
          this.resizeCube(factor);
          this.undoStack.pop();  // Remove the resize we just did
        }
        break;
    }
    
    return true;
  }

  /**
   * Clear all cubes
   */
  clearAll() {
    for (const cube of this.cubes) {
      this.scene3D.remove(cube.mesh);
      cube.mesh.geometry.dispose();
      cube.mesh.material.dispose();
    }
    this.cubes = [];
    this.selectedCube = null;
    this.hoveredCube = null;
  }

  /**
   * Get cube count
   */
  getCubeCount() {
    return this.cubes.length;
  }

  /**
   * Get all cubes for serialization
   */
  serialize() {
    return this.cubes.map(cube => ({
      id: cube.id,
      position: { x: cube.position.x, y: cube.position.y, z: cube.position.z },
      size: cube.size,
    }));
  }
}
