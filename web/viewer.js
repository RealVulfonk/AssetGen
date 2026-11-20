import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class TwinViewer {
  constructor() {
    this.views = [];
    this.token = 0;
    this.resources = null;
    for (const id of ['textured', 'solid']) {
      const element = document.getElementById(id);
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      element.append(renderer.domElement);
      const scene = new THREE.Scene();
      scene.add(new THREE.HemisphereLight(0xe9f1ff, 0x8a8273, 2.4));
      const light = new THREE.DirectionalLight(0xfff4e6, 3);
      light.position.set(3, 6, 5); scene.add(light);
      const camera = new THREE.PerspectiveCamera(38, 1, 0.001, 10000);
      const controls = new OrbitControls(camera, renderer.domElement);
      const view = { element, renderer, scene, camera, controls, model: null };
      controls.addEventListener('change', () => {
        if (this.syncing) return;
        this.syncing = true;
        for (const other of this.views) {
          if (other === view) continue;
          other.camera.position.copy(camera.position);
          other.controls.target.copy(controls.target);
          other.controls.update();
        }
        this.syncing = false;
        this.render();
      });
      this.views.push(view);
      new ResizeObserver(() => this.render()).observe(element);
    }
    this.grey = new THREE.MeshStandardMaterial({ color: 0xaab6bf, roughness: 0.95, side: THREE.DoubleSide, flatShading: true });
  }
  message(text) {
    for (const v of this.views) v.element.querySelector('.view-message').textContent = text;
  }
  dispose(root) {
    if (!root) return;
    const geometries = new Set(), materials = new Set(), textures = new Set();
    root.traverse(node => {
      if (node.geometry) geometries.add(node.geometry);
      for (const mat of [node.material].flat().filter(Boolean)) {
        if (mat === this.grey) continue;
        materials.add(mat);
        for (const value of Object.values(mat)) if (value?.isTexture) textures.add(value);
      }
    });
    textures.forEach(t => t.dispose()); materials.forEach(m => m.dispose()); geometries.forEach(g => g.dispose());
  }
  clear() {
    for (const v of this.views) { if (v.model) v.scene.remove(v.model); v.model = null; }
    this.dispose(this.resources); this.resources = null;
  }
  async load(asset) {
    const token = ++this.token;
    this.clear(); this.render();
    if (!asset.built) { this.message('Модель ещё не собрана. Запекание соберёт геометрию автоматически.'); return; }
    this.message('Загрузка модели…');
    try {
      const gltf = await new GLTFLoader().loadAsync(`/asset/${asset.name}/${asset.name}.glb?v=${asset.version}`);
      if (token !== this.token) { this.dispose(gltf.scene); return; }
      const root = gltf.scene;
      const box = new THREE.Box3().setFromObject(root);
      const center = box.getCenter(new THREE.Vector3());
      root.position.sub(center);
      this.radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.01);
      this.resources = root;
      const solid = root.clone(true);
      solid.traverse(node => { if (node.isMesh) node.material = this.grey; });
      [root, solid].forEach((model, i) => { this.views[i].model = model; this.views[i].scene.add(model); });
      this.message(''); this.fit();
    } catch (error) { if (token === this.token) this.message(`Не удалось загрузить GLB: ${error.message}`); }
  }
  fit() {
    const radius = this.radius || 1;
    this.syncing = true;
    for (const v of this.views) {
      const aspect = Math.max(v.element.clientWidth / v.element.clientHeight, 0.1);
      const fov = THREE.MathUtils.degToRad(38);
      const distance = radius / Math.sin(Math.min(fov, 2 * Math.atan(Math.tan(fov / 2) * aspect)) / 2) * 1.1;
      v.camera.position.copy(new THREE.Vector3(1, 0.6, 1.5).normalize().multiplyScalar(distance));
      v.camera.near = radius / 1000; v.camera.far = radius * 1000;
      v.controls.target.set(0, 0, 0); v.controls.maxDistance = radius * 100;
      v.controls.minDistance = radius * 0.03; v.controls.update();
    }
    this.syncing = false; this.render();
  }
  render() {
    for (const v of this.views) {
      const w = v.element.clientWidth, h = v.element.clientHeight;
      if (!w || !h) continue;
      v.renderer.setSize(w, h, false); v.camera.aspect = w / h; v.camera.updateProjectionMatrix();
      v.renderer.render(v.scene, v.camera);
    }
  }
}
