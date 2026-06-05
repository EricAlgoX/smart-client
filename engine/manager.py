"""引擎管理器 — 统一管理推理引擎的加载、推理、卸载"""

import numpy as np
from typing import List, Dict, Optional
from engine.base import BaseEngine
from utils.logger import logger


class EngineManager:
    """管理所有推理引擎的生命周期"""

    def __init__(self):
        self._engines: Dict[str, BaseEngine] = {}  # {model_key: engine}
        self._current_model: Optional[str] = None

    def load_model(self, model_key: str, config: dict) -> bool:
        """
        加载指定模型
        :param model_key: 模型配置名（不含 .json）
        :param config: 模型配置 dict
        """
        # 如果已经加载了同一个模型，跳过
        if model_key in self._engines and self._engines[model_key].is_loaded:
            self._current_model = model_key
            return True

        engine_type = config.get("engine_type", "mock")

        if engine_type == "onnx":
            from engine.onnx_engine import OnnxEngine
            engine = OnnxEngine()
        else:
            from engine.mock_engine import MockEngine
            engine = MockEngine()

        success = engine.load(config)
        if success:
            self._engines[model_key] = engine
            self._current_model = model_key
            logger.info(f"[EngineManager] 已加载模型: {model_key} ({engine.name})")
        else:
            logger.error(f"[EngineManager] 加载模型失败: {model_key}")

        return success

    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5) -> List[Dict]:
        """使用当前模型进行推理"""
        if self._current_model is None or self._current_model not in self._engines:
            return []
        engine = self._engines[self._current_model]
        if not engine.is_loaded:
            return []
        return engine.detect(image, confidence, nms)

    def unload_model(self, model_key: str):
        """卸载指定模型"""
        if model_key in self._engines:
            self._engines[model_key].unload()
            del self._engines[model_key]
            if self._current_model == model_key:
                self._current_model = None

    def unload_all(self):
        """卸载所有模型"""
        for key in list(self._engines.keys()):
            self._engines[key].unload()
        self._engines.clear()
        self._current_model = None
        logger.info("[EngineManager] 已卸载所有模型")

    @property
    def current_model(self) -> Optional[str]:
        return self._current_model

    @property
    def is_loaded(self) -> bool:
        return self._current_model is not None and self._current_model in self._engines


# 全局单例
engine_manager = EngineManager()
