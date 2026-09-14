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
        from mhr.utils import SparseLinear
        from pymomentum import skel_state

        def bake_sparse_linears(module: torch.nn.Module) -> int:
            count = 0
            for name, child in list(module.named_children()):
                if isinstance(child, SparseLinear):
                    shape = tuple(int(x) for x in child.sparse_shape)
                    dense = torch.zeros(
                        shape,
                        dtype=child.sparse_weight.dtype,
                        device=child.sparse_weight.device,
                    )
                    dense[
                        child.sparse_indices[0], child.sparse_indices[1]
                    ] = child.sparse_weight.detach()
                    linear = torch.nn.Linear(
                        shape[1], shape[0], bias=child.bias is not None
                    )
                    with torch.no_grad():
                        linear.weight.copy_(dense)
                        if child.bias is not None:
                            linear.bias.copy_(child.bias.detach())
                    setattr(module, name, linear.eval())
                    count += 1
                else:
                    count += bake_sparse_linears(child)
            return count

        class MHRScatterFreeF32(torch.nn.Module):
            """Official MHR math with fp32 FK and scatter-free inference updates."""
            def __init__(self, inner):
                super().__init__()
                self.inner = inner
                skeleton = inner.character_torch.skeleton
                parts = list(
                    skeleton.pmi.split(
                        split_size=skeleton._pmi_buffer_sizes,
                        dim=1,
                    )
                )
                self.num_joints = int(skeleton.joint_translation_offsets.shape[0])
                self.levels = len(parts)
                for i, part in enumerate(parts):
                    source = part[0].long().clone()
                    target = part[1].long().clone()
                    selector = torch.zeros(
                        self.num_joints, source.numel(), dtype=torch.float32
                    )
                    for k, joint in enumerate(source.tolist()):
                        selector[joint, k] = 1.0
                    mask = (selector.sum(dim=1) > 0).view(1, self.num_joints, 1)
                    self.register_buffer(f'source_{i}', source)
                    self.register_buffer(f'target_{i}', target)
                    self.register_buffer(f'selector_{i}', selector)
                    self.register_buffer(f'mask_{i}', mask)

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
                    torch.cat((params, padding), dim=1)
                )
                skeleton = self.inner.character_torch.skeleton
                global_state = skeleton.joint_parameters_to_local_skeleton_state(joints)
                for i in range(self.levels):
                    source = getattr(self, f'source_{i}')
                    target = getattr(self, f'target_{i}')
                    selector = getattr(self, f'selector_{i}')
                    mask = getattr(self, f'mask_{i}')
                    product = skel_state.multiply(
                        global_state.index_select(-2, target),
                        global_state.index_select(-2, source),
                    )
                    updates = torch.einsum('jk,bkd->bjd', selector, product)
                    global_state = torch.where(mask, updates, global_state)
                unposed = rest_pose + self.inner.pose_correctives_model.forward(
                    joint_parameters=joints
                )
                vertices = self.inner.character_torch.skin_points(
                    skel_state=global_state,
                    rest_vertex_positions=unposed,
                )
                return vertices, global_state

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
            folder=assets,
            device=torch.device('cpu'),
            lod=1,
            wants_pose_correctives=True,
        ).eval()
        report['mhr_load_ok'] = True
        report['mhr_load_seconds'] = time.time() - t0

        torch.manual_seed(1234)
        inputs = (
            torch.randn(1, 45, dtype=torch.float32) * 0.25,
            torch.randn(1, 204, dtype=torch.float32) * 0.08,
            torch.randn(1, 72, dtype=torch.float32) * 0.15,
        )
        with torch.no_grad():
            official_v, official_s = official(*inputs)

        report['baked_sparse_linears'] = bake_sparse_linears(
            official.pose_correctives_model
        )
        converted_model = MHRScatterFreeF32(official).eval()
        report['f32_fk_path'] = 'scatter_free_gather_matmul_where'

        with torch.no_grad():
            converted_v, converted_s = converted_model(*inputs)
        report['pytorch_output_shapes'] = [
            list(converted_v.shape), list(converted_s.shape)
        ]
        report['pytorch_output_dtypes'] = [
            str(converted_v.dtype), str(converted_s.dtype)
        ]
        report['converted_vs_official_vertices_max_abs'] = float(
            (converted_v - official_v).abs().max()
        )
        report['converted_vs_official_vertices_mean_abs'] = float(
            (converted_v - official_v).abs().mean()
        )
        report['converted_vs_official_skeleton_max_abs'] = float(
            (converted_s - official_s).abs().max()
        )
        report['converted_vs_official_skeleton_mean_abs'] = float(
            (converted_s - official_s).abs().mean()
        )

        t0 = time.time()
        ep = torch.export.export(converted_model, inputs)
        report['torch_export_ok'] = True
        report['torch_export_seconds'] = time.time() - t0
        report['torch_export_graph_nodes'] = sum(1 for _ in ep.graph.nodes)
        f64_nodes = []
        scatter_nodes = []
        for node in ep.graph.nodes:
            val = node.meta.get('val')
            target = str(node.target)
            if getattr(val, 'dtype', None) == torch.float64:
                f64_nodes.append({'op': node.op, 'target': target, 'name': node.name})
            lower_target = target.lower()
            if any(x in lower_target for x in ('scatter', 'index_copy', 'index_put')):
                scatter_nodes.append({'op': node.op, 'target': target, 'name': node.name})
        report['torch_export_f64_nodes'] = f64_nodes
        report['torch_export_scatter_nodes'] = scatter_nodes

        t0 = time.time()
        edge = litert_torch.convert(converted_model, inputs)
        report['litert_convert_ok'] = True
        report['litert_convert_seconds'] = time.time() - t0
        tflite_path = args.output_dir / 'mhr_lod1_android.tflite'
        edge.export(str(tflite_path))
        report['tflite_bytes'] = tflite_path.stat().st_size
        report['tflite_sha256'] = sha256(tflite_path)

        t0 = time.time()
        litert_out = edge(*inputs)
        report['litert_inference_ok'] = True
        report['litert_inference_seconds'] = time.time() - t0
        if not isinstance(litert_out, (tuple, list)) or len(litert_out) != 2:
            raise RuntimeError(
                f'Expected two LiteRT outputs, got {type(litert_out)!r}'
            )
        lv, ls = np.asarray(litert_out[0]), np.asarray(litert_out[1])
        cv = converted_v.detach().cpu().numpy()
        cs = converted_s.detach().cpu().numpy()
        ov = official_v.detach().cpu().numpy()
        os = official_s.detach().cpu().numpy()
        report['litert_output_shapes'] = [list(lv.shape), list(ls.shape)]
        report['litert_vs_converted_vertices_max_abs'] = float(
            np.max(np.abs(lv - cv))
        )
        report['litert_vs_converted_skeleton_max_abs'] = float(
            np.max(np.abs(ls - cs))
        )
        report['litert_vs_official_vertices_max_abs'] = float(
            np.max(np.abs(lv - ov))
        )
        report['litert_vs_official_skeleton_max_abs'] = float(
            np.max(np.abs(ls - os))
        )
        report['passed'] = (
            not f64_nodes
            and not scatter_nodes
            and report['converted_vs_official_vertices_max_abs'] < 0.001
            and report['litert_vs_official_vertices_max_abs'] < 0.001
            and report['litert_vs_official_skeleton_max_abs'] < 0.001
        )
    except Exception as exc:
        report['passed'] = False
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()

    (args.output_dir / 'report.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8'
    )
    print(json.dumps({k: v for k, v in report.items() if k != 'traceback'}, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
