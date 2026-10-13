"""Exercise disposal without a browser or WebGL (requires apps/web npm dependencies)."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for three.js")
def test_shared_resources_and_renderer_counters():
    web = Path(__file__).resolve().parents[2] / "apps/web"
    if not (web / "node_modules/typescript").is_dir():
        pytest.skip("run npm ci in apps/web first")
    result = subprocess.run(
        [
            "node",
            "-e",
            r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const ts = require('typescript');
const THREE = require('three');
const source = fs.readFileSync('src/dispose3d.ts', 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
}).outputText;
const api = {};
const browserWindow = {};
vm.runInNewContext(code, { exports: api, require, window: browserWindow });
const root = new THREE.Group();
const geometry = new THREE.BufferGeometry();
const texture = new THREE.Texture();
const a = new THREE.MeshBasicMaterial({ map: texture });
const b = new THREE.SpriteMaterial({ map: texture });
const counts = [0, 0, 0, 0];
[geometry, texture, a, b].forEach((resource, i) => {
  resource.addEventListener('dispose', () => counts[i]++);
});
root.add(new THREE.Mesh(geometry, [a, a]));
root.add(new THREE.Line(geometry, a));
root.add(new THREE.Points(geometry, a));
root.add(new THREE.Sprite(b));
api.disposeObject(root);
assert.deepEqual(counts, [1, 1, 1, 1]);
api.disposeObject(root); // reused resources must be disposed again
assert.deepEqual(counts, [2, 2, 2, 2]);
const removeA = api.trackRenderer({ info: { memory: { geometries: 2, textures: 3 } } });
const removeB = api.trackRenderer({ info: { memory: { geometries: 4, textures: 5 } } });
assert.equal(browserWindow.__three.renderers, 2);
assert.equal(browserWindow.__three.geometries, 6);
assert.equal(browserWindow.__three.textures, 8);
removeA(); removeB(); removeB();
assert.equal(browserWindow.__three.renderers, 0);
assert.equal(browserWindow.__three.geometries, 0);
assert.equal(browserWindow.__three.textures, 0);
""",
        ],
        cwd=web,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
