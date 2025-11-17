
from multiprocessing import Value
from tkinter import NO
import os
import cv2

import numpy as np
import threading
from functools import partial
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QFileDialog, QLabel, QSizePolicy, QMessageBox
from PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QLinearGradient
from core.inference import Inference
from core.painter import ImageDraw
from PyQt5.QtGui import QImage, QPixmap
from utils.logger import logger

from core.writer import ImageWriter, LabelWriter
from core.server import start_server, stop_server, stop_all_servers
from core.stream import select_image, select_video, select_folder, select_stream


class MainController:
    def __init__(self, ui):
        self.ui = ui
        self.model = None
        self.stream = None
        self.file_name = None
        self.roi_points = []
        self.drawer = ImageDraw()
        self.current_server = None

        # 设置定时器定时调用
        self.timer = QTimer()
        
        # 初始化一次（例如在控制器初始化时）
        self.image_writer = ImageWriter(save_dir="images", maxsize=200)
        self.image_writer.start()
        self.label_writer = LabelWriter(save_dir="annotations", maxsize=200)
        self.label_writer.start()
        

        self.video_timer = QTimer()
        self.video_timer.timeout.connect(self.update_frame)

        self.mode = 'image' # choice = ['image', 'folder', 'video']
        self.api = {
            '01_overflow': 'http://127.0.0.1:5000/sv/detection_garbageoverflow',
            '02_roadcongestion': 'http://127.0.0.1:5000/sv/detection_roadcongestion',
            '03_illegalparking': 'http://127.0.0.1:5000/sv/tracking_illegalparking',
            '04_licenseplate': 'http://127.0.0.1:5000/sv/recognition_licenseplate',
            '05_nvmencroachment': 'http://127.0.0.1:5000/sv/detection_nmvencroachment',
            '06_person': 'http://127.0.0.1:5000/sv/tracking_person',
            '07_persongather': 'http://127.0.0.1:5000/sv/detection_persongather',
            '08_slagtruckexcavator': 'http://127.0.0.1:5000/sv/detection_slagtruckexcavator',
            '09_face': 'http://127.0.0.1:5000/sv/recognition_face',
            '10_areaintrusion': 'http://127.0.0.1:5000/sv/detection_areaintrusion',
            '11_fire': 'http://127.0.0.1:5000/sv/detection_fire',
            '12_smoke': 'http://127.0.0.1:5000/sv/detection_smoke',
            '13_cigarette': 'http://127.0.0.1:5000/sv/detection_cigarette',
            '16_elevator': 'http://127.0.0.1:5000/sv/detection_elevator',
            '18_vehicle': 'http://127.0.0.1:5000/sv/tracking_vehicle',
            '19_animal': 'http://127.0.0.1:5000/sv/detection_animal',
            '21_climb': 'http://127.0.0.1:5000/sv/detection_climb',
            '24_employeeabsence': 'http://127.0.0.1:5000/sv/detection_employeeabsence',
            '25_personexcessivedwell': 'http://127.0.0.1:5000/sv/tracking_personexcessivedwell',
            '26_waste': 'http://127.0.0.1:5000/sv/detection_waste',
            '27_roadmanhole': 'http://127.0.0.1:5000/sv/detection_roadmanhole',
            '28_roadwater': 'http://127.0.0.1:5000/sv/detection_roadwaterlogging',
            '29_roadpothole': 'http://127.0.0.1:5000/sv/detection_roadpothole',
            '30_roadcrack': 'http://127.0.0.1:5000/sv/detection_roadcrack',
            '32_baresoilcoverage':'http://127.0.0.1:5000/sv/detection_baresoilcoverage',
            '34_facemask': 'http://127.0.0.1:5000/sv/detection_facemask',
            '35_illegalphotography': 'http://127.0.0.1:5000/sv/detection_illegalphotography',
            '38_roadobstacle': 'http://127.0.0.1:5000/sv/detection_roadobstacle',
            '39_riderhelmetcheck': 'http://127.0.0.1:5000/sv/detection_riderhelmetcheck',
            '40_pedestrianredlightviolation': 'http://127.0.0.1:5000/sv/detection_pedestrianredlightviolation',
            '41_unleasheddog': 'http://127.0.0.1:5000/sv/detection_unleasheddog',
            '53_droneroadcrack':'http://127.0.0.1:5000/sv/detection_droneroadcrack',
            '54_droneroadwaterlogging':'http://127.0.0.1:5000/sv/detection_droneroadwaterlogging',
            '57_droneriverfloatingdebris':'http://127.0.0.1:5000/sv/detection_droneriverfloatingdebris',
            '58_dronesafetyhelmet':'http://127.0.0.1:5000/sv/detection_dronesafetyhelmet',
        }

        # 追加页面信息
        self.ui.selectModelBox.addItems(self.api.keys())
        self.ui.tableWidget.setColumnWidth(2, 150)
        row_count = self.ui.tableWidget.rowCount()
        for row in range(row_count):
            self.ui.tableWidget.setRowHeight(row, 50)  # 每行高度设置为 50
            
        # 绑定按钮事件
        self.ui.selectImageButton.clicked.connect(partial(self.select_source, "image"))
        self.ui.selectVideoButton.clicked.connect(partial(self.select_source, "video"))
        self.ui.selectFolderButton.clicked.connect(partial(self.select_source, "folder"))
        self.ui.selectSourceButton.clicked.connect(partial(self.select_source, "stream"))

        self.ui.selectModelBox.currentIndexChanged.connect(self.select_model)
        self.ui.nmsSpinBox.valueChanged.connect(self.nmsspinbox_changed)
        self.ui.nmsSlider.valueChanged.connect(self.nmsslider_changed)
        self.ui.conSpinBox.valueChanged.connect(self.conspinbox_changed)
        self.ui.conSlider.valueChanged.connect(self.conslider_changed)
        self.ui.saveDataButton.setCheckable(True)

        self.ui.nextButton.setEnabled(False)
        self.ui.autoInferButton.setEnabled(False)

        # 稳定图像显示区域，避免设置像素图后改变sizeHint引发布局抖动
        if hasattr(self.ui, 'label') and isinstance(self.ui.label, QLabel):
            self.ui.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            # 设定一个合理的最小尺寸（可按需要调整）
            if self.ui.label.minimumWidth() == 0 and self.ui.label.minimumHeight() == 0:
                self.ui.label.setMinimumSize(640, 360)

        self.ui.startDetectionButton.clicked.connect(self.start_inference)
        self.ui.nextButton.clicked.connect(self.update_frame)
        self.ui.autoInferButton.clicked.connect(self.auto_inference)


        self.ui.clearImageButton.clicked.connect(self.clear_image)
        self.ui.setROIButton.clicked.connect(self.set_roi_image)
        self.ui.clearROIButton.clicked.connect(self.clear_roi_image)
        
    def select_source(self, source_type):
        self.source_type = source_type
        if self.source_type == 'folder':
            self.ui.nextButton.setEnabled(True)
            self.ui.autoInferButton.setEnabled(True)
        else:
            self.ui.nextButton.setEnabled(False)
            self.ui.autoInferButton.setEnabled(False)
        
        source_map = {
            'image': select_image,
            'video': select_video,
            'folder': select_folder,
            'stream': select_stream
        }
        self.source = source_map.get(source_type)(self)
        if self.source:
            self.ui.log_edit.append(f'已选择: {self.source['stream_name']}')
            self.ui.label.setStyleSheet("background-color: white;")
            self.display(self.source['frame'])
        else:
            QMessageBox.critical(self.ui, 'Error', 'Please select again')
            
    def select_model(self, index):
        stop_all_servers()

        model_name = self.ui.selectModelBox.itemText(index)
        self.thread = threading.Thread(
                target=start_server,
                args=(model_name,),
                daemon=True
            )
        self.thread.start()
        self.current_server = model_name

        self.model = Inference(self.api[model_name])
        self.ui.log_edit.append(f'Selected model: {model_name}')

    def nmsspinbox_changed(self, value):
        # 将 spinbox 的浮点值映射到 slider 的整数值
        self.ui.nmsSlider.blockSignals(True)
        self.ui.nmsSlider.setValue(int(value * 100))   # 根据实际范围调整
        self.ui.nmsSlider.blockSignals(False)
    
    def nmsslider_changed(self, value):
        # 将 slider 的整数值映射到 spinbox 的浮点值
        self.ui.nmsSpinBox.blockSignals(True)          # 阻止循环信号
        self.ui.nmsSpinBox.setValue(value / 100.0)     # 根据实际范围调整
        self.ui.nmsSpinBox.blockSignals(False)

    def conspinbox_changed(self, value):
        self.ui.conSlider.blockSignals(True)
        self.ui.conSlider.setValue(int(value * 100))   # 根据实际范围调整
        self.ui.conSlider.blockSignals(False)
    
    def conslider_changed(self, value):
        self.ui.conSpinBox.blockSignals(True)          # 阻止循环信号
        self.ui.conSpinBox.setValue(value / 100.0)     # 根据实际范围调整
        self.ui.conSpinBox.blockSignals(False)

    def start_inference(self):
        # # 停止之前的视频定时器
        # if self.video_timer.isActive():
        #     self.video_timer.stop()
        #     self.ui.startDetectionButton.setText("开始检测")
        #     return

        if self.model is None:
            self.ui.log_edit.append("未选择有效的模型")
            
        if not self.source['stream']:
            QMessageBox.critical(self.ui, 'Error', 'Please select source first')
            return

        # if self.mode == 'video':
        #     self.video_timer.start(20)  # 每100ms处理一帧
        #     self.ui.startDetectionButton.setText("停止检测")
        # elif self.mode == 'folder':
        #     self.video_timer.start(1000)  # 每100ms处理一帧
        #     self.ui.startDetectionButton.setText("停止检测")
                
        if self.model:    
            try:
                result = self.model.run(self.source['frame'],
                                        nms = self.ui.nmsSpinBox.value(),
                                        polygon = self.roi_points,
                                        confidence = self.ui.conSpinBox.value(),
                                        timeout = self.ui.timeoutSpinBox.value()
                                        )
                self.ui.log_edit.append(f'Info:{result}')
                if self.ui.saveDataButton.isChecked():
                    self.label_writer.submit(self.source['frame_name'], result['data']['detections'], drop_if_full=True)

                self.display_result(result)
            except Exception as e:
                logger.error(f"推理失败: {e}")
    
    def update_frame(self):
        """处理当前帧（图片或文件夹中的图片）"""
        # if self.mode not in ['folder', 'video']:
        #     self.video_timer.stop()
        self.source['frame'], self.source['frame_name'] = self.source['stream'].read()
        if self.source['frame'] is None:
            QMessageBox.information(self.ui, "Finished", "All data have been processed.")
            return False

        #     self.video_timer.stop()
        #     self.ui.startDetectionButton.setText("开始检测")
        #     self.ui.log_edit.append("数据读取结束")
        #     return

        self.display(self.source['frame'])
        
        if self.ui.saveDataButton.isChecked() and self.source_type in ['video', 'stream']:

            # 原来：save_img(self.source['frame_name'], self.source['frame'])
            self.image_writer.submit(self.source['frame_name'], self.source['frame'], drop_if_full=True)
        
        return True

    def auto_inference(self):
        self.timer.timeout.connect(self.process_next_frame)
        self.timer.start(30)  # 每30ms一帧（约33fps）

    def process_next_frame(self):
        if not self.update_frame():
            self.timer.stop()
            return
        self.start_inference()

    def display(self, frame):
        overlay = frame.copy()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        overlay = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)

        if hasattr(self, 'current_roi') and self.current_roi is not None:
            if len(self.current_roi) >= 3:
                pts = np.array(self.current_roi, np.int32)
                pts = pts.reshape((-1, 1, 2))

                cv2.fillPoly(overlay, [pts], color=(255, 0, 0))  # RGB，红色

                alpha = 0.3  # 透明度 0~1
                overlay = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

                cv2.polylines(overlay, [pts], isClosed=True, color=(255, 0, 0), thickness=2)

            for pt in self.current_roi:
                cv2.circle(overlay, (pt[0], pt[1]), 3, (0, 0, 255), -1)

        h, w, ch = overlay.shape
        qimg = QImage(overlay, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled_pixmap = pixmap.scaled(
            self.ui.label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.ui.label.setPixmap(scaled_pixmap)

    def display_result(self, result_frame):
        frame, details = self.drawer.run(self.source['frame'], result_frame)

        self.display(frame)

        for index, instance in enumerate(details):
            label = QLabel()
            column_width = self.ui.tableWidget.columnWidth(3)
            row_height = self.ui.tableWidget.rowHeight(index)
            label.setFixedSize(column_width, row_height)

            instance_image = instance['image']
            instance_image = cv2.cvtColor(instance_image, cv2.COLOR_BGR2RGB)
            instance_class = instance['class']
            instance_score = instance['socre']
            instance_coordinate = instance['coordinate']

            height, width, channel = instance_image.shape
            bytes_per_line = 3 * width
            q_image = QImage(instance_image.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            pixmap = QPixmap.fromImage(q_image)
            pixmap = pixmap.scaled(label.size(),
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation
                                )
            label.setPixmap(pixmap)

            instance_class = QTableWidgetItem(instance_class)
            instance_class.setTextAlignment(Qt.AlignCenter)
            self.ui.tableWidget.setItem(index, 0, instance_class)

            instance_score = QTableWidgetItem(instance_score)
            instance_score.setTextAlignment(Qt.AlignCenter)
            self.ui.tableWidget.setItem(index, 1, instance_score)
            self.ui.tableWidget.setItem(index, 2, QTableWidgetItem(instance_coordinate))
            self.ui.tableWidget.setCellWidget(index, 3, label)
        
        # 如果是文件夹模式，显示导航信息
        if hasattr(self.stream, 'is_video') and not self.stream.is_video and hasattr(self.stream, 'image_files'):
            current_file = os.path.basename(self.stream.image_files[self.stream.current_index])
            total_files = len(self.stream.image_files)
            logger.info(f"当前图片: {current_file} ({self.stream.current_index + 1}/{total_files})")
    
    def set_roi_image(self):
        """设置ROI（感兴趣区域）- 允许用户在图像上绘制多边形围栏"""
        self.redraw_with_roi()

        if not hasattr(self, 'roi_mode') or not self.roi_mode:
            # 进入ROI绘制模式
            self.roi_mode = True
            self.drawing_roi = False
            
            # 更改鼠标样式，提示用户可以绘制
            self.ui.label.setCursor(Qt.CrossCursor)
            
            # 绑定鼠标事件到label
            self.ui.label.mousePressEvent = self.roi_mouse_press
            self.ui.label.mouseMoveEvent = self.roi_mouse_move
            self.ui.label.mouseDoubleClickEvent = self.roi_mouse_double_click
            
            # 更新按钮状态
            self.ui.setROIButton.setText("完成绘制")
            self.ui.setROIButton.setStyleSheet("background-color: #4CAF50; color: white;")
            
            logger.info('进入ROI绘制模式，点击图像绘制多边形，双击完成绘制')
        else:
            # 完成ROI绘制
            self.finish_roi_drawing()
    
    def roi_mouse_press(self, event):
        """ROI绘制时的鼠标按下事件"""
        if not self.roi_mode:
            return
            
        if event.button() == Qt.LeftButton:
            if not self.drawing_roi:
                self.roi_points = []
                self.drawing_roi = True
            
            # 获取鼠标位置
            pos = event.pos()
            img_x, img_y = self.map_label_to_image(pos)
            self.roi_points.append((img_x, img_y))
            
            # 重绘图像显示ROI
            self.redraw_with_roi()
            logger.info(f'添加ROI点: ({img_x}, {img_y})')
    
    def roi_mouse_move(self, event):
        """ROI绘制时的鼠标移动事件"""
        if not self.roi_mode or not self.drawing_roi:
            return
            
        # 记录鼠标位置用于绘制预览线
        self.last_mouse_pos = event.pos()
        self.redraw_with_roi()
    
    def roi_mouse_double_click(self, event):
        """ROI绘制时的鼠标双击事件"""
        if not self.roi_mode or not self.drawing_roi:
            return
            
        if len(self.roi_points) >= 3:
            self.drawing_roi = False
            self.finish_roi_drawing()
            logger.info(f'完成ROI绘制，共{len(self.roi_points)}个点')
    
    def redraw_with_roi(self):
        """重绘图像，显示ROI多边形"""
        display_frame = self.frame.copy()
        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)

        # 绘制ROI多边形
        if hasattr(self, 'roi_points'):
            if len(self.roi_points) > 1:               
                # 绘制多边形
                if len(self.roi_points) >= 3:
                    # 转换ROI为numpy数组
                    pts = np.array(self.roi_points, np.int32)
                    pts = pts.reshape((-1, 1, 2))

                    # 创建一个与frame大小相同的全黑蒙版
                    overlay = display_frame.copy()

                    # 填充多边形（红色，半透明）
                    cv2.fillPoly(overlay, [pts], color=(255, 0, 0))  # BGR，红色

                    # 融合overlay到原图，alpha控制透明度
                    alpha = 0.3  # 透明度 0~1
                    display_frame = cv2.addWeighted(overlay, alpha, display_frame, 1 - alpha, 0)

                    # 绘制红色实线边界
                    cv2.polylines(display_frame, [pts], isClosed=True, color=(255, 0, 0), thickness=2)

                # 绘制点
                for pt in self.roi_points:
                    cv2.circle(display_frame, (pt[0], pt[1]), 3, (0, 0, 255), -1)
                
                # # 绘制预览线（如果正在绘制）
                # if self.drawing_roi and hasattr(self, 'last_mouse_pos') and self.roi_points:
                #     last_img_pt = self.map_label_to_image(self.roi_points[-1])
                #     current_img_pt = self.map_label_to_image(self.last_mouse_pos)
                #     cv2.line(display_frame, last_img_pt, current_img_pt, (0, 255, 255), 2)
        
        # 显示更新后的图像
        h, w, ch = display_frame.shape
        qimg = QImage(display_frame, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled_pixmap = pixmap.scaled(
            self.ui.label.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        self.ui.label.setPixmap(scaled_pixmap)
    
    def map_label_to_image(self, label_point):
        """将QLabel坐标映射到图像坐标"""
        if self.frame is None:
            return (0, 0)

        img_h, img_w = self.frame.shape[:2]
        label_w = self.ui.label.width()
        label_h = self.ui.label.height()

        # 计算图像缩放后显示的尺寸（保持比例）
        pixmap = self.ui.label.pixmap()
        if pixmap is None:
            return (0, 0)
        scaled_w = pixmap.width()
        scaled_h = pixmap.height()

        # 计算图像在 QLabel 中的偏移量（因为 KeepAspectRatio 居中显示）
        offset_x = (label_w - scaled_w) // 2
        offset_y = (label_h - scaled_h) // 2

        # 判断点击点是否在图像区域内
        x_in_image = label_point.x() - offset_x
        y_in_image = label_point.y() - offset_y
        if x_in_image < 0 or y_in_image < 0 or x_in_image > scaled_w or y_in_image > scaled_h:
            return (0, 0)  # 点击在空白区域

        # 映射到原图坐标
        scale_x = img_w / scaled_w
        scale_y = img_h / scaled_h
        img_x = int(x_in_image * scale_x)
        img_y = int(y_in_image * scale_y)

        return (img_x, img_y)

    def finish_roi_drawing(self):
        """完成ROI绘制"""
        self.roi_mode = False
        self.drawing_roi = False
        
        # 恢复鼠标样式
        self.ui.label.setCursor(Qt.ArrowCursor)
        
        # 恢复按钮状态
        self.ui.setROIButton.setText("设置视频围栏")
        self.ui.setROIButton.setStyleSheet("")
        
        # 保存ROI区域信息
        if hasattr(self, 'roi_points') and len(self.roi_points) >= 3:
            self.current_roi = self.roi_points
            logger.info(f'ROI设置完成，区域包含{len(self.roi_points)}个点')
        else:
            self.current_roi = None
            logger.info('ROI绘制取消或点数不足')
        
        # 移除临时鼠标事件绑定
        self.ui.label.mousePressEvent = None
        self.ui.label.mouseMoveEvent = None
        self.ui.label.mouseDoubleClickEvent = None

    def clear_roi_image(self):
        """清除ROI（感兴趣区域）"""
        # 清除ROI相关状态
        if hasattr(self, 'roi_mode'):
            self.roi_mode = False
        if hasattr(self, 'drawing_roi'):
            self.drawing_roi = False
        if hasattr(self, 'roi_points'):
            self.roi_points = []
        if hasattr(self, 'current_roi'):
            self.current_roi = None
        
        # 恢复鼠标样式
        if hasattr(self, 'ui') and hasattr(self.ui, 'label'):
            self.ui.label.setCursor(Qt.ArrowCursor)
            
            # 移除临时鼠标事件绑定
            self.ui.label.mousePressEvent = None
            self.ui.label.mouseMoveEvent = None
            self.ui.label.mouseDoubleClickEvent = None
        
        # 恢复按钮状态
        if hasattr(self, 'ui') and hasattr(self.ui, 'setROIButton'):
            self.ui.setROIButton.setText("设置视频围栏")
            self.ui.setROIButton.setStyleSheet("")
        
        # 如果有原始帧，重新显示原始图像
        if hasattr(self, 'frame') and self.frame is not None:
            frame_rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            qimg = QImage(frame_rgb, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            scaled_pixmap = pixmap.scaled(
                self.ui.label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.ui.label.setPixmap(scaled_pixmap)
        
        logger.info('ROI区域已清除')

    def clear_image(self):
        if self.frame is not None:
            self.ui.label.setStyleSheet("background-color: white;")
            self.display(self.frame)