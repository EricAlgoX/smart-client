"""模拟推理引擎 — 用于开发调试和销售演示"""

import random
import numpy as np
from typing import List, Dict
from engine.base import BaseEngine
from utils.logger import logger


class MockEngine(BaseEngine):
    """返回随机检测框的模拟引擎，不需要真实模型"""

    def __init__(self):
        self._loaded = False
        self._config = {}
        self._class_names = ["person"]
        self._frame_count = 0

    def load(self, config: dict) -> bool:
        self._config = config
        self._class_names = config.get("class_names", ["person"])
        self._loaded = True
        logger.info(f"[MockEngine] 已加载: {self._class_names}")
        return True

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5) -> List[Dict]:
        if not self._loaded or image is None:
            return []

        h, w = image.shape[:2]
        self._frame_count += 1

        # 每 3 帧才生成检测结果（模拟不是每帧都有目标）
        if self._frame_count % 3 != 0:
            return []

        # 随机生成 1~3 个检测框
        num_dets = random.randint(1, 3)
        details = []

        for _ in range(num_dets):
            cls_name = random.choice(self._class_names)
            score = random.uniform(confidence, 0.99)

            # 随机框，但保证在图像范围内
            box_w = random.randint(int(w * 0.05), int(w * 0.25))
            box_h = random.randint(int(h * 0.1), int(h * 0.4))
            xmin = random.randint(0, max(0, w - box_w))
            ymin = random.randint(0, max(0, h - box_h))
            xmax = min(w, xmin + box_w)
            ymax = min(h, ymin + box_h)

            details.append({
                'class': cls_name,
                'score': f"{score:.2f}",
                'bbox': (xmin, ymin, xmax, ymax),
                'coordinate': [[xmin, ymin], [xmax, ymax]],
            })

        return details

    def unload(self):
        self._loaded = False
        self._frame_count = 0
        logger.info("[MockEngine] 已卸载")

    @property
    def name(self) -> str:
        return "Mock"

    @property
    def is_loaded(self) -> bool:
        return self._loaded
