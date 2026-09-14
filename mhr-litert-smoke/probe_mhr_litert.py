from __future__ import annotations
import argparse, hashlib, json, time, traceback
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


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

        t0 = time.time()
        ep = torch.export.export(model, inputs)
        report['torch_export_ok'] = True
        report['torch_export_seconds'] = time.time() - t0
        report['torch_export_graph_nodes'] = sum(1 for _ in ep.graph.nodes)

        t0 = time.time()
        edge_model = litert_torch.convert(model, inputs)
        report['litert_convert_ok'] = True
        report['litert_convert_seconds'] = time.time() - t0

        tflite = args.output_dir / 'mhr_lod1.tflite'
        edge_model.export(str(tflite))
        report['tflite_bytes'] = tflite.stat().st_size
        report['tflite_sha256'] = sha256(tflite)

        edge_out = edge_model(*inputs)
        ev, es = np.asarray(edge_out[0]), np.asarray(edge_out[1])
        pv, ps = pt_vertices.detach().cpu().numpy(), pt_skeleton.detach().cpu().numpy()
        report['litert_output_shapes'] = [list(ev.shape), list(es.shape)]
        report['vertices_max_abs_error'] = float(np.max(np.abs(ev - pv)))
        report['skeleton_max_abs_error'] = float(np.max(np.abs(es - ps)))
        report['passed'] = True
    except Exception as exc:
        report['passed'] = False
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()

    (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'traceback'}, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
