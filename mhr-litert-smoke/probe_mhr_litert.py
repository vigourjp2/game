from __future__ import annotations
import argparse, hashlib, inspect, json, time, traceback
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
        from pymomentum.backend import skel_state_backend

        class MHRBackendF32FK(torch.nn.Module):
            """Official MHR math; only global FK precision changes from fp64 to fp32."""
            def __init__(self, inner):
                super().__init__()
                self.inner = inner

            def forward(self, identity, params, face):
                identity = identity.expand(params.shape[0], -1)
                coeffs = torch.cat([identity, face], dim=1)
                rest_pose = self.inner.character_torch.blend_shape.forward(coeffs)
                padding = torch.zeros(
                    params.shape[0],
                    self.inner.get_num_face_expression_blendshapes()
                    + self.inner.get_num_identity_blendshapes(),
                ).to(params)
                joints = self.inner.character_torch.model_parameters_to_joint_parameters(
                    torch.concatenate((params, padding), axis=1)
                )
                skeleton = self.inner.character_torch.skeleton
                local = skeleton.joint_parameters_to_local_skeleton_state(joints)
                prefix_parts = list(
                    skeleton.pmi.split(
                        split_size=skeleton._pmi_buffer_sizes,
                        dim=1,
                    )
                )
                skel, _ = skel_state_backend.global_skel_state_from_local_skel_state_impl(
                    local,
                    prefix_parts,
                    save_intermediate_results=False,
                    use_double_precision=False,
                )
                unposed = rest_pose + self.inner.pose_correctives_model.forward(
                    joint_parameters=joints
                )
                verts = self.inner.character_torch.skin_points(
                    skel_state=skel, rest_vertex_positions=unposed
                )
                return verts, skel

        report.update(
            torch_version=torch.__version__,
            torchao_version=getattr(torchao, '__version__', 'unknown'),
            litert_torch_file=str(Path(litert_torch.__file__).resolve()),
        )
        assets = args.mhr_root / 'assets'
        if not (assets / 'lod1.fbx').is_file() and (assets / 'assets' / 'lod1.fbx').is_file():
            assets = assets / 'assets'
        report['assets_dir'] = str(assets)
        report['official_torchscript_exists'] = (assets / 'mhr_model.pt').is_file()

        t0 = time.time()
        official = MHR.from_files(
            folder=assets, device=torch.device('cpu'), lod=1, wants_pose_correctives=True
        ).eval()
        f32_model = MHRBackendF32FK(official).eval()
        report['mhr_load_ok'] = True
        report['mhr_load_seconds'] = time.time() - t0
        skeleton = official.character_torch.skeleton
        report['skeleton_type'] = str(type(skeleton))
        report['pmi_shape'] = list(skeleton.pmi.shape)
        report['pmi_buffer_sizes'] = list(skeleton._pmi_buffer_sizes)
        report['backend_impl_signature'] = str(
            inspect.signature(skel_state_backend.global_skel_state_from_local_skel_state_impl)
        )
        report['f32_fk_path'] = 'skel_state_backend.global_skel_state_from_local_skel_state_impl'

        torch.manual_seed(1234)
        inputs = (
            torch.randn(1, 45, dtype=torch.float32) * 0.25,
            torch.randn(1, 204, dtype=torch.float32) * 0.08,
            torch.randn(1, 72, dtype=torch.float32) * 0.15,
        )
        with torch.no_grad():
            official_v, official_s = official(*inputs)
            f32_v, f32_s = f32_model(*inputs)
        report['pytorch_output_shapes'] = [list(f32_v.shape), list(f32_s.shape)]
        report['pytorch_output_dtypes'] = [str(f32_v.dtype), str(f32_s.dtype)]
        report['f32_vs_official_vertices_max_abs'] = float((f32_v-official_v).abs().max())
        report['f32_vs_official_vertices_mean_abs'] = float((f32_v-official_v).abs().mean())
        report['f32_vs_official_skeleton_max_abs'] = float((f32_s-official_s).abs().max())
        report['f32_vs_official_skeleton_mean_abs'] = float((f32_s-official_s).abs().mean())

        t0 = time.time()
        ep = torch.export.export(f32_model, inputs)
        report['torch_export_ok'] = True
        report['torch_export_seconds'] = time.time() - t0
        report['torch_export_graph_nodes'] = sum(1 for _ in ep.graph.nodes)
        f64_nodes = []
        for node in ep.graph.nodes:
            val = node.meta.get('val')
            if getattr(val, 'dtype', None) == torch.float64:
                f64_nodes.append({'op': node.op, 'target': str(node.target), 'name': node.name})
        report['torch_export_f64_nodes'] = f64_nodes

        t0 = time.time()
        edge = litert_torch.convert(f32_model, inputs)
        report['litert_convert_ok'] = True
        report['litert_convert_seconds'] = time.time() - t0
        tflite_path = args.output_dir / 'mhr_lod1_f32fk.tflite'
        edge.export(str(tflite_path))
        report['tflite_bytes'] = tflite_path.stat().st_size
        report['tflite_sha256'] = sha256(tflite_path)

        litert_out = edge(*inputs)
        if not isinstance(litert_out, (tuple, list)) or len(litert_out) != 2:
            raise RuntimeError(f'Expected two LiteRT outputs, got {type(litert_out)!r}')
        lv, ls = np.asarray(litert_out[0]), np.asarray(litert_out[1])
        fv, fs = f32_v.detach().cpu().numpy(), f32_s.detach().cpu().numpy()
        ov, os = official_v.detach().cpu().numpy(), official_s.detach().cpu().numpy()
        report['litert_output_shapes'] = [list(lv.shape), list(ls.shape)]
        report['litert_vs_f32_vertices_max_abs'] = float(np.max(np.abs(lv-fv)))
        report['litert_vs_f32_skeleton_max_abs'] = float(np.max(np.abs(ls-fs)))
        report['litert_vs_official_vertices_max_abs'] = float(np.max(np.abs(lv-ov)))
        report['litert_vs_official_skeleton_max_abs'] = float(np.max(np.abs(ls-os)))
        report['passed'] = (
            not f64_nodes
            and report['f32_vs_official_vertices_max_abs'] < 0.001
            and report['litert_vs_official_vertices_max_abs'] < 0.001
            and report['litert_vs_official_skeleton_max_abs'] < 0.001
        )
    except Exception as exc:
        report['passed'] = False
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()

    (args.output_dir/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='traceback'},indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
