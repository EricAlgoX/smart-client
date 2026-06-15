"""车牌字符识别引擎 — ONNX 推理 + CTC 解码"""

import cv2
import numpy as np
from PIL import Image
from typing import List, Dict
from engine.base import BaseEngine
from utils.logger import logger


# 字符集：blank(0) + 78个字符
PLATE_CHARS = "#京沪津渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新学警港澳挂使领民航危0123456789ABCDEFGHJKLMNPQRSTUVWXYZ险品"


class PlateOcrEngine(BaseEngine):
    """车牌字符识别引擎"""

    def __init__(self):
        self._session = None
        self._loaded = False
        self._input_name = None
        self._input_size = (48, 168)  # (H, W)
        self._mean = 0.588
        self._std = 0.193
        # 构建字符映射表，跟参考代码 strLabelConverter 的 dict 对齐
        # 参考代码 dict: {'京':1, '沪':2, ...} → decode 时 alphabet[idx-1]
        # 所以 _char_map 需要: [占位, '京', '沪', ...]，index 0 不用
        self._char_map = [''] + list(PLATE_CHARS[1:])

    def load(self, config: dict) -> bool:
        try:
            import onnxruntime as ort
        except ImportError:
            logger.error("[PlateOcrEngine] onnxruntime 未安装")
            return False

        model_path = config.get("model_path", "")
        if not model_path:
            logger.error("[PlateOcrEngine] 未指定 model_path")
            return False

        self._config = config

        try:
            self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
            self._loaded = True
            logger.info(f"[PlateOcrEngine] 已加载: {model_path}")
            return True
        except Exception as e:
            logger.error(f"[PlateOcrEngine] 加载失败: {e}")
            return False

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5, **kwargs) -> List[Dict]:
        """对输入的车牌裁剪图进行 OCR，返回带 text 字段的检测结果"""
        if not self._loaded or image is None:
            return []

        parent_class = kwargs.get("parent_class", "")

        try:
            plate_text = self._recognize(image, parent_class)
        except Exception as e:
            logger.error(f"[PlateOcrEngine] OCR 失败: {e}")
            plate_text = ""

        if not plate_text:
            return []

        h, w = image.shape[:2]
        return [{
            "class": "plate",
            "score": "0.95",
            "bbox": (0, 0, w, h),
            "coordinate": [[0, 0], [w, h]],
            "text": plate_text,
        }]

    def _recognize(self, plate_img: np.ndarray, parent_class: str = "") -> str:
        """车牌图像 → 文字"""
        if plate_img is None or plate_img.size == 0:
            return ""
        # 确保 3 通道（去掉 alpha 通道）
        if len(plate_img.shape) == 2:
            plate_img = cv2.cvtColor(plate_img, cv2.COLOR_GRAY2BGR)
        elif len(plate_img.shape) == 3:
            if plate_img.shape[2] == 4:
                plate_img = plate_img[:, :, :3]
            elif plate_img.shape[2] == 1:
                plate_img = cv2.cvtColor(plate_img, cv2.COLOR_GRAY2BGR)

        logger.info(f"[PlateOcrEngine] 输入形状: {plate_img.shape}, 上游类别: {parent_class}")

        h, w = plate_img.shape[:2]
        # 双行牌处理：用上游检测模型的 class 判断（跟参考代码一致）
        # class=double_plate → 双行牌；class=plate → 单行牌
        is_double = "double" in parent_class
        logger.info(f"[PlateOcrEngine] 车牌裁剪: {w}x{h}, 双行牌={is_double}")

        if is_double:
            # 双行牌：上半部分和下半部分拼接
            img_upper = plate_img[0:int(5 / 12 * h), :]
            img_lower = plate_img[int(1 / 3 * h):, :]
            if img_upper.size > 0 and img_lower.size > 0:
                target_h = img_lower.shape[0]
                img_upper = cv2.resize(img_upper, (img_lower.shape[1], target_h))
                plate_img = np.hstack((img_upper, img_lower))

        # 预处理：resize 到 168×48（用 PIL，跟参考代码一致）
        plate_img = np.array(Image.fromarray(plate_img).resize((168, 48)))
        plate_img = plate_img.transpose([2, 0, 1]).astype(np.float32)
        plate_img = (plate_img / 255. - self._mean) / self._std
        plate_img = np.expand_dims(plate_img, 0)
        

        # ONNX 推理
        outputs = self._session.run(None, {self._input_name: plate_img})
        logits = outputs[0]  # [1, T, C]

        # CTC 解码
        pred_indices = np.argmax(logits, axis=2).astype(np.int64)  # [B, T]
        plate_text = self._ctc_decode(pred_indices)
        logger.info(f"[PlateOcrEngine] OCR 结果: '{plate_text}', 原始索引: {pred_indices.tolist()}")

        return plate_text

    def _ctc_decode(self, indices: np.ndarray) -> str:
        """CTC 贪心解码：去重复 + 去 blank"""
        chars = []
        prev_idx = 0
        for i, value in enumerate(indices[0]):
            if value != 0 and i != prev_idx:
                chars.append(self._char_map[value - 1])
            prev_idx = i
        return "".join(chars)

    def unload(self):
        self._session = None
        self._loaded = False
        logger.info("[PlateOcrEngine] 已卸载")

    @property
    def name(self) -> str:
        return "PlateOCR"

    @property
    def is_loaded(self) -> bool:
        return self._loaded
