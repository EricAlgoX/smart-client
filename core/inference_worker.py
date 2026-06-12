"""内嵌推理工作线程 — 从 image_queue 取图，调用引擎推理，结果放入 result_queue"""

import time
import queue
from utils.logger import logger
from PySide6.QtCore import QThread
from engine.manager import engine_manager
from utils.profiler import profiler


class InferenceWorker(QThread):
    """后台推理线程"""

    def __init__(self, input_queue, output_queue, confidence=0.3, nms=0.5, skip_frames=0):
        super().__init__()
        self.q = input_queue
        self.out_q = output_queue
        self.confidence = confidence
        self.nms = nms
        self.skip_frames = skip_frames  # 每 N 帧跳过推理，直接透传
        self._running = True

    @profiler.measure("inference")
    def _do_inference(self, image, path):
        start = time.time()
        detections = engine_manager.detect(image, self.confidence, self.nms)
        elapsed = time.time() - start
        if elapsed > 0.05:
            logger.debug(f"[性能] 推理: {elapsed*1000:.1f}ms, 检测到 {len(detections)} 个目标")
        return image, detections, path

    def run(self):
        frame_idx = 0
        last_details = []  # 缓存上一次检测结果，跳过帧时复用

        while self._running:
            try:
                item = self.q.get(timeout=0.05)
            except queue.Empty:
                continue

            image, path = item

            if image is None:
                self.out_q.put((image, [], path))
                self.q.task_done()
                continue

            frame_idx += 1

            # skip_frames > 0 时，跳过部分帧的推理，但复用上一次检测结果（避免闪烁）
            if self.skip_frames > 0 and (frame_idx % (self.skip_frames + 1)) != 0:
                self.out_q.put((image, last_details, path))
                self.q.task_done()
                continue

            try:
                image, details, path = self._do_inference(image, path)
                # 只在检测到目标时更新缓存（空结果不覆盖，避免检测框闪烁）
                if details:
                    last_details = details
                self.out_q.put((image, last_details, path))
            except Exception as e:
                logger.error(f"[InferenceWorker] 推理异常: {e}")
                self.out_q.put((image, last_details, path))

            self.q.task_done()

    def stop(self):
        self._running = False
        self.wait(2000)
