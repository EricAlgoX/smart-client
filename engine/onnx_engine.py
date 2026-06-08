"""ONNX Runtime 推理引擎"""

import cv2
import numpy as np
from typing import List, Dict
from engine.base import BaseEngine
from utils.logger import logger


class OnnxEngine(BaseEngine):
    """基于 ONNX Runtime 的推理引擎，支持 YOLO 系列模型"""

    def __init__(self):
        self._session = None
        self._config = {}
        self._loaded = False
        self._input_name = None
        self._input_size = (640, 640)

    def load(self, config: dict) -> bool:
        """
        加载 ONNX 模型
        config 示例:
        {
            "model_path": "models/yolov8n.onnx",
            "input_size": [640, 640],
            "class_names": ["person", "car"],
            "provider": "CPUExecutionProvider"
        }
        """
        try:
            import onnxruntime as ort
        except ImportError:
            logger.error("[OnnxEngine] onnxruntime 未安装，请执行: pip install onnxruntime")
            return False

        model_path = config.get("model_path", "")
        if not model_path:
            logger.error("[OnnxEngine] 未指定 model_path")
            return False

        provider = config.get("provider", "CPUExecutionProvider")
        self._input_size = tuple(config.get("input_size", [640, 640]))
        self._config = config

        try:
            self._session = ort.InferenceSession(model_path, providers=[provider])
            self._input_name = self._session.get_inputs()[0].name
            self._loaded = True
            logger.info(f"[OnnxEngine] 已加载: {model_path} (provider={provider})")
            return True
        except Exception as e:
            logger.error(f"[OnnxEngine] 加载失败: {e}")
            return False

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5) -> List[Dict]:
        if not self._loaded or image is None:
            return []

        orig_h, orig_w = image.shape[:2]
        input_w, input_h = self._input_size
        class_names = self._config.get("class_names", [])

        # 前处理：resize + normalize + transpose
        img = cv2.resize(image, (input_w, input_h))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC → CHW
        img = np.expand_dims(img, axis=0)    # add batch dim

        # 推理
        try:
            outputs = self._session.run(None, {self._input_name: img})
        except Exception as e:
            logger.error(f"[OnnxEngine] 推理失败: {e}")
            return []

        # 后处理
        return self._postprocess(outputs, orig_w, orig_h, confidence, nms, class_names)

    def _postprocess(self, outputs, orig_w, orig_h, conf_thresh, nms_thresh, class_names):
        """YOLO 后处理（兼容 YOLOv5/v8/v11 输出格式）"""
        details = []

        preds = outputs[0]  # (1, 84, 8400) 或 (1, 8400, 84)

        if preds.ndim == 3:
            preds = preds[0]  # → (84, 8400) 或 (8400, 84)

        # YOLO11: (84, 8400) → 转置为 (8400, 84)
        # YOLOv8: (8400, 84) → 不需要转置
        if preds.shape[0] < preds.shape[1]:
            preds = preds.T  # → (8400, 84)

        # 分离坐标和类别分数
        # 前 4 列: cx, cy, w, h（YOLO cxcywh 格式）
        # 后 80 列: 类别分数
        cx = preds[:, 0]
        cy = preds[:, 1]
        w = preds[:, 2]
        h = preds[:, 3]
        class_scores = preds[:, 4:]

        # 每个预测的最大类别分数
        max_scores = np.max(class_scores, axis=1)
        cls_ids = np.argmax(class_scores, axis=1)

        # 置信度过滤
        mask = max_scores >= conf_thresh
        cx, cy, w, h = cx[mask], cy[mask], w[mask], h[mask]
        max_scores = max_scores[mask]
        cls_ids = cls_ids[mask]

        if len(max_scores) == 0:
            return []

        # cxcywh → xyxy
        scale_x = orig_w / self._input_size[0]
        scale_y = orig_h / self._input_size[1]

        x1 = (cx - w / 2) * scale_x
        y1 = (cy - h / 2) * scale_y
        x2 = (cx + w / 2) * scale_x
        y2 = (cy + h / 2) * scale_y

        # 裁剪到图像范围
        x1 = np.clip(x1, 0, orig_w).astype(int)
        y1 = np.clip(y1, 0, orig_h).astype(int)
        x2 = np.clip(x2, 0, orig_w).astype(int)
        y2 = np.clip(y2, 0, orig_h).astype(int)

        boxes = np.stack([x1, y1, x2, y2], axis=1).tolist()
        scores = max_scores.tolist()

        # NMS
        indices = cv2.dnn.NMSBoxes(boxes, scores, conf_thresh, nms_thresh)
        if len(indices) > 0:
            for i in indices.flatten():
                cls_name = class_names[int(cls_ids[i])] if int(cls_ids[i]) < len(class_names) else str(int(cls_ids[i]))
                xmin, ymin, xmax, ymax = int(boxes[i][0]), int(boxes[i][1]), int(boxes[i][2]), int(boxes[i][3])
                details.append({
                    'class': cls_name,
                    'score': f"{scores[i]:.2f}",
                    'bbox': (xmin, ymin, xmax, ymax),
                    'coordinate': [[xmin, ymin], [xmax, ymax]],
                })

        return details

    def unload(self):
        self._session = None
        self._loaded = False
        self._input_name = None
        logger.info("[OnnxEngine] 已卸载")

    @property
    def name(self) -> str:
        return "ONNX"

    @property
    def is_loaded(self) -> bool:
        return self._loaded
