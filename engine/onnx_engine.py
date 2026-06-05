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
        """YOLO 标准后处理"""
        details = []

        # outputs[0] shape 通常为 (1, num_dets, 4+num_classes) 或 (1, 4+num_classes, num_dets)
        preds = outputs[0]

        if preds.ndim == 3:
            preds = preds[0]  # 去掉 batch dim

        # 如果 shape 是 (num_classes+4, num_dets)，转置
        if preds.shape[0] < preds.shape[1]:
            preds = preds.T

        boxes = []
        scores = []
        class_ids = []

        for det in preds:
            # 前 4 个是坐标 (x_center, y_center, w, h) 或 (x1, y1, x2, y2)
            x1, y1, x2, y2 = det[:4]
            class_scores = det[4:]
            cls_id = int(np.argmax(class_scores))
            score = float(class_scores[cls_id])

            if score < conf_thresh:
                continue

            # 坐标映射回原图
            scale_x = orig_w / self._input_size[0]
            scale_y = orig_h / self._input_size[1]

            # 如果是 xywh 格式，转换为 xyxy
            if x2 > x1 and y2 > y1:
                # 已经是 xyxy
                xmin = int(max(0, x1 * scale_x))
                ymin = int(max(0, y1 * scale_y))
                xmax = int(min(orig_w, x2 * scale_x))
                ymax = int(min(orig_h, y2 * scale_y))
            else:
                # xywh 格式
                cx, cy, w, h = x1, y1, x2, y2
                xmin = int(max(0, (cx - w / 2) * scale_x))
                ymin = int(max(0, (cy - h / 2) * scale_y))
                xmax = int(min(orig_w, (cx + w / 2) * scale_x))
                ymax = int(min(orig_h, (cy + h / 2) * scale_y))

            boxes.append([xmin, ymin, xmax, ymax])
            scores.append(score)
            class_ids.append(cls_id)

        # NMS
        if boxes:
            indices = cv2.dnn.NMSBoxes(boxes, scores, conf_thresh, nms_thresh)
            if len(indices) > 0:
                for i in indices.flatten():
                    cls_name = class_names[class_ids[i]] if class_ids[i] < len(class_names) else str(class_ids[i])
                    xmin, ymin, xmax, ymax = boxes[i]
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
