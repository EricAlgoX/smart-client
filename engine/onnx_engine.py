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

    def _letterbox(self, image, target_size):
        """Letterbox resize：保持宽高比 + 灰色填充（跟 ultralytics YOLO 一致）"""
        target_w, target_h = target_size
        h, w = image.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # 灰色画布
        canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
        # 居中粘贴
        dx, dy = (target_w - new_w) // 2, (target_h - new_h) // 2
        canvas[dy:dy + new_h, dx:dx + new_w] = resized

        return canvas, scale, dx, dy

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5, **kwargs) -> List[Dict]:
        if not self._loaded or image is None:
            return []

        orig_h, orig_w = image.shape[:2]
        input_w, input_h = self._input_size
        class_names = self._config.get("class_names", [])

        # 前处理：letterbox resize + normalize + transpose（跟 ultralytics YOLO 一致）
        img, scale, dx, dy = self._letterbox(image, (input_w, input_h))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC → CHW
        img = np.expand_dims(img, axis=0)    # add batch dim

        # 推理
        try:
            outputs = self._session.run(None, {self._input_name: img})
        except Exception as e:
            logger.error(f"[OnnxEngine] 推理失败: {e}")
            return []

        # 后处理（传入 letterbox 参数用于坐标还原）
        result = self._postprocess(outputs, orig_w, orig_h, confidence, nms, class_names, scale, dx, dy)
        logger.info(f"[OnnxEngine] 输入 {orig_w}x{orig_h}, conf={confidence}, nms={nms}, 检测到 {len(result)} 个")
        return result

    def _postprocess(self, outputs, orig_w, orig_h, conf_thresh, nms_thresh, class_names, scale=1.0, dx=0, dy=0):
        """YOLO 后处理（兼容 YOLOv5/v8/v11 输出格式，支持 letterbox 坐标还原）"""
        details = []

        preds = outputs[0]  # (1, N, 8400) 或 (1, 8400, N)

        if preds.ndim == 3:
            preds = preds[0]

        if preds.shape[0] < preds.shape[1]:
            preds = preds.T

        num_classes = preds.shape[1] - 4
        cx = preds[:, 0]
        cy = preds[:, 1]
        w = preds[:, 2]
        h = preds[:, 3]
        class_scores = preds[:, 4:]

        max_scores = np.max(class_scores, axis=1)
        cls_ids = np.argmax(class_scores, axis=1)

        total_preds = len(max_scores)
        mask = max_scores >= conf_thresh
        cx, cy, w, h = cx[mask], cy[mask], w[mask], h[mask]
        max_scores = max_scores[mask]
        cls_ids = cls_ids[mask]
        logger.info(f"[OnnxEngine] 总预测 {total_preds} 个, 置信度过滤后 {len(max_scores)} 个 (阈值={conf_thresh}), 类别数={num_classes}")

        if len(max_scores) == 0:
            return []

        # cxcywh → xyxy（在 letterbox 坐标系中）
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2

        # 还原到原图坐标：减去 padding 偏移，除以缩放比例
        x1 = (x1 - dx) / scale
        y1 = (y1 - dy) / scale
        x2 = (x2 - dx) / scale
        y2 = (y2 - dy) / scale

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
                cls_idx = int(cls_ids[i])
                cls_name = class_names[cls_idx] if cls_idx < len(class_names) else str(cls_idx)
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
