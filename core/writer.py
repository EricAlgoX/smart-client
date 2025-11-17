import os
import cv2
import xml.etree.ElementTree as ET
# import numpy as np

# def save_yolo_result(img_path, detections, class_map, save_dir):
#     """
#     保存为YOLO格式，每张图片一个txt文件。
#     :param img_path: 图片路径
#     :param detections: [{'class_name':..., 'bbox':..., 'score':...}, ...]
#     :param class_map: {'dog': 0, 'cat': 1, ...}
#     :param save_dir: 保存txt的目录
#     """
#     img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
#     h, w = img.shape[:2]
#     base = os.path.splitext(os.path.basename(img_path))[0]
#     txt_path = os.path.join(save_dir, base + ".txt")
#     with open(txt_path, "w") as f:
#         for det in detections:
#             class_id = class_map.get(det["class_name"], 0)
#             bbox = det["bbox"]
#             # 归一化
#             x_cen = bbox["x_cen"] / w
#             y_cen = bbox["y_cen"] / h
#             width = bbox["width"] / w
#             height = bbox["height"] / h
#             f.write(f"{class_id} {x_cen:.6f} {y_cen:.6f} {width:.6f} {height:.6f}\n")

# def save_img(img_path, image):
#     """
#     保存图片到指定路径。
#     :param img_path: 图片路径
#     :param image: 图片数据（numpy数组）
#     """
#     if not os.path.exists('images'):
#         os.makedirs('images')
#     img_path = os.path.join('images', os.path.basename(img_path))
#     cv2.imwrite(img_path, image)
import os
import cv2
import threading
import queue
import time

class ImageWriter:
    def __init__(self, save_dir="images", maxsize=200, flush_interval=0.0):
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)
        self.queue = queue.Queue(maxsize=maxsize)
        self.flush_interval = flush_interval
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def stop(self, drain=True, timeout=2.0):
        self._stop.set()
        if drain:
            self.queue.join()
        self._worker.join(timeout=timeout)

    def submit(self, img_path, image, drop_if_full=True):
        basename = os.path.basename(img_path)
        full_path = os.path.join(self.save_dir, basename)
        try:
            self.queue.put_nowait((full_path, image))
            return True
        except queue.Full:
            if drop_if_full:
                return False
            self.queue.put((full_path, image))
            return True

    def _run(self):
        while not self._stop.is_set() or not self.queue.empty():
            try:
                path, img = self.queue.get(timeout=0.1)
            except queue.Empty:
                if self.flush_interval:
                    time.sleep(self.flush_interval)
                continue
            try:
                cv2.imwrite(path, img)
            finally:
                self.queue.task_done()

class LabelWriter:
    def __init__(self, save_dir="annotations", maxsize=200, flush_interval=0.0):
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)
        self.queue = queue.Queue(maxsize=maxsize)
        self.flush_interval = flush_interval
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def stop(self, drain=True, timeout=2.0):
        self._stop.set()
        if drain:
            self.queue.join()
        self._worker.join(timeout=timeout)

    def submit(self, image_path, label, drop_if_full=True):
        # basename = os.path.basename(label_path)
        # full_path = os.path.join(self.save_dir, basename)
        try:
            self.queue.put_nowait((image_path, label))
            return True
        except queue.Full:
            if drop_if_full:
                return False
            self.queue.put((image_path, label))
            return True

    def _run(self):
        while not self._stop.is_set() or not self.queue.empty():
            try:
                path, label = self.queue.get(timeout=0.1)
            except queue.Empty:
                if self.flush_interval:
                    time.sleep(self.flush_interval)
                continue
            try:
                """
                保存为VOC格式，每张图片一个xml文件。
                :param img_path: 图片路径
                :param detections: [{'class_name':..., 'bbox':..., 'score':...}, ...]
                """
                img_folder = os.path.dirname(path)
                xml_folder = os.path.join(os.path.dirname(img_folder), "annotations")
                if not os.path.exists(xml_folder):
                    os.makedirs(xml_folder)

                image = cv2.imread(path)
                xml_path = os.path.join(xml_folder, os.path.basename(path).replace(".jpg", ".xml"))

                h, w, c = image.shape
                annotation = ET.Element("annotation")
                ET.SubElement(annotation, "folder").text = os.path.dirname(path)
                ET.SubElement(annotation, "filename").text = os.path.basename(path)
                size = ET.SubElement(annotation, "size")
                ET.SubElement(size, "width").text = str(w)
                ET.SubElement(size, "height").text = str(h)
                ET.SubElement(size, "depth").text = str(c)

                for det in label:
                    obj = ET.SubElement(annotation, "object")
                    ET.SubElement(obj, "name").text = det["class_name"]
                    ET.SubElement(obj, "pose").text = 'Unspecified'
                    ET.SubElement(obj, "truncated").text = '0'
                    ET.SubElement(obj, "occluded").text = '0'
                    ET.SubElement(obj, "difficult").text = '0'

                    bbox = det["bbox"]
                    x_cen, y_cen, width, height = bbox["x_cen"], bbox["y_cen"], bbox["width"], bbox["height"]
                    xmin = int(x_cen - width / 2)
                    ymin = int(y_cen - height / 2)
                    xmax = int(x_cen + width / 2)
                    ymax = int(y_cen + height / 2)
                    bndbox = ET.SubElement(obj, "bndbox")
                    ET.SubElement(bndbox, "xmin").text = str(int(xmin))
                    ET.SubElement(bndbox, "ymin").text = str(int(ymin))
                    ET.SubElement(bndbox, "xmax").text = str(int(xmax))
                    ET.SubElement(bndbox, "ymax").text = str(int(ymax))

                tree = ET.ElementTree(annotation)
                tree.write(xml_path, xml_declaration=True)
                
            finally:
                self.queue.task_done()   

    
# 批量保存
# core/result_saver.py

# from utils.file_utils import save_yolo_result, save_voc_result

# class ResultSaver:
#     def __init__(self):
#         pass

#     def save_labels_batch(self, results, save_dir, format="YOLO", class_map=None):
#         """
#         批量保存推理结果为label文件
#         :param results: {img_path: result_dict, ...}
#         :param save_dir: 保存目录
#         :param format: "YOLO" 或 "VOC"
#         :param class_map: 类别映射字典
#         :return: (success_count, fail_count, fail_list)
#         """
#         success_count = 0
#         fail_count = 0
#         fail_list = []
#         for img_path, result in results.items():
#             detections = result.get("data", {}).get("detections", [])
#             try:
#                 if format == "YOLO":
#                     save_yolo_result(img_path, detections, class_map, save_dir)
#                 else:
#                     save_voc_result(img_path, detections, save_dir)
#                 success_count += 1
#             except Exception as e:
#                 fail_count += 1
#                 fail_list.append((img_path, str(e)))
#         return success_count, fail_count, fail_list