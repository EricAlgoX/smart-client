import threading

# ui/image_viewer.py
from core.visualizer import Visualizer

import time
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
import cv2
import numpy as np
from sympy.geometry.plane import y
from PIL import Image, ImageDraw as PILImageDraw, ImageFont
from core.queue import result_queue



from pickle import FALSE
import requests
import cv2
import queue
import base64
from PyQt5.QtCore import QThread, pyqtSignal
from utils.logger import logger

class StartClient(QThread):
    result_ready = pyqtSignal(object, list)  # result, frame, frame_name

    def __init__(
        self, 
        url,
        input_queue,

        nms,
        polygon,
        confidence,
        timeout_mins,
        max_detection = 100
    ):
        super().__init__()
        """
        组装推理API参数，供APIClient调用
        :param confidence: 置信度
        :param max_det: 最大检测数
        :param polygon: 多边形围栏点集（原图像素坐标）
        :param timeout: 超时时间（秒）
        """

        self.url = url
        self.q = input_queue
        self.nms = nms
        self.polygon = polygon,
        self.confidence = confidence,
        self.timeout_mins = timeout_mins,
        self.max_detection = max_detection

        self.viz = Visualizer()

        # 创建 Session
        self.session = requests.Session()
        self.session.headers.update({"Connection": "keep-alive"})  # 默认就会启用 Keep-Alive

    def postprocess(self, image_bgr, result, elapsed_time):
        image = image_bgr.copy()
        details = []

        detections =result.get("data", {}).get("detections", [])
        for det in detections:
            instance = {}

            class_name = det.get("class_name", "")
            bbox = det.get("bbox", {})
            score = det.get("score", "")
            
            x_cen = bbox.get("x_cen", 0)
            y_cen = bbox.get("y_cen", 0)
            width = bbox.get("width", 0)
            height = bbox.get("height", 0)

            xmin = int(x_cen - width / 2)
            ymin = int(y_cen - height / 2)
            xmax = int(x_cen + width / 2)
            ymax = int(y_cen + height / 2)
            
            instance['class'] = class_name
            instance['socre'] = f"{float(score):.2f}"
            instance['coordinate'] = [[xmin, ymin], [xmin, xmax]]
            instance['image'] = cv2.cvtColor(image_bgr[ymin:ymax, xmin:xmax, :], cv2.COLOR_BGR2RGB)

            image = self.viz.draw_boxes(image, xmin, ymin, xmax, ymax, class_name, score)

            details.append(instance)

        image = self.viz.draw_elapsed_time(image, elapsed_time)

        return image, details
        
    def run(self):
        while True:
            start = time.time()
            try:
                image = self.q.get(timeout=0.05)
            except queue.Empty:
                continue
            
            ret, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                print("JPG编码失败")
                continue

            image_base64 = base64.b64encode(buffer).decode('utf-8')

            payload = {
                'image': image_base64
                # 'nms': self.nms,
                # 'reset': False,
                # 'track_id': None,
                # 'polygon': self.polygon,
                # 'confidence': self.confidence,
                # 'timeout_mins': self.timeout_mins,
                # 'max_threshold': self.max_detection
            }

            # -------------------------
            #   带 Session 的 POST 请求 + 重试
            # -------------------------
            for attempt in range(2):  # 你的模型很快，最多重试1次即可
                try:
                    response = self.session.post(
                        self.url,
                        json=payload,
                        timeout=(1, 3)
                    )
                    response.raise_for_status()
                    break
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.ReadTimeout,
                        requests.exceptions.ConnectTimeout) as e:

                    print(f"[Client] 尝试 {attempt+1} 失败: {e}")

                    if attempt == 1:
                        # 两次都失败 → 用空结果
                        result_queue.put((image, []))
                        self.q.task_done()
                        continue
                    else:
                        time.sleep(0.1)  # 防止高频重连压垮服务
                except Exception as e:
                    print(f"[Client] 未知异常: {e}")
                    result_queue.put((image, []))
                    self.q.task_done()
                    continue
        
            # -------------------------
            # POST 成功
            # -------------------------
            try:
                data = response.json()
            except:
                data = []

            elapsed = time.time() - start
            image, details = self.postprocess(image, data, elapsed)

            result_queue.put((image, details))
            self.q.task_done()
            
            print("Client run thread id:", threading.get_ident())