"""Build Chassie's open-vocabulary camera model (YOLOE-11s prompt-free, 416 px) as ONNX.

Torch and ultralytics are needed only for this one-time export and never enter
Chassie's venv. Run with uv, which makes a throwaway environment:

    uv run --no-project -p 3.12 --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --with torch --with torchvision --with ultralytics --with onnx --with onnxslim \
        python scripts/export_yoloe.py

The graph is cut after the class head: it returns boxes, the best score and the best
class per candidate, so ~85 KB (not ~155 MB) leaves the GPU per frame. Mask outputs are
pruned. Ultralytics YOLOE weights are AGPL-3.0.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paths import DATA  # noqa: E402
TARGET = DATA / '.chassie' / 'vision-models'
SIZE = 416


def main():
    import onnx
    from onnx import TensorProto, helper, numpy_helper
    from ultralytics import YOLOE
    TARGET.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        os.chdir(work)  # Ultralytics downloads weights into the working directory.
        model = YOLOE('yoloe-11s-seg-pf.pt')
        names = [model.names[i] for i in sorted(model.names)]
        exported = Path(model.export(format='onnx', imgsz=SIZE, simplify=True, opset=17))
        graph_model = onnx.load(exported)
        graph = graph_model.graph
        classes = len(names)
        anchors = [d.dim_value for d in graph.output[0].type.tensor_type.shape.dim][2]
        for name, value in (('box_s', 0), ('box_e', 4), ('cls_s', 4), ('cls_e', 4 + classes), ('ax1', 1)):
            graph.initializer.append(numpy_helper.from_array(np.array([value], dtype=np.int64), name))
        graph.node.extend([
            helper.make_node('Slice', ['output0', 'box_s', 'box_e', 'ax1'], ['boxes']),
            helper.make_node('Slice', ['output0', 'cls_s', 'cls_e', 'ax1'], ['cls_scores']),
            helper.make_node('ReduceMax', ['cls_scores'], ['score'], axes=[1], keepdims=0),
            helper.make_node('ArgMax', ['cls_scores'], ['cls'], axis=1, keepdims=0),
        ])
        del graph.output[:]
        graph.output.extend([helper.make_tensor_value_info('boxes', TensorProto.FLOAT, [1, 4, anchors]),
                             helper.make_tensor_value_info('score', TensorProto.FLOAT, [1, anchors]),
                             helper.make_tensor_value_info('cls', TensorProto.INT64, [1, anchors])])
        full = Path(work) / 'full.onnx'
        onnx.save(graph_model, full)
        onnx.utils.extract_model(str(full), str(TARGET / f'yoloe-11s-pf-{SIZE}.onnx'), ['images'], ['boxes', 'score', 'cls'])
    (TARGET / 'yoloe-11s-pf.names.json').write_text(json.dumps(names), encoding='utf-8')
    print(f'Installed: yoloe-11s-pf-{SIZE}.onnx ({len(names)} labels)')


if __name__ == '__main__':
    main()
