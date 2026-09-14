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
            """Windows-worker-equivalent canonical MHR, rewritten for LiteRT-supported ops."""
            def __init__(self, inner):
                super().__init__()
                self.inner = inner
                body_mask = torch.zeros(204, dtype=torch.float32)
                body_mask[130:204] = 1.0
                self.register_buffer('body_mask', body_mask)

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

            def forward(self, identity, source_params, face):
                identity = identity.expand(source_params.shape[0], -1)
                params = source_params * self.body_mask.unsqueeze(0)
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
                corrected = rest_pose + offsets

                inverse_bind = self.inverse_bind_pose
                while inverse_bind.ndim < global_state.ndim:
                    inverse_bind = inverse_bind.unsqueeze(0)
                joint_state = skel_state.multiply(global_state, inverse_bind)
                vertices = torch.zeros_like(corrected)
                for k in range(4):
                    states = joint_state.index_select(-2, self.skin_idx[:, k])
                    transformed = skel_state.transform_points(states, corrected)
                    vertices = vertices + transformed * self.skin_w[:, k][None, :, None]
                # .mhrb third output is the pre-corrective/pre-skin rest shape.
                return vertices, global_state, rest_pose

        report.update(
            torch_version=torch.__version__,
            torchao_version=getattr(torchao, '__version__', 'unknown'),
            litert_torch_file=str(Path(litert_torch.__file__).resolve()),
        )
        assets = args.mhr_root / 'assets'
        if not (assets / 'lod1.fbx').is_file() and (assets / 'assets' / 'lod1.fbx').is_file():
            assets = assets / 'assets'
        scripted_path = assets / 'mhr_model.pt'
        report['assets_dir'] = str(assets)
        report['official_torchscript_exists'] = scripted_path.is_file()
        report['official_torchscript_sha256'] = sha256(scripted_path)

        t0 = time.time()
        official = MHR.from_files(folder=assets, device=torch.device('cpu'), lod=1, wants_pose_correctives=True).eval()
        scripted = torch.jit.load(str(scripted_path), map_location='cpu').eval()
        report['mhr_load_ok'] = True
        report['mhr_load_seconds'] = time.time() - t0

        transform = scripted.get_parameter_transform()[:, :204].reshape(127, 7, 204)
        rotations = transform[:, 3:6, :].abs().sum(dim=(0, 1))
        translations_or_scale = transform[:, [0, 1, 2, 6], :].abs().sum(dim=(0, 1))
        scaling = scripted.character_torch.parameter_transform.scaling_parameters[:204].bool()
        scripted_body_mask = scaling | ((rotations == 0) & (translations_or_scale != 0))
        for index, name in enumerate(list(scripted.get_parameter_names())[:204]):
            if name.startswith('root_'):
                scripted_body_mask[index] = False
        body_indices = torch.nonzero(scripted_body_mask).flatten().tolist()
        report['worker_body_parameter_indices'] = body_indices
        if body_indices != list(range(130, 204)):
            raise RuntimeError(f'Worker body mask changed: {body_indices}')

        torch.manual_seed(1234)
        inputs = (
            torch.randn(1, 45, dtype=torch.float32) * 0.25,
            torch.randn(1, 204, dtype=torch.float32) * 0.08,
            torch.randn(1, 72, dtype=torch.float32) * 0.15,
        )
        canonical_params = inputs[1] * scripted_body_mask.unsqueeze(0)
        with torch.no_grad():
            worker_v, worker_s = scripted(inputs[0], canonical_params, inputs[2], True)
            worker_u = scripted.character_torch.blend_shape(inputs[0]) + scripted.face_expressions_model(inputs[2])

        report['baked_sparse_linears'] = bake_sparse_linears(official.pose_correctives_model)
        converted_model = AndroidMHR(official).eval()
        report['android_rewrite'] = 'worker_body_mask + fp32_fk + baked_sparse_linear + functional_pose_features + fixed4_lbs'
        report['body_package_outputs'] = ['vertices', 'skeleton', 'unposed_vertices_pre_corrective']

        with torch.no_grad():
            converted_v, converted_s, converted_u = converted_model(*inputs)
        report['pytorch_output_shapes'] = [list(converted_v.shape), list(converted_s.shape), list(converted_u.shape)]
        report['pytorch_output_dtypes'] = [str(converted_v.dtype), str(converted_s.dtype), str(converted_u.dtype)]
        report['converted_vs_worker_vertices_max_abs'] = float((converted_v - worker_v).abs().max())
        report['converted_vs_worker_vertices_mean_abs'] = float((converted_v - worker_v).abs().mean())
        report['converted_vs_worker_skeleton_max_abs'] = float((converted_s - worker_s).abs().max())
        report['converted_vs_worker_skeleton_mean_abs'] = float((converted_s - worker_s).abs().mean())
        report['converted_vs_worker_unposed_max_abs'] = float((converted_u - worker_u).abs().max())
        report['converted_vs_worker_unposed_mean_abs'] = float((converted_u - worker_u).abs().mean())

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
        lv, ls, lu = np.asarray(litert_out[0]), np.asarray(litert_out[1]), np.asarray(litert_out[2])
        cv, cs, cu = converted_v.detach().cpu().numpy(), converted_s.detach().cpu().numpy(), converted_u.detach().cpu().numpy()
        wv, ws, wu = worker_v.detach().cpu().numpy(), worker_s.detach().cpu().numpy(), worker_u.detach().cpu().numpy()
        report['litert_output_shapes'] = [list(lv.shape), list(ls.shape), list(lu.shape)]
        report['litert_vs_converted_vertices_max_abs'] = float(np.max(np.abs(lv - cv)))
        report['litert_vs_converted_skeleton_max_abs'] = float(np.max(np.abs(ls - cs)))
        report['litert_vs_converted_unposed_max_abs'] = float(np.max(np.abs(lu - cu)))
        report['litert_vs_worker_vertices_max_abs'] = float(np.max(np.abs(lv - wv)))
        report['litert_vs_worker_skeleton_max_abs'] = float(np.max(np.abs(ls - ws)))
        report['litert_vs_worker_unposed_max_abs'] = float(np.max(np.abs(lu - wu)))
        report['passed'] = (
            not f64_nodes
            and not mutation_nodes
            and report['converted_vs_worker_vertices_max_abs'] < 0.001
            and report['converted_vs_worker_skeleton_max_abs'] < 0.001
            and report['converted_vs_worker_unposed_max_abs'] < 0.001
            and report['litert_vs_worker_vertices_max_abs'] < 0.001
            and report['litert_vs_worker_skeleton_max_abs'] < 0.001
            and report['litert_vs_worker_unposed_max_abs'] < 0.001
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
