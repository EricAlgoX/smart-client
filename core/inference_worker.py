"""内嵌推理工作线程 — 从 image_queue 取图，调用引擎推理，结果放入 result_queue"""

import time
import queue
from utils.logger import logger
from PySide6.QtCore import QThread
from core.queue import result_queue
from engine.manager import engine_manager
from utils.profiler import profiler


class InferenceWorker(QThread):
    """后台推理线程，与原 StartClient 接口兼容"""

    def __init__(self, input_queue, confidence=0.3, nms=0.5):
        super().__init__()
        self.q = input_queue
        self.confidence = confidence
        self.nms = nms
        self._running = True

    @profiler.measure("inference")
    def _do_inference(self, image, path):
        """执行推理并返回结果"""
        start = time.time()

        detections = engine_manager.detect(image, self.confidence, self.nms)

        elapsed = time.time() - start
        if elapsed > 0.05:
            logger.debug(f"[性能] 推理: {elapsed*1000:.1f}ms, 检测到 {len(detections)} 个目标")

        return image, detections, path

    def run(self):
        while self._running:
            try:
                item = self.q.get(timeout=0.05)
            except queue.Empty:
                continue

            image, path = item

            if image is None:
                result_queue.put((image, [], path))
                self.q.task_done()
                continue

            try:
                image, details, path = self._do_inference(image, path)
                result_queue.put((image, details, path))
            except Exception as e:
                logger.error(f"[InferenceWorker] 推理异常: {e}")
                result_queue.put((image, [], path))

            self.q.task_done()

    def stop(self):
        self._running = False
        self.wait(2000)
