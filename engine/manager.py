"""引擎管理器 — 按场景加载推理流水线"""

import os
import json
import numpy as np
from typing import List, Dict, Optional
from engine.pipeline import Pipeline
from utils.logger import logger


class EngineManager:
    """管理场景推理流水线的生命周期"""

    def __init__(self):
        self._pipeline: Optional[Pipeline] = None
        self._current_scene: Optional[str] = None
        self._base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

    def load_scene(self, scene_name: str) -> bool:
        """
        加载指定场景
        :param scene_name: 场景文件夹名（如 "smart_parking"）
        """
        scene_dir = os.path.join(self._base_dir, scene_name)
        config_path = os.path.join(scene_dir, "config.json")

        if not os.path.isdir(scene_dir):
            logger.error(f"[EngineManager] 场景文件夹不存在: {scene_dir}")
            return False

        if not os.path.exists(config_path):
            logger.error(f"[EngineManager] 场景配置不存在: {config_path}")
            return False

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"[EngineManager] 读取配置失败: {e}")
            return False

        # 卸载旧场景
        self.unload()

        # 加载新场景
        pipeline = Pipeline(scene_dir, config)
        success = pipeline.load()

        if success:
            self._pipeline = pipeline
            self._current_scene = scene_name
            logger.info(f"[EngineManager] 场景已加载: {config.get('name', scene_name)}")
        else:
            logger.error(f"[EngineManager] 场景加载失败: {scene_name}")

        return success

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5) -> List[Dict]:
        """使用当前场景进行推理"""
        if self._pipeline is None or not self._pipeline.is_loaded:
            return []
        return self._pipeline.detect(image, confidence, nms)

    def unload(self):
        """卸载当前场景"""
        if self._pipeline is not None:
            self._pipeline.unload()
            self._pipeline = None
            self._current_scene = None

    @property
    def current_scene(self) -> Optional[str]:
        return self._current_scene

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None and self._pipeline.is_loaded


# 全局单例
engine_manager = EngineManager()
