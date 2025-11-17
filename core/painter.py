# ui/image_viewer.py
import re
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
import cv2
import numpy as np
from sympy.geometry.plane import y
from PIL import Image, ImageDraw as PILImageDraw, ImageFont
# from utils.image_utils import map_widget_to_image

class ImageDraw():
    def _get_chinese_font(self, font_size: int):
        """Return a truetype font that supports Chinese on Windows; fallback to default."""
        candidate_paths = [
            r"C:\\Windows\\Fonts\\msyh.ttc",   # Microsoft YaHei
            r"C:\\Windows\\Fonts\\msyh.ttf",
            r"C:\\Windows\\Fonts\\simhei.ttf", # SimHei
            r"C:\\Windows\\Fonts\\simsun.ttc", # SimSun
        ]
        for path in candidate_paths:
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue
        # Fallback (may not render Chinese correctly)
        return ImageFont.load_default()

    def _put_text_cn(self, image_bgr: np.ndarray, text: str, org: tuple, color_bgr=(0, 255, 0), font_size: int = 20) -> np.ndarray:
        """Draw text (supports Chinese) on a BGR image using PIL, then return BGR image."""
        x, y = org
        # Convert to RGB for PIL
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(image_rgb)
        draw = PILImageDraw.Draw(pil_img)
        font = self._get_chinese_font(font_size)
        # Convert color to RGB
        color_rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))
        # Prevent text from going above image
        y = max(y, 0)
        draw.text((int(x), int(y)), text, font=font, fill=color_rgb)
        # Back to BGR
        image_rgb_out = np.array(pil_img)
        return cv2.cvtColor(image_rgb_out, cv2.COLOR_RGB2BGR)
    def run(self, image, result):
        image_copy = image.copy()
        details = []
        if result.get("code") == 200:
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
                instance['socre'] = f"{float(score):.2f}"
                instance['coordinate'] = f"{[xmin, ymin], [xmin, xmax]}"
                instance['image'] = cv2.cvtColor(image[ymin:ymax, xmin:xmax, :], cv2.COLOR_BGR2RGB)

                color = (0, 255, 0)
                cv2.rectangle(image_copy, (xmin, ymin), (xmax, ymax), color, 2)
               
                text = f"{class_name} {float(score):.2f}" if score else class_name
                # Use PIL to render Chinese text
                baseline_y = ymin - 5
                # cv2.putText(image_copy, text, (xmin, ymin - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                image_copy = self._put_text_cn(image_copy, text, (xmin, baseline_y), color_bgr=(255, 255, 255), font_size=20)

                details.append(instance)

        return image_copy, details