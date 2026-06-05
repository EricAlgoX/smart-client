import os
import json
import csv
import threading
from datetime import datetime
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox, QTreeWidgetItem, QFileDialog
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from core.client import StartClient
from utils.logger import logger
from core.converter import ImageConverter
from utils.profiler import profiler
from core.server import start_server, stop_all_servers
from core.stream import select_image, select_stream
from core.queue import image_queue, result_queue
from ui.settings_dialog import SettingsDialog


class MainController:
    """产品通版控制器：场景切换 / 源管理 / 告警流 / 检测记录"""

    def __init__(self, window):
        self.window = window
        self.ui = window
        self.roi_points = []
        self.frame = None
        self.converter = None
        self.current_scene = None
        self.alert_count = 0
        self._sources = {}

        # 检测记录
        self.records = []  # [{'time', 'scene', 'type', 'detail', 'frame'}]

        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.next)

        # 默认参数
        self._nms = 0.5
        self._confidence = 0.3
        self._timeout = 3

        # 加载场景和 API
        self._load_scenes()
        self._load_api()
        self._setup_connections()

    # ────────────────────────────────────────
    #  初始化
    # ────────────────────────────────────────
    def _load_scenes(self):
        """加载场景配置"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scenes.json")
            with open(config_path, "r", encoding="utf-8") as f:
                self.scenes = json.load(f)
            for key, scene in self.scenes.items():
                self.ui.sceneBox.addItem(f"{scene['icon']}  {scene['name']}", key)
        except Exception as e:
            logger.error(f"加载场景配置失败: {e}")
            self.scenes = {}

    def _load_api(self):
        """加载 API 配置"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api.json")
            with open(config_path, "r", encoding="utf-8") as f:
                self.api = json.load(f)
        except Exception as e:
            logger.error(f"加载 api.json 失败: {e}")
            self.api = {}

    def _setup_connections(self):
        """绑定所有信号"""
        ui = self.ui

        # 工具栏
        ui.tb_act_image.triggered.connect(lambda: self.select_source("image"))
        ui.tb_act_camera.triggered.connect(lambda: self.select_source("camera"))
        ui.tb_act_start.triggered.connect(self.startDetection)
        ui.tb_act_stop.triggered.connect(self._stop_detection)
        ui.tb_act_settings.triggered.connect(self._open_settings)

        # 场景切换
        ui.sceneBox.currentIndexChanged.connect(self._on_scene_changed)

        # 导出记录
        ui.btnExportRecords.clicked.connect(self._export_records)

    # ────────────────────────────────────────
    #  场景切换
    # ────────────────────────────────────────
    def _on_scene_changed(self, index):
        """切换检测场景"""
        scene_key = self.ui.sceneBox.currentData()
        if not scene_key or scene_key not in self.scenes:
            return

        self.current_scene = self.scenes[scene_key]
        scene_name = self.current_scene['name']

        # 停止旧服务
        stop_all_servers()

        # 启动场景关联的模型服务
        for model_name in self.current_scene.get('models', []):
            if model_name in self.api:
                threading.Thread(
                    target=start_server,
                    args=(model_name,),
                    daemon=True
                ).start()

        # 更新状态栏
        self.ui.statusSceneLabel.setText(f"场景: {scene_name}")
        self.ui.statsSceneLabel.setText(scene_name)
        self.ui.log_edit.append(f"已切换场景: {scene_name}")

        # 如果已有源，重新创建客户端
        if hasattr(self, '_current_source_type') and self._current_source_type:
            self._create_client()

    # ────────────────────────────────────────
    #  源管理
    # ────────────────────────────────────────
    def select_source(self, source_type):
        """选择输入源"""
        self._current_source_type = source_type

        if source_type == "image":
            result = select_image(self)
        elif source_type == "camera":
            result = select_stream(self)
        else:
            return

        # 异步连接（视频流）
        if result and 'worker' in result:
            # 停掉旧的连接线程
            if hasattr(self, '_connect_worker') and self._connect_worker is not None:
                self._connect_worker.terminate()
                self._connect_worker.wait(1000)
                self._connect_worker = None

            worker = result['worker']
            self._connect_worker = worker  # 持有引用，防止 GC 回收
            source_name = result['stream_name']
            self.ui.log_edit.append(f"正在连接摄像头: {source_name} ...")
            self.ui.label.setText("⏳ 正在连接摄像头...")
            self.ui.label.setStyleSheet("color: #60a5fa; font-size: 16px; background: #0f0f1a;")
            worker.finished.connect(lambda stream, frame, fname: self._on_stream_connected(stream, frame, fname, source_name))
            worker.error.connect(self._on_stream_error)
            worker.start()
            return

        # 同步结果（图片）
        if result and 'frame' in result:
            self._activate_source(result)
        elif result is None:
            pass
        else:
            QMessageBox.critical(self.window, "错误", "无法加载输入源")

    def _on_stream_connected(self, stream, frame, frame_name, source_name):
        """摄像头连接成功"""
        self.source = {
            'stream': stream,
            'stream_name': source_name,
            'frame': frame,
            'frame_name': frame_name,
        }
        self._activate_source(self.source)
        # 自动开始检测
        self.start_flag = True
        self.timer.start(33)
        self.ui.log_edit.append(f"✅ 摄像头已连接: {source_name}，自动开始检测")

    def _on_stream_error(self, error_msg):
        """摄像头连接失败"""
        self.ui.label.setText("连接失败，请重试")
        self.ui.label.setStyleSheet("color: #ef4444; font-size: 14px; background: #0f0f1a;")
        self.ui.log_edit.append(f"❌ 连接失败: {error_msg}")
        QMessageBox.critical(self.window, "连接失败", error_msg)

    def _activate_source(self, source):
        """源就绪后初始化显示"""
        name = source["stream_name"]
        self.source = source
        self.ui.log_edit.append(f"已选择: {name}")

        self.ui.show_video()
        self.ui.label.setStyleSheet("background-color: transparent;")
        self.ui.set_status_connected(str(name))

        result_queue.put((source['frame'], [], source['frame_name']))

        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(result_queue, self._get_label_size, fps_limit=20)
        self.converter.pixmap_ready.connect(self.display)
        self.converter.start()

        self._create_client()

    def _create_client(self):
        """为当前场景和源创建推理客户端"""
        if not self.current_scene:
            self.ui.log_edit.append("请先选择检测场景")
            return

        models = self.current_scene.get('models', [])
        if not models:
            return

        # 停掉旧的推理线程
        if hasattr(self, 'client_thread') and self.client_thread is not None:
            self.client_thread.terminate()
            self.client_thread.wait(1000)
            self.client_thread = None

        # 使用第一个模型作为主模型
        model_name = models[0]
        if model_name not in self.api:
            self.ui.log_edit.append(f"模型 {model_name} 未配置 API")
            return

        self.client_thread = StartClient(
            url=self.api[model_name],
            input_queue=image_queue,
            nms=self._nms,
            polygon=self.roi_points,
            confidence=self._confidence,
            timeout_mins=self._timeout,
        )
        self.client_thread.start()
        self.ui.log_edit.append(f"推理客户端已就绪: {model_name}")

    def _get_label_size(self):
        try:
            return self.ui.label.size()
        except Exception:
            return None

    # ────────────────────────────────────────
    #  推理控制
    # ────────────────────────────────────────
    def startDetection(self):
        if not hasattr(self, 'source') or self.source is None:
            self.ui.log_edit.append("请先接入摄像头或打开图片")
            return
        if not hasattr(self, 'client_thread'):
            self.ui.log_edit.append("请先选择检测场景")
            return

        if self._current_source_type == "image":
            image_queue.put((self.source['frame'], self.source['frame_name']))
            return

        # 摄像头模式：切换播放/暂停
        if not self.start_flag:
            self.start_flag = True
            try:
                image_queue.put((self.source['frame'], self.source['frame_name']))
            except:
                pass
            self.timer.start(33)
        else:
            self.start_flag = False
            self.timer.stop()

    def _stop_detection(self):
        self.start_flag = False
        self.timer.stop()
        self.ui.log_edit.append("检测已停止")

    @profiler.measure("next")
    def next(self):
        self.source['frame'], self.source['frame_name'] = self.source['stream'].read()
        if self.source['frame'] is None:
            self.timer.stop()
            self.start_flag = False
            self.ui.log_edit.append("视频流已结束")
            return

        if hasattr(self, "client_thread") and self.start_flag:
            try:
                image_queue.put((self.source['frame'], self.source['frame_name']))
            except Exception as e:
                logger.error(e)
        else:
            try:
                result_queue.put((self.source['frame'], [], self.source['frame_name']))
            except:
                pass

    # ────────────────────────────────────────
    #  显示与告警
    # ────────────────────────────────────────
    @profiler.measure("display")
    def display(self, qimg, details=[], path='', original_rgb=None):
        if original_rgb is not None:
            self.current_display_image = original_rgb

        qpix = QPixmap.fromImage(qimg)
        self.ui.label.setPixmap(qpix)

        # 处理检测结果
        if details:
            self._process_alerts(details)
            self._update_records(details)
            self._update_stats(details)

    def _process_alerts(self, details):
        """处理告警：在右侧告警列表中显示"""
        scene_key = self.ui.sceneBox.currentData()
        scene = self.scenes.get(scene_key, {})
        alert_rules = scene.get('alert_rules', {})

        for det in details:
            class_name = det.get('class', '')
            score = float(det.get('score', 0))
            level = alert_rules.get(class_name, 'info')

            # 只有超过置信度阈值的才显示
            if score < self._confidence:
                continue

            level_map = {
                'critical': ('🔴', '严重'),
                'alert': ('🟠', '告警'),
                'warning': ('🟡', '注意'),
                'info': ('🟢', '信息'),
            }
            icon, level_text = level_map.get(level, ('⚪', '信息'))

            now = datetime.now().strftime("%H:%M:%S")
            item = QTreeWidgetItem([
                now,
                f"{icon} {level_text}",
                f"{class_name} ({score:.0%})"
            ])
            self.ui.alertList.insertTopLevelItem(0, item)

            # 限制告警列表长度
            if self.ui.alertList.topLevelItemCount() > 100:
                self.ui.alertList.takeTopLevelItem(100)

            if level in ('critical', 'alert'):
                self.alert_count += 1

    def _update_records(self, details):
        """更新检测记录表"""
        now = datetime.now().strftime("%H:%M:%S")
        scene_name = self.current_scene['name'] if self.current_scene else '--'

        for det in details:
            class_name = det.get('class', '')
            score = float(det.get('score', 0))
            if score < self._confidence:
                continue

            row = self.ui.recordTable.rowCount()
            self.ui.recordTable.insertRow(row)
            self.ui.recordTable.setItem(row, 0, QTableWidgetItem(now))
            self.ui.recordTable.setItem(row, 1, QTableWidgetItem(scene_name))
            self.ui.recordTable.setItem(row, 2, QTableWidgetItem(class_name))
            self.ui.recordTable.setItem(row, 3, QTableWidgetItem(f"{score:.0%}"))
            self.ui.recordTable.setItem(row, 4, QTableWidgetItem("📷"))

            # 保存到内存
            self.records.append({
                'time': now,
                'scene': scene_name,
                'type': class_name,
                'detail': f"{score:.0%}",
            })

            # 限制表格行数
            if self.ui.recordTable.rowCount() > 500:
                self.ui.recordTable.removeRow(0)

    def _update_stats(self, details):
        """更新统计面板"""
        count = len([d for d in details if float(d.get('score', 0)) >= self._confidence])
        total = int(self.ui.statsCountLabel.text() or 0) + count
        self.ui.statsCountLabel.setText(str(total))
        self.ui.statsAlertLabel.setText(str(self.alert_count))

    # ────────────────────────────────────────
    #  设置
    # ────────────────────────────────────────
    def _open_settings(self):
        """打开设置弹窗"""
        dlg = SettingsDialog(
            self.window,
            nms=self._nms,
            confidence=self._confidence,
            timeout=self._timeout,
        )
        if dlg.exec():
            self._nms = dlg.nmsSpin.value()
            self._confidence = dlg.conSpin.value()
            self._timeout = dlg.timeoutSpin.value()
            self.ui.log_edit.append(
                f"设置已更新: NMS={self._nms:.2f}, 置信度={self._confidence:.2f}, 超时={self._timeout}s"
            )

    # ────────────────────────────────────────
    #  导出
    # ────────────────────────────────────────
    def _export_records(self):
        """导出检测记录为 CSV"""
        if not self.records:
            QMessageBox.information(self.window, "提示", "暂无检测记录可导出")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self.window, "导出记录", f"detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV 文件 (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['time', 'scene', 'type', 'detail'])
                writer.writeheader()
                writer.writerows(self.records)
            self.ui.log_edit.append(f"✅ 记录已导出: {file_path}")
            QMessageBox.information(self.window, "导出成功", f"已导出 {len(self.records)} 条记录")
        except Exception as e:
            self.ui.log_edit.append(f"❌ 导出失败: {e}")
