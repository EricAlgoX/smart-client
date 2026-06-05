import os
import cv2
import json
import numpy as np
import threading
from functools import partial
from PySide6.QtWidgets import QTableWidgetItem, QLabel, QMessageBox, QTreeWidgetItem
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage
from core.client import StartClient
from utils.logger import logger
from core.converter import ImageConverter
from utils.profiler import profiler

from core.writer import ImageWriter, LabelWriter
from core.server import start_server, stop_all_servers
from core.stream import select_image, select_video, select_stream, select_folder
from core.queue import image_queue, result_queue


class MainController:
    def __init__(self, window):
        self.window = window
        self.ui = window  # 兼容旧代码：ui.xxx 直接访问 MainWindow 上的控件
        self.roi_points = []
        self.frame = None
        self.converter = None
        self._sources = {}  # 已注册的源 {name: source_dict}
        self.timer = QTimer()
        self.timer.timeout.connect(self.next)

        # 加载 API 配置
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.api = json.load(f)
                self.ui.selectModelBox.addItems(self.api.keys())
        except Exception as e:
            logger.error(f"加载 api.json 失败: {e}")
            self.api = {}

        self._setup_connections()

    def _setup_connections(self):
        """绑定所有信号"""
        ui = self.ui

        # ── 源管理按钮 ──
        ui.btnAddImage.clicked.connect(lambda: self.select_source("image"))
        ui.btnAddFolder.clicked.connect(lambda: self.select_source("folder"))
        ui.btnAddVideo.clicked.connect(lambda: self.select_source("video"))
        ui.btnAddStream.clicked.connect(lambda: self.select_source("stream"))

        # ── 源管理树：点击切换 ──
        ui.sourceTree.itemClicked.connect(self._on_source_item_clicked)

        # ── 菜单栏 ──
        ui.act_open_img.triggered.connect(lambda: self.select_source("image"))
        ui.act_open_vid.triggered.connect(lambda: self.select_source("video"))
        ui.act_open_dir.triggered.connect(lambda: self.select_source("folder"))
        ui.act_open_stream.triggered.connect(lambda: self.select_source("stream"))

        # ── 工具栏 ──
        ui.tb_act_start.triggered.connect(self.startDetection)
        ui.tb_act_stop.triggered.connect(self._stop_detection)

        # ── 模型参数同步 ──
        ui.selectModelBox.currentIndexChanged.connect(self.select_model)
        ui.nmsSpinBox.valueChanged.connect(self.nmsspinbox_changed)
        ui.nmsSlider.valueChanged.connect(self.nmsslider_changed)
        ui.conSpinBox.valueChanged.connect(self.conspinbox_changed)
        ui.conSlider.valueChanged.connect(self.conslider_changed)

        # ── 操作按钮 ──
        ui.startDetectionButton.clicked.connect(self.startDetection)
        ui.saveDataButton.clicked.connect(self.save_data)
        ui.setROIButton.clicked.connect(self.set_roi_image)
        ui.clearImageButton.clicked.connect(self.clear_image)
        ui.clearROIButton.clicked.connect(self.clear_roi_image)

    # ── 源管理树：点击切换源 ──
    def _on_source_item_clicked(self, item, column):
        """点击源管理树中的条目，切换到对应源"""
        source_name = item.text(0)
        # 从已注册的源中查找
        if hasattr(self, '_sources') and source_name in self._sources:
            src = self._sources[source_name]
            self.source = src
            self.source_type = src.get('_type', 'video')
            self._activate_source(src)

    def _add_source_to_tree(self, source_name, source_type):
        """把新源添加到源管理树"""
        tree = self.ui.sourceTree
        root = tree.invisibleRootItem()
        # 清除占位提示
        for i in range(root.childCount()):
            child = root.child(i)
            if child.flags() == Qt.ItemFlag.NoItemFlags:
                root.removeChild(child)

        # 检查是否已存在
        for i in range(root.childCount()):
            if root.child(i).text(0) == source_name:
                return

        icon_map = {'image': '📷', 'folder': '📁', 'video': '🎬', 'stream': '📡'}
        item = QTreeWidgetItem(root, [f"{icon_map.get(source_type, '📄')}  {source_name}"])
        item.setData(0, Qt.ItemDataRole.UserRole, source_type)
        tree.setCurrentItem(item)

    def _stop_detection(self):
        """停止检测"""
        self.start_flag = False
        self.timer.stop()
        self.ui.startDetectionButton.setText("▶  开始推理")

    # ────────────────────────────────────────────
    #  核心方法（与原版一致）
    # ────────────────────────────────────────────
    def _get_label_size(self):
        try:
            return self.ui.label.size()
        except Exception:
            return None

    def _sync_spinbox_to_slider(self, spinbox_value, slider_widget):
        slider_widget.blockSignals(True)
        slider_widget.setValue(int(spinbox_value * 100))
        slider_widget.blockSignals(False)

    def _sync_slider_to_spinbox(self, slider_value, spinbox_widget):
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

        # ── 视频流异步连接 ──
        if source_type == 'stream' and self.source and 'worker' in self.source:
            worker = self.source['worker']
            stream_name = self.source['stream_name']
            self.ui.log_edit.append(f'正在连接: {stream_name} ...')
            self.ui.label.setText("⏳ 正在连接视频流...")
            self.ui.label.setStyleSheet("color: #60a5fa; font-size: 16px; background: #0f0f1a;")
            # 阻止重复点击
            self.ui.startDetectionButton.setEnabled(False)
            worker.finished.connect(lambda stream, frame, fname: self._on_stream_connected(stream, frame, fname, stream_name))
            worker.error.connect(self._on_stream_error)
            worker.start()
            return

        # ── 其他源（同步）──
        if self.source and 'frame' in self.source:
            self._activate_source(self.source)
        elif self.source is None:
            pass  # 用户取消
        else:
            QMessageBox.critical(self.window, 'Error', 'Please select again')

    def _on_stream_connected(self, stream, frame, frame_name, stream_name):
        """视频流连接成功回调（主线程）"""
        self.ui.startDetectionButton.setEnabled(True)
        self.source = {
            'stream': stream,
            'stream_name': stream_name,
            'frame': frame,
            'frame_name': frame_name,
        }
        self.ui.log_edit.append(f'✅ 连接成功: {stream_name}')
        self._activate_source(self.source)
        # 自动开始推理
        self.start_flag = True
        self.timer.start(33)
        self.ui.startDetectionButton.setText("⏹  停止检测")

    def _on_stream_error(self, error_msg):
        """视频流连接失败回调（主线程）"""
        self.ui.startDetectionButton.setEnabled(True)
        self.ui.label.setText("连接失败，请重试")
        self.ui.label.setStyleSheet("color: #ef4444; font-size: 14px; background: #0f0f1a;")
        self.ui.log_edit.append(f'❌ 连接失败: {error_msg}')
        QMessageBox.critical(self.window, '连接失败', error_msg)

    def _activate_source(self, source):
        """源就绪后，启动 converter 和显示"""
        name = source["stream_name"]
        self.ui.log_edit.append(f'已选择: {name}')

        # 注册到源管理树
        self._sources[str(name)] = source
        self._add_source_to_tree(str(name), self.source_type)

        # 切换到视频显示
        self.ui.show_video()
        self.ui.label.setStyleSheet("background-color: transparent;")
        # 更新状态栏
        self.ui.set_status_connected(str(name))
        result_queue.put((source['frame'], [], source['frame_name']))

        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            result_queue,
            self._get_label_size,
            fps_limit=20
        )
        self.converter.pixmap_ready.connect(self.display)
        self.converter.start()

        self.timer.stop()
        self.start_flag = False

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
            nms=self.ui.nmsSpinBox.value(),
            polygon=self.roi_points,
            confidence=self.ui.conSpinBox.value(),
            timeout_mins=self.ui.timeoutSpinBox.value()
        )
        self.client_thread.start()

        self.ui.log_edit.append(f'Selected model: {self.model_name}')
        self.ui.statusModelLabel.setText(f'  模型: {self.model_name}  ')

    def nmsspinbox_changed(self, value):
        self._sync_spinbox_to_slider(value, self.ui.nmsSlider)

    def nmsslider_changed(self, value):
        self._sync_slider_to_spinbox(value, self.ui.nmsSpinBox)

    def conspinbox_changed(self, value):
        self._sync_spinbox_to_slider(value, self.ui.conSlider)

    def conslider_changed(self, value):
        self._sync_slider_to_spinbox(value, self.ui.conSpinBox)

    def startDetection(self):
        if not hasattr(self, 'source_type') or not hasattr(self, 'source') or self.source is None:
            self.ui.log_edit.append("请先选择输入源")
            return

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
                self.timer.start(33)
                self.ui.startDetectionButton.setText("⏹  停止检测")
                return
            else:
                self.start_flag = False
                self.ui.startDetectionButton.setText("▶  开始推理")

        if self.source_type == 'stream':
            if not self.start_flag:
                if hasattr(self, "client_thread"):
                    self.start_flag = True
                    try:
                        image_queue.put((self.source['frame'], self.source['frame_name']))
                    except:
                        pass
                    self.ui.startDetectionButton.setText("⏹  停止检测")
                else:
                    self.start_flag = False
                    self.ui.log_edit.append("未选择有效的模型")
            else:
                self.start_flag = False
                self.ui.startDetectionButton.setText("▶  开始推理")

    @profiler.measure("next")
    def next(self):
        self.source['frame'], self.source['frame_name'] = self.source['stream'].read()
        if self.source['frame'] is None:
            self.timer.stop()
            self.start_flag = False
            self.ui.startDetectionButton.setText("▶  开始推理")
            QMessageBox.information(self.window, "Finished", "All data have been processed.")
            return

        if self.ui.saveDataButton.isChecked() and self.source_type in ['video', 'stream']:
            if hasattr(self, 'image_writer') and self.image_writer is not None:
                self.image_writer.submit(self.source['frame_name'], self.source['frame'], drop_if_full=True)

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
        max_rows = min(len(details), self.ui.tableWidget.rowCount())
        for index in range(max_rows):
            instance = details[index]
            instance_class = instance['class']
            instance_score = instance['score']
            instance_coordinate = f'{instance["coordinate"]}'

            if 'bbox' in instance and hasattr(self, 'current_display_image'):
                xmin, ymin, xmax, ymax = instance['bbox']
                instance_image = self.current_display_image[ymin:ymax, xmin:xmax, :].copy()
                height, width, channel = instance_image.shape
                bytes_per_line = 3 * width
                q_image = QImage(instance_image.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(q_image)
                label = QLabel()
                column_width = self.ui.tableWidget.columnWidth(3)
                row_height = self.ui.tableWidget.rowHeight(index)
                label.setFixedSize(column_width, row_height)
                pixmap = pixmap.scaled(label.size(),
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                label.setPixmap(pixmap)
                self.ui.tableWidget.setCellWidget(index, 3, label)

            instance_class = QTableWidgetItem(instance_class)
            instance_class.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ui.tableWidget.setItem(index, 0, instance_class)

            instance_score = QTableWidgetItem(instance_score)
            instance_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ui.tableWidget.setItem(index, 1, instance_score)
            self.ui.tableWidget.setItem(index, 2, QTableWidgetItem(instance_coordinate))

        # 更新统计信息
        self.ui.statsCountLabel.setText(str(len(details)))

    @profiler.measure("display")
    def display(self, qimg, details=[], path='', original_rgb=None):
        if original_rgb is not None:
            self.current_display_image = original_rgb

        if self.ui.saveDataButton.isChecked():
            if hasattr(self, 'label_writer') and self.label_writer is not None:
                self.label_writer.submit(path, details, drop_if_full=True)

        qpix = QPixmap.fromImage(qimg)
        self.ui.label.setPixmap(qpix)
        self.tabel_list(details)

    # ── ROI 相关（与原版一致）──
    def set_roi_image(self):
        self.redraw_with_roi()
        if not hasattr(self, 'roi_mode') or not self.roi_mode:
            self.roi_mode = True
            self.drawing_roi = False
            self.ui.label.setCursor(Qt.CursorShape.CrossCursor)
            self.ui.label.mousePressEvent = self.roi_mouse_press
            self.ui.label.mouseMoveEvent = self.roi_mouse_move
            self.ui.label.mouseDoubleClickEvent = self.roi_mouse_double_click
            self.ui.setROIButton.setText("完成绘制")
            self.ui.setROIButton.setStyleSheet("background-color: #22c55e; color: white;")
            logger.info('进入ROI绘制模式，点击图像绘制多边形，双击完成绘制')
        else:
            self.finish_roi_drawing()

    def roi_mouse_press(self, event):
        if not self.roi_mode:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.drawing_roi:
                self.roi_points = []
                self.drawing_roi = True
            pos = event.pos()
            img_x, img_y = self.map_label_to_image(pos)
            self.roi_points.append((img_x, img_y))
            self.redraw_with_roi()
            logger.info(f'添加ROI点: ({img_x}, {img_y})')

    def roi_mouse_move(self, event):
        if not self.roi_mode or not self.drawing_roi:
            return
        self.last_mouse_pos = event.pos()
        self.redraw_with_roi()

    def roi_mouse_double_click(self, event):
        if not self.roi_mode or not self.drawing_roi:
            return
        if len(self.roi_points) >= 3:
            self.drawing_roi = False
            self.finish_roi_drawing()
            logger.info(f'完成ROI绘制，共{len(self.roi_points)}个点')

    def redraw_with_roi(self):
        if self.frame is None:
            return
        display_frame = self.frame.copy()
        display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        if hasattr(self, 'roi_points') and len(self.roi_points) > 1:
            if len(self.roi_points) >= 3:
                pts = np.array(self.roi_points, np.int32).reshape((-1, 1, 2))
                overlay = display_frame.copy()
                cv2.fillPoly(overlay, [pts], color=(255, 0, 0))
                display_frame = cv2.addWeighted(overlay, 0.3, display_frame, 0.7, 0)
                cv2.polylines(display_frame, [pts], isClosed=True, color=(255, 0, 0), thickness=2)
            for pt in self.roi_points:
                cv2.circle(display_frame, (pt[0], pt[1]), 3, (0, 0, 255), -1)
        h, w, ch = display_frame.shape
        qimg = QImage(display_frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled_pixmap = pixmap.scaled(
            self.ui.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.ui.label.setPixmap(scaled_pixmap)

    def map_label_to_image(self, label_point):
        if self.frame is None:
            return (0, 0)
        img_h, img_w = self.frame.shape[:2]
        label_w = self.ui.label.width()
        label_h = self.ui.label.height()
        pixmap = self.ui.label.pixmap()
        if pixmap is None:
            return (0, 0)
        scaled_w = pixmap.width()
        scaled_h = pixmap.height()
        offset_x = (label_w - scaled_w) // 2
        offset_y = (label_h - scaled_h) // 2
        x_in_image = label_point.x() - offset_x
        y_in_image = label_point.y() - offset_y
        if x_in_image < 0 or y_in_image < 0 or x_in_image > scaled_w or y_in_image > scaled_h:
            return (0, 0)
        scale_x = img_w / scaled_w
        scale_y = img_h / scaled_h
        return (int(x_in_image * scale_x), int(y_in_image * scale_y))

    def finish_roi_drawing(self):
        self.roi_mode = False
        self.drawing_roi = False
        self.ui.label.setCursor(Qt.CursorShape.ArrowCursor)
        self.ui.setROIButton.setText("🎯  设置围栏")
        self.ui.setROIButton.setStyleSheet("")
        if hasattr(self, 'roi_points') and len(self.roi_points) >= 3:
            self.current_roi = self.roi_points
            logger.info(f'ROI设置完成，区域包含{len(self.roi_points)}个点')
        else:
            self.current_roi = None
            logger.info('ROI绘制取消或点数不足')
        self.ui.label.mousePressEvent = None
        self.ui.label.mouseMoveEvent = None
        self.ui.label.mouseDoubleClickEvent = None

    def clear_roi_image(self):
        if hasattr(self, 'roi_mode'):
            self.roi_mode = False
        if hasattr(self, 'drawing_roi'):
            self.drawing_roi = False
        if hasattr(self, 'roi_points'):
            self.roi_points = []
        if hasattr(self, 'current_roi'):
            self.current_roi = None
        if hasattr(self, 'ui') and hasattr(self.ui, 'label'):
            self.ui.label.setCursor(Qt.CursorShape.ArrowCursor)
            self.ui.label.mousePressEvent = None
            self.ui.label.mouseMoveEvent = None
            self.ui.label.mouseDoubleClickEvent = None
        if hasattr(self, 'ui') and hasattr(self.ui, 'setROIButton'):
            self.ui.setROIButton.setText("🎯  设置围栏")
            self.ui.setROIButton.setStyleSheet("")
        if hasattr(self, 'frame') and self.frame is not None:
            frame_rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            scaled_pixmap = pixmap.scaled(
                self.ui.label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.ui.label.setPixmap(scaled_pixmap)
        logger.info('ROI区域已清除')

    def clear_image(self):
        if self.frame is not None:
            self.ui.label.setStyleSheet("background-color: #0f0f1a;")
            self.display(self.frame)

    def save_data(self):
        self.image_writer = ImageWriter(save_dir="images", maxsize=200)
        self.image_writer.start()
        self.label_writer = LabelWriter(save_dir="annotations", maxsize=200)
        self.label_writer.start()
