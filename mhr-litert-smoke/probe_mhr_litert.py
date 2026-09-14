from __future__ import annotations
import argparse, hashlib, json, time, traceback
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def err_text(exc: Exception) -> str:
    return repr(exc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mhr-root', type=Path, required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    try:
        import sys
        sys.path.insert(0, str(args.mhr_root))
        import numpy as np
        import torch
        import torchao
        import litert_torch
        from mhr.mhr import MHR

        class VerticesOnly(torch.nn.Module):
            def __init__(self, inner):
                super().__init__()
                self.inner = inner
            def forward(self, identity, params, face):
                vertices, _ = self.inner(identity, params, face)
                return vertices.to(torch.float32)

        class SkeletonOnly(torch.nn.Module):
            def __init__(self, inner):
                super().__init__()
                self.inner = inner
            def forward(self, identity, params, face):
                _, skeleton = self.inner(identity, params, face)
                return skeleton.to(torch.float32)

        report.update(
            torch_version=torch.__version__,
            torchao_version=getattr(torchao, '__version__', 'unknown'),
            litert_torch_file=str(Path(litert_torch.__file__).resolve()),
        )
        assets = args.mhr_root / 'assets'
        if not (assets / 'lod1.fbx').is_file() and (assets / 'assets' / 'lod1.fbx').is_file():
            assets = assets / 'assets'
        report['assets_dir'] = str(assets)
        report['lod1_fbx_exists'] = (assets / 'lod1.fbx').is_file()

        t0 = time.time()
        model = MHR.from_files(
            folder=assets,
            device=torch.device('cpu'),
            lod=1,
            wants_pose_correctives=True,
        ).eval()
        report['mhr_load_ok'] = True
        report['mhr_load_seconds'] = time.time() - t0

        inputs = (
            torch.zeros(1, 45, dtype=torch.float32),
            torch.zeros(1, 204, dtype=torch.float32),
            torch.zeros(1, 72, dtype=torch.float32),
        )
        with torch.no_grad():
            pt_vertices, pt_skeleton = model(*inputs)
        report['pytorch_output_shapes'] = [list(pt_vertices.shape), list(pt_skeleton.shape)]
        report['pytorch_output_dtypes'] = [str(pt_vertices.dtype), str(pt_skeleton.dtype)]

        t0 = time.time()
        ep = torch.export.export(model, inputs)
        report['torch_export_ok'] = True
        report['torch_export_seconds'] = time.time() - t0
        report['torch_export_graph_nodes'] = sum(1 for _ in ep.graph.nodes)
        f64_nodes = []
        for node in ep.graph.nodes:
            val = node.meta.get('val')
            dtype = getattr(val, 'dtype', None)
            if dtype == torch.float64:
                f64_nodes.append({'op': node.op, 'target': str(node.target), 'name': node.name})
        report['torch_export_f64_nodes'] = f64_nodes

        try:
            t0 = time.time()
            full_edge = litert_torch.convert(model, inputs)
            report['full_litert_convert_ok'] = True
            report['full_litert_convert_seconds'] = time.time() - t0
            full_path = args.output_dir / 'mhr_lod1_full.tflite'
            full_edge.export(str(full_path))
            report['full_tflite_bytes'] = full_path.stat().st_size
            report['full_tflite_sha256'] = sha256(full_path)
        except Exception as exc:
            report['full_litert_convert_ok'] = False
            report['full_litert_error'] = err_text(exc)

        vertices_model = VerticesOnly(model).eval()
        t0 = time.time()
        vertices_ep = torch.export.export(vertices_model, inputs)
        report['vertices_export_ok'] = True
        report['vertices_export_graph_nodes'] = sum(1 for _ in vertices_ep.graph.nodes)
        vertices_edge = litert_torch.convert(vertices_model, inputs)
        report['vertices_litert_convert_ok'] = True
        report['vertices_litert_convert_seconds'] = time.time() - t0
        vertices_path = args.output_dir / 'mhr_lod1_vertices.tflite'
        vertices_edge.export(str(vertices_path))
        report['vertices_tflite_bytes'] = vertices_path.stat().st_size
        report['vertices_tflite_sha256'] = sha256(vertices_path)
        vertex_out = np.asarray(vertices_edge(*inputs))
        pv = pt_vertices.detach().cpu().numpy()
        report['vertices_litert_output_shape'] = list(vertex_out.shape)
        report['vertices_max_abs_error'] = float(np.max(np.abs(vertex_out - pv)))

        try:
            skeleton_model = SkeletonOnly(model).eval()
            skeleton_ep = torch.export.export(skeleton_model, inputs)
            report['skeleton_export_ok'] = True
            report['skeleton_export_graph_nodes'] = sum(1 for _ in skeleton_ep.graph.nodes)
            t0 = time.time()
            skeleton_edge = litert_torch.convert(skeleton_model, inputs)
            report['skeleton_litert_convert_ok'] = True
            report['skeleton_litert_convert_seconds'] = time.time() - t0
            skeleton_path = args.output_dir / 'mhr_lod1_skeleton.tflite'
            skeleton_edge.export(str(skeleton_path))
            report['skeleton_tflite_bytes'] = skeleton_path.stat().st_size
            report['skeleton_tflite_sha256'] = sha256(skeleton_path)
            skeleton_out = np.asarray(skeleton_edge(*inputs))
            ps = pt_skeleton.detach().cpu().numpy()
            report['skeleton_litert_output_shape'] = list(skeleton_out.shape)
            report['skeleton_max_abs_error'] = float(np.max(np.abs(skeleton_out - ps)))
        except Exception as exc:
            report['skeleton_litert_convert_ok'] = False
            report['skeleton_litert_error'] = err_text(exc)

        report['geometry_path_passed'] = bool(report.get('vertices_litert_convert_ok'))
        report['full_model_passed'] = bool(report.get('full_litert_convert_ok'))
        report['passed'] = report['geometry_path_passed']
    except Exception as exc:
        report['passed'] = False
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()

    (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'traceback'}, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
