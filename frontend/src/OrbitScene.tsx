import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Path, Result } from "./types";

function point(path: Path, time: number): THREE.Vector3 {
  const times = path.times_s;
  const fraction = Math.max(
    0,
    Math.min(
      times.length - 1,
      (time / times[times.length - 1]) * (times.length - 1),
    ),
  );
  const i = Math.floor(fraction),
    j = Math.min(i + 1, times.length - 1),
    a = fraction - i;
  return new THREE.Vector3(
    ...(path.positions_km[i] as [number, number, number]),
  )
    .lerp(
      new THREE.Vector3(...(path.positions_km[j] as [number, number, number])),
      a,
    )
    .multiplyScalar(1 / 6378.137);
}
const globeVertex = `varying vec3 vNormal; varying vec3 vPosition; void main(){vNormal=normalize(normalMatrix*normal);vPosition=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
const globeFragment = `varying vec3 vNormal;varying vec3 vPosition;
float hash(vec3 p){p=fract(p*.3183099+vec3(.1,.2,.3));p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}
float noise(vec3 x){vec3 i=floor(x),f=fract(x);f=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1)),f.x),f.y),f.z);}
void main(){vec3 p=normalize(vPosition);float continent=noise(p*3.)*.65+noise(p*9.)*.25+noise(p*25.)*.1;float land=smoothstep(.49,.54,continent);vec3 ocean=vec3(.012,.046,.085),ground=vec3(.035,.18,.19);vec3 color=mix(ocean,ground,land);float lat=asin(p.z),lon=atan(p.y,p.x);float grid=max(pow(abs(cos(lat*18.)),85.),pow(abs(cos(lon*18.)),85.));color+=grid*vec3(.016,.07,.09);float light=.2+.8*max(dot(normalize(vNormal),normalize(vec3(-.4,.6,1.))),0.);float rim=pow(1.-abs(vNormal.z),3.);color=color*light+rim*vec3(.03,.14,.22);gl_FragColor=vec4(color,1.);}`;

export default function OrbitScene({
  result,
  time,
  after,
}: {
  result: Result;
  time: number;
  after: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const live = useRef({ time, after });
  live.current = { time, after };
  const [error, setError] = useState(false);
  useEffect(() => {
    const element = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setError(true);
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100);
    camera.position.set(2.55, -2.1, 1.7);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.minDistance = 1.5;
    controls.maxDistance = 7;
    controls.enablePan = false;
    const globe = new THREE.Mesh(
      new THREE.SphereGeometry(1, 80, 48),
      new THREE.ShaderMaterial({
        vertexShader: globeVertex,
        fragmentShader: globeFragment,
      }),
    );
    scene.add(globe);
    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.026, 64, 48),
      new THREE.MeshBasicMaterial({
        color: 0x176b88,
        transparent: true,
        opacity: 0.1,
        side: THREE.BackSide,
      }),
    );
    scene.add(atmosphere);
    const starPoints = [];
    let seed = 619;
    function random() {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    }
    for (let i = 0; i < 1400; i++) {
      const az = random() * Math.PI * 2,
        z = random() * 2 - 1,
        r = Math.sqrt(1 - z * z);
      starPoints.push(r * Math.cos(az) * 15, r * Math.sin(az) * 15, z * 15);
    }
    const starsGeometry = new THREE.BufferGeometry();
    starsGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(starPoints, 3),
    );
    scene.add(
      new THREE.Points(
        starsGeometry,
        new THREE.PointsMaterial({
          color: 0x62809c,
          size: 0.013,
          transparent: true,
          opacity: 0.7,
        }),
      ),
    );
    function line(path: Path, color: number, opacity: number) {
      const geometry = new THREE.BufferGeometry().setFromPoints(
        path.positions_km.map((p) =>
          new THREE.Vector3(...(p as [number, number, number])).multiplyScalar(
            1 / 6378.137,
          ),
        ),
      );
      const orbit = new THREE.Line(
        geometry,
        new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
      );
      scene.add(orbit);
      return orbit;
    }
    const markers: THREE.Mesh[] = [];
    for (const [i, obj] of result.objects.entries()) {
      const color = i === 0 ? 0x58e5cb : i === 1 ? 0xff826e : 0x6e8bfd;
      line(obj, color, i === 0 ? 0.3 : 0.65);
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(i === 0 ? 0.014 : 0.01, 12, 8),
        new THREE.MeshBasicMaterial({ color }),
      );
      scene.add(marker);
      markers.push(marker);
    }
    const maneuverLine = line(result.after_trajectory, 0x58e5cb, 0.9);
    maneuverLine.visible = after;
    const grid = new THREE.GridHelper(5, 24, 0x153544, 0x0d202f);
    grid.rotateX(Math.PI / 2);
    grid.position.z = -1.35;
    scene.add(grid);
    const observer = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
    });
    observer.observe(element);
    let frame = 0;
    function render() {
      const current = live.current;
      markers.forEach((marker, i) =>
        marker.position.copy(
          point(
            i === 0 && current.after
              ? result.after_trajectory
              : result.objects[i],
            current.time,
          ),
        ),
      );
      maneuverLine.visible = current.after;
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    }
    render();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        if (mesh.material) {
          (Array.isArray(mesh.material)
            ? mesh.material
            : [mesh.material]
          ).forEach((material) => material.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [result]);
  return (
    <div
      className="orbit-render"
      ref={host}
      role="img"
      aria-label="Interactive 3D synthetic orbital trajectories. Drag to rotate; scroll to zoom."
    >
      {error && (
        <div className="webgl-error">
          WebGL is unavailable. Numerical results and encounter charts remain
          accessible.
        </div>
      )}
    </div>
  );
}
