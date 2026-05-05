# ObjView Benchmark Dataset Release

This release contains benchmark annotations for ObjView assets and scripts for reproducing the geometry preprocessing pipeline.

## Files

```text
release_dataset/
  README.md
  data/
    slow_saturation_pool.json
    main_train_public.json
  scripts/
    download_objaverse_glb.py
    glb_to_normalized_pcd.py
    glb_to_obj_blender.py
    normalize_obj.py
```

This draft release does not include normalized OBJ or PCD geometry files. The geometry preprocessing scripts are provided for reproducibility and for processing additional Objaverse assets.

## JSON Schema

Each record in `data/slow_saturation_pool.json` and `data/main_train_public.json` has six fields:

```json
{
  "uid": "...",
  "translation_center": [0.0, 0.0, 0.0],
  "scale": 1.0,
  "omnidirectional_self_occlusion_attribute": 0.0,
  "observation_saturation_difficulty": 0,
  "planning_difficulty": 0
}
```

Field meanings:

- `uid`: Objaverse asset UID.
- `translation_center`: Center used by the geometry normalization transform.
- `scale`: Scale used by the geometry normalization transform.
- `omnidirectional_self_occlusion_attribute`: Precomputed benchmark annotation for omnidirectional self-occlusion.
- `observation_saturation_difficulty`: Precomputed benchmark annotation for observation saturation difficulty.
- `planning_difficulty`: Precomputed benchmark annotation for planning difficulty.

The three benchmark annotation fields are provided as fixed labels. The full benchmark annotation pipeline used to compute them is not required for using this dataset.

## Normalization

The normalization transform is:

```text
normalized_point = (raw_point - translation_center) / scale
normalized_vertex = (raw_vertex - translation_center) / scale
```

For the released assets, `translation_center` and `scale` were computed from Poisson disk sampled GLB surface points:

```text
translation_center = mean(sampled_points)
scale = max(||sampled_point - translation_center||)
```

The same normalization parameters are then used for normalized PCDs and normalized OBJs.

## Geometry Pipeline

The intended geometry processing flow is:

```text
Objaverse uid -> GLB
GLB -> normalized PCD
GLB -> OBJ with Blender 4.2.7
OBJ -> normalized OBJ
```

The OBJ path is not derived from the PCD. Both the PCD and OBJ are derived from the downloaded GLB.

## Environment

The preprocessing scripts were prepared with the following environment:

```text
Python 3.9
numpy 1.24.4
open3d 0.19.0
objaverse 0.1.7
```

Install the main Python dependencies with:

```bash
pip install -r requirements.txt
```

Optional dependency:

```bash
pip install trimesh
```

`trimesh` is only needed for the optional GLB validation mode in `scripts/download_objaverse_glb.py`.

The GLB-to-OBJ conversion script must be run with Blender, not regular Python. Blender 4.2.7 is recommended.

## Scripts

The examples below assume your shell’s current working directory is the dataset root (the directory that contains `data/` and `scripts/`). On Linux, use `blender` on your `PATH`, or pass the full path to the Blender 4.2 binary.

### Download GLB

Use `scripts/download_objaverse_glb.py` to download Objaverse assets by UID.

Example:

```bash
python scripts/download_objaverse_glb.py \
  --mode download_all \
  --json_path data/main_train_public.json \
  --target_dir glb
```

Redownload only missing or empty `.glb` files under the target directory:

```bash
python scripts/download_objaverse_glb.py \
  --mode redownload_missing \
  --json_path data/main_train_public.json \
  --target_dir glb
```

Validate that `.glb` files load in trimesh and Open3D (optional: `pip install trimesh`):

```bash
python scripts/download_objaverse_glb.py \
  --mode validate_mesh_loaders \
  --target_dir glb \
  --report_path glb_mesh_validation_report.json
```

### GLB to normalized PCD

Use `scripts/glb_to_normalized_pcd.py`:

```bash
python scripts/glb_to_normalized_pcd.py \
  --glb-path "glb/<uid>.glb" \
  --output-dir pcd_normalized \
  --normalization-json normalization.json \
  --num-points 20000
```

Write a small JSON record for the run (paths, center, scale, point count) to a file:

```bash
python scripts/glb_to_normalized_pcd.py \
  --glb-path "glb/<uid>.glb" \
  --output-dir pcd_normalized \
  --normalization-json normalization.json \
  --num-points 20000 \
  --result-json "pcd_normalized/<uid>_run.json"
```

If the UID exists in `normalization.json`, the script uses the stored `translation_center` and `scale`. If the UID is missing, the script computes them from the sampled points and writes a new normalization record.

### GLB to OBJ
Use `scripts/glb_to_obj_blender.py` with Blender 4.2.7 to convert GLB assets into standardized OBJ assets.

```bash
blender -b -P scripts/glb_to_obj_blender.py -- \
  --input_dir glb \
  --output_dir obj \
  --overwrite
```

Example:

```bash
blender -b -P scripts/glb_to_obj_blender.py -- \
  --single_glb "glb/<uid>.glb" \
  --output_dir obj \
  --overwrite
```

### OBJ to normalized OBJ

Use `scripts/normalize_obj.py` to apply the same `translation_center` and `scale` to OBJ vertices:

```text
normalized_vertex = (raw_vertex - translation_center) / scale
```

Example:

```bash
python scripts/normalize_obj.py \
  --input_dir obj \
  --output_dir obj_normalized \
  --json_path normalization.json \
  --stats_json_path obj_normalized_stats.json \
  --workers 8 \
  --overwrite
```

## Dataset Splits

- `data/main_train_public.json`: public main-pool training split.
- `data/slow_saturation_pool.json`: long-tail pool renamed for release, containing assets with slower observation saturation behavior.
