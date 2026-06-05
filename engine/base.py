"""抽象推理引擎基类"""

from abc import ABC, abstractmethod
import numpy as np
from typing import List, Dict


class BaseEngine(ABC):
    """所有推理引擎的基类"""

    @abstractmethod
    def load(self, config: dict) -> bool:
        """加载模型，返回是否成功"""
        ...

    @abstractmethod
    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5) -> List[Dict]:
        """
        推理接口
        :param image: BGR numpy 图像
        :param confidence: 置信度阈值
        :param nms: NMS 阈值
        :return: [{'class': str, 'score': str, 'bbox': (xmin,ymin,xmax,ymax), 'coordinate': [[x1,y1],[x2,y2]]}]
        """
        ...

    @abstractmethod
    def unload(self):
        """卸载模型，释放资源"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称"""
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        ...
