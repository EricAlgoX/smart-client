import os
import time
import json
import queue
import threading
import traceback

import cv2
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QImage, QPixmap

# 假定 logger 已存在
# from base.logger import logger

class ImageConverter(QThread):
    """
    后台线程：把 BGR numpy frame 转换为 QPixmap（并做必要的 resize）
    输入通过 input_queue（thread-safe），输出通过信号发回主线程
    """
    pixmap_ready = pyqtSignal(QImage, object)  # (pixmap, details)

    def __init__(self, input_queue: queue.Queue, target_size_getter, fps_limit=30):
        super().__init__()
        self.input_queue = input_queue
        self._running = True
        self.target_size_getter = target_size_getter  # function to get current QLabel size (QSize)
        self.fps_limit = fps_limit
        self.min_interval = 1.0 / fps_limit if fps_limit > 0 else 0

    def run(self):
        while self._running:
            try:
                item = self.input_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            
            try:
                frame, details = item
                # 安全检查
                if frame is None:
                    continue

                # 转换 BGR->RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                target_size = self.target_size_getter()  # 调用函数获取 QSize
                if target_size is not None and not target_size.isEmpty():
                    rgb = cv2.resize(rgb, (target_size.width(), target_size.height()), interpolation=cv2.INTER_AREA)

                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

                # 发送给主线程
                self.pixmap_ready.emit(qimg, details)
            except Exception:
                # logger.exception("ImageConverter 处理帧出错")
                traceback.print_exc()
            print("ImageConverter run thread id:", threading.get_ident())
    def stop(self):
        self._running = False
        self.wait(timeout=500)