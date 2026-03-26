import os
from unittest import result
import cv2
import json
import numpy as np
import threading
from functools import partial
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel, QMessageBox
from PyQt5.QtGui import QPixmap
from core.client import StartClient
from PyQt5.QtGui import QImage, QPixmap
from utils.logger import logger
from core.converter import ImageConverter
from utils.profiler import profiler

from core.writer import ImageWriter, LabelWriter
from core.server import start_server, stop_all_servers
from core.stream import select_image, select_video, select_stream, select_folder
from core.queue import image_queue, result_queue

class MainController:
    def __init__(self, ui):
        self.ui = ui
        self.roi_points = []
        self.frame = None
        self.converter = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.next)
        
        # 事件绑定
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.api = json.load(f)
                self.ui.selectModelBox.addItems(self.api.keys())
        except Exception as e:
            logger.error(f"加载 api.json 失败: {e}")
            self.api = {}
        self.ui.selectImageButton.clicked.connect(partial(self.select_source, "image"))
        self.ui.selectFolderButton.clicked.connect(partial(self.select_source, "folder"))
        self.ui.selectVideoButton.clicked.connect(partial(self.select_source, "video"))
        self.ui.selectSourceButton.clicked.connect(partial(self.select_source, "stream"))
        self.ui.selectModelBox.currentIndexChanged.connect(self.select_model)
        self.ui.nmsSpinBox.valueChanged.connect(self.nmsspinbox_changed)
        self.ui.nmsSlider.valueChanged.connect(self.nmsslider_changed)
        self.ui.conSpinBox.valueChanged.connect(self.conspinbox_changed)
        self.ui.conSlider.valueChanged.connect(self.conslider_changed)
        self.ui.startDetectionButton.clicked.connect(self.startDetection)
        self.ui.saveDataButton.clicked.connect(self.save_data)
        self.ui.saveDataButton.setCheckable(True)
        self.ui.setROIButton.clicked.connect(self.set_roi_image)
        self.ui.clearImageButton.clicked.connect(self.clear_image)
        self.ui.clearROIButton.clicked.connect(self.clear_roi_image)

    def _get_label_size(self):
        try:
            return self.ui.label.size()
        except Exception:
            return None
    
    def _sync_spinbox_to_slider(self, spinbox_value, slider_widget):
        """通用方法：将 spinbox 值同步到 slider"""
        slider_widget.blockSignals(True)
        slider_widget.setValue(int(spinbox_value * 100))
        slider_widget.blockSignals(False)
    
    def _sync_slider_to_spinbox(self, slider_value, spinbox_widget):
        """通用方法：将 slider 值同步到 spinbox"""
        spinbox_widget.blockSignals(True)
        spinbox_widget.setValue(slider_value / 100.0)
        spinbox_widget.blockSignals(False)

    def select_source(self, source_type):
        source_map = {
            'image': select_image,
            'video': select_video,
            'folder': select_folder,
            'stream': select_stream,
        }

        self.source_type = source_type
        self.source = source_map.get(self.source_type)(self)
        if self.source:
            self.ui.log_edit.append(f'已选择: {self.source['stream_name']}')
            self.ui.label.setStyleSheet("background-color: transparent;")
            result_queue.put((self.source['frame'], [], self.source['frame_name']))
        else:
            QMessageBox.critical(self.ui, 'Error', 'Please select again')

        # 停止旧的 converter 线程
        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            result_queue,
            self._get_label_size,
            fps_limit=20
            )
        self.converter.pixmap_ready.connect(self.display)
        self.converter.start()

        self.timer.stop()  # 必须先 stop
        self.start_flag = False
        if self.source_type == 'stream':
            interval = 33  # 从33ms改为100ms，降低到10fps
            self.timer.start(interval)

    def select_model(self, index):
        stop_all_servers()

        self.model_name = self.ui.selectModelBox.itemText(index)

        self.server_thread = threading.Thread(
                target=start_server,
                args=(self.model_name,),
                daemon=True
            )
        self.server_thread.start()

        self.client_thread = StartClient(
            url=self.api[self.model_name],
            input_queue=image_queue,
            nms = self.ui.nmsSpinBox.value(),
            polygon=self.roi_points,
            confidence=self.ui.conSpinBox.value(),
            timeout_mins=self.ui.timeoutSpinBox.value()
            )
        self.client_thread.start()
        
        self.ui.log_edit.append(f'Selected model: {self.model_name}')

    def nmsspinbox_changed(self, value):
        self._sync_spinbox_to_slider(value, self.ui.nmsSlider)
    
    def nmsslider_changed(self, value):
        self._sync_slider_to_spinbox(value, self.ui.nmsSpinBox)

    def conspinbox_changed(self, value):
        self._sync_spinbox_to_slider(value, self.ui.conSlider)
    
    def conslider_changed(self, value):
        self._sync_slider_to_spinbox(value, self.ui.conSpinBox)

    def startDetection(self):
        if self.source_type == 'image':
            if hasattr(self, "client_thread"):
                image_queue.put((self.source['frame'], self.source['frame_name']))
            else:
                self.ui.log_edit.append("未选择有效的模型")
        
        if self.source_type == 'video' or self.source_type == 'folder':
            self.timer.stop()

            if not self.start_flag:
                self.start_flag = True
                if hasattr(self, "client_thread"):
                    image_queue.put((self.source['frame'], self.source['frame_name']))
                else:
                    self.ui.log_edit.append("未选择有效的模型")

                interval = 33
                self.timer.start(interval)
                self.ui.startDetectionButton.setText("停止检测")
                return
            else:
                self.start_flag = False
                self.ui.startDetectionButton.setText("开始检测")
        
        if self.source_type == 'stream':
            if not self.start_flag:
                if hasattr(self, "client_thread"):
                    self.start_flag = True
                    try:
                        image_queue.put((self.source['frame'], self.source['frame_name']))
                    except:
                        pass
                    self.ui.startDetectionButton.setText("停止检测")
                else:
                    self.start_flag = False
                    self.ui.log_edit.append("未选择有效的模型")   
            else:
                self.start_flag = False
                self.ui.startDetectionButton.setText("开始检测")
    
    @profiler.measure("next")
    def next(self):
        self.source['frame'], self.source['frame_name'] = self.source['stream'].read()
        if self.source['frame'] is None:
            self.timer.stop()
            self.start_flag = False
            self.ui.startDetectionButton.setText("开始检测")
            QMessageBox.information(self.ui, "Finished", "All data have been processed.")
            return  # 立即返回，不再执行后续代码

        if self.ui.saveDataButton.isChecked() and self.source_type in ['video', 'stream']:
            if hasattr(self, 'image_writer'):
                self.image_writer.submit(self.source['frame_name'], self.source['frame'], drop_if_full=True)

        # 异步启动推理（不阻塞UI）
        if hasattr(self, "client_thread") and self.start_flag:
            try:
                image_queue.put((self.source['frame'], self.source['frame_name']))
                logger.debug(f'image_queue size: {image_queue.qsize()}, result_queue size: {result_queue.qsize()}')
            except Exception as e:
                logger.error(e)
        else:
            try:
                result_queue.put((self.source['frame'], [], self.source['frame_name']))
            except:
                pass
    
    @profiler.measure("tabel_list")
    def tabel_list(self, details):
        # 更新表格（限制行数，避免UI卡顿）
        max_rows = min(len(details), self.ui.tableWidget.rowCount())
        for index in range(max_rows):
            instance = details[index]

            instance_class = instance['class']
            instance_score = instance['score']
            instance_coordinate = f'{instance['coordinate']}'

            # 只在需要时裁剪图像
            if 'bbox' in instance and hasattr(self, 'current_display_image'):
                xmin, ymin, xmax, ymax = instance['bbox']
                instance_image = self.current_display_image[ymin:ymax, xmin:xmax, :].copy()  # 添加 .copy()

                # 创建 QImage
                height, width, channel = instance_image.shape
                bytes_per_line = 3 * width
                q_image = QImage(instance_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_image)

                # 创建 label 并设置
                label = QLabel()
                column_width = self.ui.tableWidget.columnWidth(3)
                row_height = self.ui.tableWidget.rowHeight(index)
                label.setFixedSize(column_width, row_height)

                pixmap = pixmap.scaled(label.size(),
                                       Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation
                                    )
                label.setPixmap(pixmap)
                self.ui.tableWidget.setCellWidget(index, 3, label)

            instance_class = QTableWidgetItem(instance_class)
            instance_class.setTextAlignment(Qt.AlignCenter)
            self.ui.tableWidget.setItem(index, 0, instance_class)

            instance_score = QTableWidgetItem(instance_score)
            instance_score.setTextAlignment(Qt.AlignCenter)
            self.ui.tableWidget.setItem(index, 1, instance_score)
            self.ui.tableWidget.setItem(index, 2, QTableWidgetItem(instance_coordinate))

    @profiler.measure("display")
    def display(self, qimg, details=[], path='', original_rgb=None):
        # 保存原始 RGB 图像供表格使用
        if original_rgb is not None:
            self.current_display_image = original_rgb

        # 保存推理结果
        if self.ui.saveDataButton.isChecked():
            if hasattr(self, 'label_writer'):
                self.label_writer.submit(path, details, drop_if_full=True)

        # 显示
        # # 绘制ROI（如果存在）
        # if hasattr(self, 'current_roi') and self.current_roi is not None:
        #     if len(self.current_roi) >= 3:
        #         pts = np.array(self.current_roi, np.int32)
        #         pts = pts.reshape((-1, 1, 2))

        #         # 创建overlay用于半透明填充
        #         overlay = display_frame.copy()
        #         cv2.fillPoly(overlay, [pts], color=(255, 0, 0))  # RGB，红色

        #         alpha = 0.3  # 透明度 0~1
        #         display_frame = cv2.addWeighted(overlay, alpha, display_frame, 1 - alpha, 0)

        #         # 绘制边界
        #         cv2.polylines(display_frame, [pts], isClosed=True, color=(255, 0, 0), thickness=2)

        #     # 绘制点
        #     for pt in self.current_roi:
        #         cv2.circle(display_frame, (pt[0], pt[1]), 3, (0, 0, 255), -1)

        qpix = QPixmap.fromImage(qimg)

        self.ui.label.setPixmap(qpix)

        self.tabel_list(details)
    
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
        if self.frame is None:
            return
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
    
    def save_data(self):
        # 初始化一次（例如在控制器初始化时）
        self.image_writer = ImageWriter(save_dir="images", maxsize=200)
        self.image_writer.start()
        self.label_writer = LabelWriter(save_dir="annotations", maxsize=200)
        self.label_writer.start()