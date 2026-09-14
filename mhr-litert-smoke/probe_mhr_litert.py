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
        from mhr.utils import SparseLinear, batch6DFromXYZ
        from pymomentum import skel_state

        def bake_sparse_linears(module: torch.nn.Module) -> int:
            count = 0
            for name, child in list(module.named_children()):
                if isinstance(child, SparseLinear):
                    shape = tuple(int(x) for x in child.sparse_shape)
                    dense = torch.zeros(shape, dtype=child.sparse_weight.dtype)
                    dense[child.sparse_indices[0], child.sparse_indices[1]] = child.sparse_weight.detach()
                    linear = torch.nn.Linear(shape[1], shape[0], bias=child.bias is not None)
                    with torch.no_grad():
                        linear.weight.copy_(dense)
                        if child.bias is not None:
                            linear.bias.copy_(child.bias.detach())
                    setattr(module, name, linear.eval())
                    count += 1
                else:
                    count += bake_sparse_linears(child)
            return count

        class AndroidMHR(torch.nn.Module):
            """Official MHR inference math, rewritten only to avoid unsupported mutations."""
            def __init__(self, inner):
                super().__init__()
                self.inner = inner
                skeleton = inner.character_torch.skeleton
                parts = list(skeleton.pmi.split(split_size=skeleton._pmi_buffer_sizes, dim=1))
                self.num_joints = int(skeleton.joint_translation_offsets.shape[0])
                self.levels = len(parts)
                for i, part in enumerate(parts):
                    source = part[0].long().clone()
                    target = part[1].long().clone()
                    selector = torch.zeros(self.num_joints, source.numel(), dtype=torch.float32)
                    for k, joint in enumerate(source.tolist()):
                        selector[joint, k] = 1.0
                    self.register_buffer(f'source_{i}', source)
                    self.register_buffer(f'target_{i}', target)
                    self.register_buffer(f'selector_{i}', selector)
                    self.register_buffer(f'mask_{i}', (selector.sum(dim=1) > 0).view(1, self.num_joints, 1))

                lbs = inner.character_torch.linear_blend_skinning
                vertex_count = int(lbs.num_vertices)
                max_influences = 4
                skin_idx = torch.zeros(vertex_count, max_influences, dtype=torch.long)
                skin_w = torch.zeros(vertex_count, max_influences, dtype=torch.float32)
                slots = [0] * vertex_count
                for vertex, joint, weight in zip(
                    lbs.vert_indices_flattened.tolist(),
                    lbs.skin_indices_flattened.tolist(),
                    lbs.skin_weights_flattened.tolist(),
                ):
                    slot = slots[vertex]
                    skin_idx[vertex, slot] = joint
                    skin_w[vertex, slot] = weight
                    slots[vertex] += 1
                if max(slots) > max_influences or min(slots) < 1:
                    raise RuntimeError(f'Unexpected skin influence counts: {min(slots)}..{max(slots)}')
                self.register_buffer('skin_idx', skin_idx)
                self.register_buffer('skin_w', skin_w)
                self.register_buffer('inverse_bind_pose', lbs.inverse_bind_pose.clone())
                self.register_buffer('pose_neutral', torch.tensor([1., 0., 0., 0., 1., 0.]).view(1, 1, 6))

            def forward(self, identity, params, face):
                identity = identity.expand(params.shape[0], -1)
                rest_pose = self.inner.character_torch.blend_shape.forward(torch.cat([identity, face], dim=1))
                padding = torch.zeros(
                    params.shape[0],
                    self.inner.get_num_face_expression_blendshapes() + self.inner.get_num_identity_blendshapes(),
                ).to(params)
                joints = self.inner.character_torch.model_parameters_to_joint_parameters(
                    torch.cat((params, padding), dim=1)
                )

                skeleton = self.inner.character_torch.skeleton
                global_state = skeleton.joint_parameters_to_local_skeleton_state(joints)
                for i in range(self.levels):
                    source = getattr(self, f'source_{i}')
                    target = getattr(self, f'target_{i}')
                    product = skel_state.multiply(
                        global_state.index_select(-2, target),
                        global_state.index_select(-2, source),
                    )
                    updates = torch.einsum('jk,bkd->bjd', getattr(self, f'selector_{i}'), product)
                    global_state = torch.where(getattr(self, f'mask_{i}'), updates, global_state)

                euler = joints.reshape(joints.shape[0], -1, 7)[:, 2:, 3:6]
                pose_features = (batch6DFromXYZ(euler) - self.pose_neutral).flatten(1, 2)
                offsets = self.inner.pose_correctives_model.pose_dirs_predictor(pose_features).reshape(
                    pose_features.shape[0], -1, 3
                )
                unposed = rest_pose + offsets

                inverse_bind = self.inverse_bind_pose
                while inverse_bind.ndim < global_state.ndim:
                    inverse_bind = inverse_bind.unsqueeze(0)
                joint_state = skel_state.multiply(global_state, inverse_bind)
                vertices = torch.zeros_like(unposed)
                for k in range(4):
                    states = joint_state.index_select(-2, self.skin_idx[:, k])
                    transformed = skel_state.transform_points(states, unposed)
                    vertices = vertices + transformed * self.skin_w[:, k][None, :, None]
                return vertices, global_state, unposed

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
        official = MHR.from_files(folder=assets, device=torch.device('cpu'), lod=1, wants_pose_correctives=True).eval()
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
            identity = inputs[0].expand(inputs[1].shape[0], -1)
            official_rest = official.character_torch.blend_shape.forward(
                torch.cat([identity, inputs[2]], dim=1)
            )
            padding = torch.zeros(
                inputs[1].shape[0],
                official.get_num_face_expression_blendshapes() + official.get_num_identity_blendshapes(),
            ).to(inputs[1])
            official_joints = official.character_torch.model_parameters_to_joint_parameters(
                torch.cat((inputs[1], padding), dim=1)
            )
            official_unposed = official_rest + official.pose_correctives_model.forward(
                joint_parameters=official_joints
            )

        report['baked_sparse_linears'] = bake_sparse_linears(official.pose_correctives_model)
        converted_model = AndroidMHR(official).eval()
        report['android_rewrite'] = 'fp32_fk + baked_sparse_linear + functional_pose_features + fixed4_lbs'
        report['body_package_outputs'] = ['vertices', 'skeleton', 'unposed_vertices']

        with torch.no_grad():
            converted_v, converted_s, converted_u = converted_model(*inputs)
        report['pytorch_output_shapes'] = [
            list(converted_v.shape), list(converted_s.shape), list(converted_u.shape)
        ]
        report['pytorch_output_dtypes'] = [
            str(converted_v.dtype), str(converted_s.dtype), str(converted_u.dtype)
        ]
        report['converted_vs_official_vertices_max_abs'] = float((converted_v - official_v).abs().max())
        report['converted_vs_official_vertices_mean_abs'] = float((converted_v - official_v).abs().mean())
        report['converted_vs_official_skeleton_max_abs'] = float((converted_s - official_s).abs().max())
        report['converted_vs_official_skeleton_mean_abs'] = float((converted_s - official_s).abs().mean())
        report['converted_vs_official_unposed_max_abs'] = float((converted_u - official_unposed).abs().max())
        report['converted_vs_official_unposed_mean_abs'] = float((converted_u - official_unposed).abs().mean())

        t0 = time.time()
        ep = torch.export.export(converted_model, inputs)
        report['torch_export_ok'] = True
        report['torch_export_seconds'] = time.time() - t0
        report['torch_export_graph_nodes'] = sum(1 for _ in ep.graph.nodes)
        f64_nodes = []
        mutation_nodes = []
        for node in ep.graph.nodes:
            target = str(node.target)
            if getattr(node.meta.get('val'), 'dtype', None) == torch.float64:
                f64_nodes.append({'op': node.op, 'target': target, 'name': node.name})
            low = target.lower()
            if any(x in low for x in ('scatter', 'index_copy', 'index_put', 'index_add', 'copy_')):
                mutation_nodes.append({'op': node.op, 'target': target, 'name': node.name})
        report['torch_export_f64_nodes'] = f64_nodes
        report['torch_export_mutation_nodes'] = mutation_nodes

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
        if not isinstance(litert_out, (tuple, list)) or len(litert_out) != 3:
            raise RuntimeError(f'Expected three LiteRT outputs, got {type(litert_out)!r}')
        lv, ls, lu = (
            np.asarray(litert_out[0]),
            np.asarray(litert_out[1]),
            np.asarray(litert_out[2]),
        )
        cv, cs, cu = (
            converted_v.detach().cpu().numpy(),
            converted_s.detach().cpu().numpy(),
            converted_u.detach().cpu().numpy(),
        )
        ov, os, ou = (
            official_v.detach().cpu().numpy(),
            official_s.detach().cpu().numpy(),
            official_unposed.detach().cpu().numpy(),
        )
        report['litert_output_shapes'] = [list(lv.shape), list(ls.shape), list(lu.shape)]
        report['litert_vs_converted_vertices_max_abs'] = float(np.max(np.abs(lv - cv)))
        report['litert_vs_converted_skeleton_max_abs'] = float(np.max(np.abs(ls - cs)))
        report['litert_vs_converted_unposed_max_abs'] = float(np.max(np.abs(lu - cu)))
        report['litert_vs_official_vertices_max_abs'] = float(np.max(np.abs(lv - ov)))
        report['litert_vs_official_skeleton_max_abs'] = float(np.max(np.abs(ls - os)))
        report['litert_vs_official_unposed_max_abs'] = float(np.max(np.abs(lu - ou)))
        report['passed'] = (
            not f64_nodes
            and not mutation_nodes
            and report['converted_vs_official_vertices_max_abs'] < 0.001
            and report['converted_vs_official_unposed_max_abs'] < 0.001
            and report['litert_vs_official_vertices_max_abs'] < 0.001
            and report['litert_vs_official_skeleton_max_abs'] < 0.001
            and report['litert_vs_official_unposed_max_abs'] < 0.001
        )
    except Exception as exc:
        report['passed'] = False
        report['error'] = repr(exc)
        report['traceback'] = traceback.format_exc()

    (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'traceback'}, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
