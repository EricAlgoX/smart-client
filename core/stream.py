import os
import cv2
import time
import glob
from utils.logger import logger

from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QFileDialog, QLabel, QSizePolicy, QInputDialog

def resize(frame):
    """
    检查图片尺寸，如果超过1920x1080则按比例缩放，否则保持原图
    """
    height, width = frame.shape[:2]
    
    # 如果图片尺寸在允许范围内，直接返回原图
    if width <= 1920 and height <= 1080:
        return frame
        
    # 计算缩放比例，保持宽高比
    scale = min(1920/width, 1080/height)
    new_width = int(width * scale)
    new_height = int(height * scale)
    
    # 使用高质量的插值算法进行缩放
    resized_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    
    return resized_frame

class ImageStream:
    def __init__(self, source=0):
        self.image_path = source

    def read(self):
        if not os.path.exists(self.image_path):
            return None, None

        basename = os.path.basename(self.image_path).lower()
        if not basename.endswith(('.jpg', '.jpeg', '.png', '.bmp')):
            return None, None

        frame = cv2.imread(self.image_path)
        if frame is None:
            return None, None
            
        # 检查图片尺寸，如果超过限制则按比例缩放
        return resize(frame), self.image_path

class VideoStream:
    def __init__(self, source=0):
        self.video_path = source
        # 强制使用 FFmpeg 后端，更稳定地读取 H.264
        self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频源：{source}")

        self.is_video = True

    def read(self, retries=3):
        for _ in range(retries):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                image_name = os.path.join('images', time.strftime("%Y%m%d_%H%M%S", time.localtime()) + '.jpg')
                return resize(frame), image_name
            time.sleep(0.01)
        return None, None

    def release(self):
        self.cap.release()

class FolderStream:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.image_files = []
        self.current_index = 0
        self.is_video = False
        
        # 获取文件夹中所有支持的图片文件
        supported_formats = ('.jpg', '.jpeg', '.png', '.bmp')
        for file_name in os.listdir(folder_path):
            if file_name.lower().endswith(supported_formats):
                self.image_files.append(os.path.join(folder_path, file_name))

        # 按文件名排序
        self.image_files.sort()
        logger.info(f"文件夹中找到 {len(self.image_files)} 张图片")

    def read(self):
        if not self.image_files or self.current_index >= len(self.image_files):
            return None, None
            
        image_path = self.image_files[self.current_index]
        frame = cv2.imread(image_path)
        
        if frame is not None:
            # 检查图片尺寸，如果超过限制则按比例缩放
            frame = resize(frame)
        if not self.next():
            return None, None
        
        return frame, image_path
    
    def next(self):
        """移动到下一张图片"""
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            return True
        else: 
            self.reset()
            return False
    
    def reset(self):
        """重置到第一张图片"""
        self.current_index = 0

def select_image(self):
    try:
        file_name, _ = QFileDialog.getOpenFileName(
            self.ui, 
            "选择图片", 
            "", 
            "图像文件 (*.png *.jpg *.jpeg *.bmp *.gif)",
            options=QFileDialog.DontUseNativeDialog
        )
        if not file_name:
            return None
        
        stream = ImageStream(file_name)
        frame, frame_name = stream.read()
        
        if frame is None:
            return None
        return {
            'stream': stream,
            'stream_name': file_name,
            'frame': frame,
            'frame_name': frame_name
        }
    except Exception as e:
        logger.error(f"选择图片时出错: {e}")
        return None

def select_video(self):
    try:
        video_name, _ = QFileDialog.getOpenFileName(
            self.ui, 
            "选择视频", 
            "", 
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm)",
            options=QFileDialog.DontUseNativeDialog
        )
        if not video_name:
            return None
        
        stream = VideoStream(video_name)
        frame, frame_name = stream.read()
        
        if frame is None:
            return None
        
        return {
            'stream': stream,
            'stream_name': video_name,
            'frame': frame,
            'frame_name': frame_name
        }
    except Exception as e:
        logger.error(f"选择视频时出错: {e}")
        return None

def select_folder(self):
    try:
        folder_name = QFileDialog.getExistingDirectory(
            self.ui,
            "选择文件夹",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog
        )
        if not folder_name:
            logger.warning("文件夹选择已取消")
            return None
        
        stream = FolderStream(folder_name)
        frame, frame_name = stream.read()
        
        if frame is None:
            logger.warning("文件夹中没有图片")
            return None
        
        return {
            'stream': stream,
            'stream_name': folder_name,
            'frame': frame,
            'frame_name': frame_name
        }
    except Exception as e:
        logger.error(f"选择文件夹时出错: {e}")
        return None

def select_stream(self):
    options = ["本地摄像头", "RTSP/HTTP 地址", "取消"]
    choice, ok = QInputDialog.getItem(
        self.ui, 
        "选择实时流来源", 
        "请选择:", 
        options, 
        0, 
        False
    )

    if not ok or choice == "取消":
        return

    try:
        if choice == "本地摄像头":
            index, ok = QInputDialog.getInt(
                self.ui, 
                "摄像头索引", 
                "输入摄像头索引（通常为0或1）:", 
                0, 
                0, 
                10, 
                1
            )
            if not ok:
                logger.warning("摄像头索引输入已取消")
                return
            stream_name = index
        else:
            url, ok = QInputDialog.getText(
                self.ui, 
                "输入流地址", 
                "请输入 RTSP/HTTP 流地址（例如 rtsp://... 或 http://...）:",
                text="rtsp://admin:Geovis@13@192.168.110.120:554"
                # text="rtsp://admin:Geovis13@192.168.130.164:554"

            )
            if not ok:
                logger.warning("流地址输入已取消")
                return
            stream_name = url

        if not stream_name:
            return None
        
        stream = VideoStream(stream_name)
        frame, frame_name = stream.read()
        
        if frame is None:
            return None
        
        return {
            'stream': stream,
            'stream_name': stream_name,
            'frame': frame,
            'frame_name': frame_name
        }
    except Exception as e:
        logger.error(f"选择实时流时出错: {e}")
        return None
         