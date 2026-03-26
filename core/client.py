import cv2
import time
import queue
import base64
import requests
import threading
from utils.logger import logger
from PyQt5.QtCore import QThread
from core.queue import result_queue
from core.visualizer import Visualizer
from utils.profiler import profiler

class StartClient(QThread):
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
        self.polygon = polygon
        self.confidence = confidence
        self.timeout_mins = timeout_mins
        self.max_detection = max_detection

        self.viz = Visualizer()

        # 创建 Session
        self.session = requests.Session()
        self.session.headers.update({"Connection": "keep-alive"})  # 默认就会启用 Keep-Alive

    @profiler.measure("postprocess")
    def postprocess(self, image_bgr, result, elapsed_time):
        # 不复制图像，不绘制，只提取数据
        details = []

        detections = result.get("data", {}).get("detections", [])
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
            instance['score'] = f"{float(score):.2f}"
            instance['coordinate'] = [[xmin, ymin], [xmax, ymax]]
            instance['bbox'] = (xmin, ymin, xmax, ymax)

            details.append(instance)

        # 返回原始图像和检测结果，绘制交给 converter
        return image_bgr, details, elapsed_time
        
    def run(self):
        while True:
            start = time.time()
            try:
                item = self.q.get(timeout=0.05)
            except queue.Empty:
                continue

            image, path = item

            # 缩小图像以加快推理速度
            h, w = image.shape[:2]
            # if max(h, w) > 640:  # 如果图像太大，缩小到640
            #     scale = 640 / max(h, w)
            #     new_w, new_h = int(w * scale), int(h * scale)
            #     image_resized = cv2.resize(image, (new_w, new_h))
            # else:
            #     image_resized = image

            # 测量编码时间
            encode_start = time.time()
            ret, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 60])  # 从80降到60
            encode_time = (time.time() - encode_start) * 1000
            if encode_time > 10:
                logger.debug(f"[性能] JPG编码: {encode_time:.2f}ms")

            if not ret:
                logger.error("JPG编码失败")
                continue

            image_base64 = base64.b64encode(buffer).decode('utf-8')

            payload = {
                'image': image_base64
            }

            # 测量API请求时间
            for attempt in range(2):
                try:
                    api_start = time.time()
                    response = self.session.post(
                        self.url,
                        json=payload,
                        timeout=(2, 10)  # 连接超时2秒，读取超时10秒
                    )
                    api_time = (time.time() - api_start) * 1000
                    logger.debug(f"[性能] API请求: {api_time:.2f}ms")

                    response.raise_for_status()

                    try:
                        data = response.json()
                    except:
                        data = []

                    elapsed = time.time() - start
                    image, details, elapsed_time = self.postprocess(image, data, elapsed)

                    result_queue.put((image, details, path))
                    self.q.task_done()

                    break
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.ReadTimeout,
                        requests.exceptions.ConnectTimeout) as e:

                    logger.error(f"[Client] 尝试 {attempt+1} 失败: {e}")

                    if attempt == 1:
                        result_queue.put((image, [], path))
                        self.q.task_done()
                        continue
                    else:
                        time.sleep(0.1)
                except Exception as e:
                    logger.error(f"[Client] 未知异常: {e}")
                    result_queue.put((image, [], path))
                    self.q.task_done()
                    continue