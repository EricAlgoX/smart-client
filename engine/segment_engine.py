"""YOLO-Seg 分割引擎 — 支持实例分割（检测框 + mask）"""

import cv2
import numpy as np
from typing import List, Dict
from engine.base import BaseEngine
from utils.logger import logger


class SegmentEngine(BaseEngine):
    """YOLO-Seg 实例分割引擎（ONNX）"""

    def __init__(self):
        self._session = None
        self._loaded = False
        self._input_name = None
        self._input_size = (640, 640)
        self._config = {}

    def load(self, config: dict) -> bool:
        try:
            import onnxruntime as ort
        except ImportError:
            logger.error("[SegmentEngine] onnxruntime 未安装")
            return False

        model_path = config.get("model_path", "")
        if not model_path:
            logger.error("[SegmentEngine] 未指定 model_path")
            return False

        self._config = config
        self._input_size = tuple(config.get("input_size", [640, 640]))

        try:
            self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
            self._loaded = True
            logger.info(f"[SegmentEngine] 已加载: {model_path}")
            return True
        except Exception as e:
            logger.error(f"[SegmentEngine] 加载失败: {e}")
            return False

    def _letterbox(self, image, target_size):
        """Letterbox resize"""
        target_w, target_h = target_size
        h, w = image.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
        dx, dy = (target_w - new_w) // 2, (target_h - new_h) // 2
        canvas[dy:dy + new_h, dx:dx + new_w] = resized
        return canvas, scale, dx, dy

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5, **kwargs) -> List[Dict]:
        if not self._loaded or image is None:
            return []

        orig_h, orig_w = image.shape[:2]
        input_w, input_h = self._input_size
        class_names = self._config.get("class_names", [])

        # Letterbox 预处理
        img, scale, dx, dy = self._letterbox(image, (input_w, input_h))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        # 推理
        try:
            outputs = self._session.run(None, {self._input_name: img})
        except Exception as e:
            logger.error(f"[SegmentEngine] 推理失败: {e}")
            return []

        return self._postprocess(outputs, orig_w, orig_h, confidence, nms, class_names, scale, dx, dy)

    def _postprocess(self, outputs, orig_w, orig_h, conf_thresh, nms_thresh, class_names, scale, dx, dy):
        """YOLO-Seg 后处理：boxes + masks"""
        details = []

        # YOLO-Seg 输出:
        #   output0: [1, 4+num_classes+mask_dim, num_dets] — 检测 + mask 系数
        #   output1: [1, mask_dim, mask_h, mask_w]          — prototype masks
        det_output = outputs[0]  # [1, C, N]
        proto_output = outputs[1] if len(outputs) > 1 else None  # [1, mask_dim, MH, MW]

        if det_output.ndim == 3:
            det_output = det_output[0]  # [C, N]

        if det_output.shape[0] < det_output.shape[1]:
            det_output = det_output.T  # [N, C]

        num_cols = det_output.shape[1]
        # YOLO-Seg: 4 bbox + num_classes + mask_dim
        # 例：80类 + 32mask = 4+80+32 = 116列
        num_classes = len(class_names) if class_names else (num_cols - 4 - 32)
        mask_dim = num_cols - 4 - num_classes

        # 分离 bbox、class_scores、mask_coeffs
        cx = det_output[:, 0]
        cy = det_output[:, 1]
        w = det_output[:, 2]
        h = det_output[:, 3]
        class_scores = det_output[:, 4:4 + num_classes]
        mask_coeffs = det_output[:, 4 + num_classes:]  # [N, mask_dim]

        max_scores = np.max(class_scores, axis=1)
        cls_ids = np.argmax(class_scores, axis=1)

        # 置信度过滤
        mask = max_scores >= conf_thresh
        cx, cy, w, h = cx[mask], cy[mask], w[mask], h[mask]
        max_scores = max_scores[mask]
        cls_ids = cls_ids[mask]
        mask_coeffs = mask_coeffs[mask]

        if len(max_scores) == 0:
            return []

        # cxcywh → xyxy（letterbox 坐标）
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2

        # 还原到原图坐标
        x1 = (x1 - dx) / scale
        y1 = (y1 - dy) / scale
        x2 = (x2 - dx) / scale
        y2 = (y2 - dy) / scale

        x1 = np.clip(x1, 0, orig_w).astype(int)
        y1 = np.clip(y1, 0, orig_h).astype(int)
        x2 = np.clip(x2, 0, orig_w).astype(int)
        y2 = np.clip(y2, 0, orig_h).astype(int)

        boxes = np.stack([x1, y1, x2, y2], axis=1).tolist()
        scores = max_scores.tolist()

        # NMS
        indices = cv2.dnn.NMSBoxes(boxes, scores, conf_thresh, nms_thresh)
        if len(indices) == 0:
            return []

        indices = indices.flatten()

        # 生成 masks
        segment_masks = []
        if proto_output is not None and len(mask_coeffs) > 0:
            segment_masks = self._process_masks(
                proto_output, mask_coeffs, indices, orig_w, orig_h, scale, dx, dy
            )

        # 组装结果
        for idx, i in enumerate(indices):
            cls_idx = int(cls_ids[i])
            cls_name = class_names[cls_idx] if cls_idx < len(class_names) else str(cls_idx)
            xmin, ymin, xmax, ymax = int(boxes[i][0]), int(boxes[i][1]), int(boxes[i][2]), int(boxes[i][3])

            det = {
                'class': cls_name,
                'score': f"{scores[i]:.2f}",
                'bbox': (xmin, ymin, xmax, ymax),
                'coordinate': [[xmin, ymin], [xmax, ymax]],
            }

            # 附带 mask
            if idx < len(segment_masks):
                det['mask'] = segment_masks[idx]

            details.append(det)

        logger.info(f"[SegmentEngine] 检测到 {len(details)} 个目标, mask_dim={mask_dim}")
        return details

    def _process_masks(self, proto_output, mask_coeffs, indices, orig_w, orig_h, scale, dx, dy):
        """从 prototype masks + 系数生成每个实例的分割 mask"""
        masks = []

        # proto: [1, mask_dim, MH, MW] → [mask_dim, MH, MW]
        proto = proto_output[0] if proto_output.ndim == 4 else proto_output
        mask_dim, mask_h, mask_w = proto.shape

        for i in indices:
            coeffs = mask_coeffs[i]  # [mask_dim]
            # 线性组合 prototype masks
            mask = np.tensordot(coeffs, proto, axes=([0], [0]))  # [MH, MW]
            mask = 1 / (1 + np.exp(-mask))  # sigmoid

            # 缩放到原图尺寸
            mask = cv2.resize(mask, (mask_w * 4, mask_h * 4), interpolation=cv2.INTER_LINEAR)

            # 裁剪到 bbox 区域（letterbox 坐标）
            lb_h, lb_w = mask_h * 4, mask_w * 4
            x1 = int((0 - dx) / scale * lb_w / (orig_w if orig_w else 1))
            y1 = int((0 - dy) / scale * lb_h / (orig_h if orig_h else 1))

            # 简化：直接缩放到原图尺寸
            mask = cv2.resize(mask, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)

            # 二值化
            mask = (mask > 0.5).astype(np.uint8) * 255
            masks.append(mask)

        return masks

    def unload(self):
        self._session = None
        self._loaded = False
        logger.info("[SegmentEngine] 已卸载")

    @property
    def name(self) -> str:
        return "Segment"

    @property
    def is_loaded(self) -> bool:
        return self._loaded
