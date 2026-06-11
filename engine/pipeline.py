"""推理流水线 — 支持多模型串联推理"""

import os
import numpy as np
from typing import List, Dict
from engine.base import BaseEngine
from engine.onnx_engine import OnnxEngine
from utils.logger import logger


class Pipeline:
    """场景推理流水线：按 step 串联多个引擎"""

    def __init__(self, scene_dir: str, config: dict):
        self.scene_dir = scene_dir
        self.config = config
        self.engines: Dict[int, BaseEngine] = {}
        self.steps: List[dict] = config.get("pipeline", [])
        self._loaded = False

    def load(self) -> bool:
        """加载流水线中所有模型"""
        for step_cfg in self.steps:
            step = step_cfg["step"]
            model_file = step_cfg["model"]
            model_path = os.path.join(self.scene_dir, model_file)
            input_size = tuple(step_cfg.get("input_size", [640, 640]))
            class_names = step_cfg.get("class_names", [])

            # 判断引擎类型
            role = step_cfg.get("role", "detection")
            if role == "plate_ocr":
                from engine.plate_ocr_engine import PlateOcrEngine
                engine = PlateOcrEngine()
            elif role == "segmentation":
                from engine.segment_engine import SegmentEngine
                engine = SegmentEngine()
            else:
                engine = OnnxEngine()

            ok = engine.load({
                "model_path": model_path,
                "input_size": list(input_size),
                "class_names": class_names,
            })
            if not ok:
                logger.error(f"[Pipeline] Step {step} 加载失败: {model_file}")
                return False

            self.engines[step] = engine
            logger.info(f"[Pipeline] Step {step} 已加载: {model_file} ({len(class_names)} 类)")

        self._loaded = True
        return True

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5) -> List[Dict]:
        """执行流水线推理"""
        if not self._loaded or image is None:
            return []

        all_details = []
        # 存储每一步的裁剪区域，供后续 step 使用
        step_crops: Dict[str, List[dict]] = {}

        for step_cfg in self.steps:
            step = step_cfg["step"]
            engine = self.engines.get(step)
            if engine is None:
                continue

            role = step_cfg.get("role", "detection")
            input_from = step_cfg.get("input_from", "")
            # 每步可独立配置置信度，否则用全局值
            step_conf = step_cfg.get("confidence", confidence)

            # 获取裁剪区域，支持按类别过滤
            crop_filter = step_cfg.get("crop_filter", [])
            all_crops = step_crops.get(input_from, []) if input_from else []
            if crop_filter:
                crop_regions = [r for r in all_crops if r.get("class", "") in crop_filter]
            else:
                crop_regions = all_crops

            if crop_regions:
                # 从上一步的检测结果中裁剪子图
                logger.info(f"[Pipeline] Step {step}: 从 {input_from} 裁剪, 共 {len(crop_regions)} 个区域")
                for region in crop_regions:
                    x1, y1, x2, y2 = region["bbox"]
                    sub_image = image[y1:y2, x1:x2]
                    if sub_image.size == 0:
                        continue
                    # 传递上游类别信息（如单行/双行牌）给 OCR 引擎
                    region_class = region.get("class", "")
                    sub_details = engine.detect(sub_image, step_conf, nms, parent_class=region_class)
                    # 坐标映射回原图
                    for det in sub_details:
                        bx1, by1, bx2, by2 = det["bbox"]
                        det["bbox"] = (bx1 + x1, by1 + y1, bx2 + x1, by2 + y1)
                        det["coordinate"] = [
                            [bx1 + x1, by1 + y1],
                            [bx2 + x1, by2 + y1],
                        ]
                    all_details.extend(sub_details)
                    # 记录本步裁剪结果
                    step_crops[f"step{step}_crop"] = [
                        {"bbox": det["bbox"]} for det in sub_details
                    ]
            else:
                # 没有上一步裁剪区域 → 降级到整图推理
                logger.info(f"[Pipeline] Step {step}: 整图推理 (无 {input_from} 裁剪区域)")
                details = engine.detect(image, step_conf, nms)
                logger.info(f"[Pipeline] Step {step}: 检测到 {len(details)} 个目标")
                for d in details[:5]:
                    logger.info(f"  → class={d.get('class')} score={d.get('score')} bbox={d.get('bbox')}")
                all_details.extend(details)
                # 记录检测区域（含类别名）供后续 step 裁剪
                step_crops[f"step{step}_crop"] = [
                    {"bbox": d["bbox"], "class": d.get("class", "")} for d in details
                ]

        return all_details

    def unload(self):
        for engine in self.engines.values():
            engine.unload()
        self.engines.clear()
        self._loaded = False
        logger.info("[Pipeline] 已卸载所有引擎")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def name(self) -> str:
        return self.config.get("name", "Pipeline")
