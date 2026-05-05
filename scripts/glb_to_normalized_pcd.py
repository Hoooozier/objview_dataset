import argparse
import gc
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import open3d as o3d


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON root to be an object: {path}")
    return data


def save_json_atomic(data: Dict[str, Any], path: Path) -> None:
    ensure_dir(path.parent)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def parse_normalization_record(uid: str, record: Any) -> Tuple[np.ndarray, float]:
    if not isinstance(record, dict):
        raise ValueError(f"Normalization record for uid={uid} must be an object")

    center = record.get("translation_center")
    scale = record.get("scale")
    if not isinstance(center, list) or len(center) != 3:
        raise ValueError(f"Invalid translation_center for uid={uid}")

    center_arr = np.asarray(center, dtype=np.float64)
    scale_float = float(scale)

    if not np.isfinite(center_arr).all():
        raise ValueError(f"Non-finite translation_center for uid={uid}")
    if not np.isfinite(scale_float) or scale_float <= 0:
        raise ValueError(f"Invalid scale for uid={uid}: {scale_float}")

    return center_arr, scale_float


def load_glb_as_triangle_mesh(glb_path: Path) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(
        str(glb_path),
        enable_post_processing=True,
        print_progress=False,
    )

    if mesh is None:
        raise RuntimeError("Open3D returned None for mesh")
    if len(mesh.vertices) == 0:
        raise RuntimeError("Mesh has no vertices")
    if len(mesh.triangles) == 0:
        raise RuntimeError("Mesh has no triangles")

    return mesh


def sample_points_poisson(mesh: o3d.geometry.TriangleMesh, num_points: int) -> o3d.geometry.PointCloud:
    pcd = mesh.sample_points_poisson_disk(number_of_points=num_points)
    if pcd is None:
        raise RuntimeError("Poisson sampling returned None")

    pts = np.asarray(pcd.points)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0:
        raise RuntimeError("Poisson sampling produced invalid points")

    return pcd


def compute_center_and_scale(points: np.ndarray) -> Tuple[np.ndarray, float]:
    center = points.mean(axis=0)
    dists = np.linalg.norm(points - center[None, :], axis=1)
    scale = float(dists.max())

    if not np.isfinite(center).all():
        raise RuntimeError("Invalid center computed")
    if not np.isfinite(scale) or scale <= 0:
        raise RuntimeError("Invalid scale computed")

    return center, scale


def normalize_points(points: np.ndarray, center: np.ndarray, scale: float) -> np.ndarray:
    normalized = (points - center[None, :]) / scale
    if not np.isfinite(normalized).all():
        raise RuntimeError("Non-finite points after normalization")
    return normalized


def save_pcd(points: np.ndarray, out_path: Path) -> None:
    ensure_dir(out_path.parent)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))

    ok = o3d.io.write_point_cloud(
        str(out_path),
        pcd,
        write_ascii=False,
        compressed=False,
        print_progress=False,
    )
    if not ok:
        raise RuntimeError(f"Failed to write PCD: {out_path}")


def get_or_compute_normalization(
    uid: str,
    points: np.ndarray,
    normalization: Dict[str, Any],
) -> Tuple[np.ndarray, float, bool]:
    if uid in normalization:
        center, scale = parse_normalization_record(uid, normalization[uid])
        return center, scale, False

    center, scale = compute_center_and_scale(points)
    normalization[uid] = {
        "uid": uid,
        "translation_center": [float(x) for x in center.tolist()],
        "scale": float(scale),
    }
    return center, scale, True


def process_one_glb(
    glb_path: Path,
    output_dir: Path,
    normalization_path: Optional[Path],
    num_points: int,
) -> Dict[str, Any]:
    uid = glb_path.stem
    normalization = load_json_dict(normalization_path) if normalization_path else {}

    mesh = None
    sampled_pcd = None
    points = None

    try:
        mesh = load_glb_as_triangle_mesh(glb_path)
        sampled_pcd = sample_points_poisson(mesh, num_points=num_points)
        points = np.asarray(sampled_pcd.points)

        center, scale, computed_new = get_or_compute_normalization(uid, points, normalization)
        normalized_points = normalize_points(points, center, scale)

        out_path = output_dir / f"{uid}.pcd"
        save_pcd(normalized_points, out_path)

        if normalization_path and computed_new:
            save_json_atomic(normalization, normalization_path)

        return {
            "uid": uid,
            "pcd_path": str(out_path),
            "translation_center": [float(x) for x in center.tolist()],
            "scale": float(scale),
            "normalization_source": "computed" if computed_new else "json",
            "num_points": int(points.shape[0]),
        }

    finally:
        del mesh
        del sampled_pcd
        del points
        gc.collect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample a GLB into a normalized PCD, using normalization JSON when available."
    )
    parser.add_argument("--glb-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--num-points", type=int, default=20000)
    parser.add_argument("--normalization-json", type=Path, default=Path("normalization.json"))
    parser.add_argument("--result-json", type=Path, default=None)
    args = parser.parse_args()

    record = process_one_glb(
        glb_path=args.glb_path,
        output_dir=args.output_dir,
        normalization_path=args.normalization_json,
        num_points=args.num_points,
    )

    if args.result_json:
        save_json_atomic(record, args.result_json)
    else:
        print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
