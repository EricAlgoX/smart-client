import os
import json
import csv
from datetime import datetime
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox, QTreeWidgetItem, QFileDialog, QMenu
from PySide6.QtGui import QPixmap
from core.stream_session import StreamSession
from core.stream_manager import StreamManager
from engine.manager import engine_manager
from utils.logger import logger
from utils.profiler import profiler
from core.stream import select_image, select_video, select_stream
from ui.settings_dialog import SettingsDialog


class MainController:
    """多流控制器：场景切换 / 流管理 / 告警 / 记录"""

    def __init__(self, window):
        self.window = window
        self.ui = window
        self.current_scene = None
        self.alert_count = 0

        # 多流管理
        self.stream_manager = StreamManager()
        self._workers = []  # 持有 worker 引用，防止 GC

        # 默认参数
        self._nms = 0.5
        self._confidence = 0.3
        self._timeout = 3

        # 加载场景
        self._load_scenes()
        self._setup_connections()

        # 默认加载第一个场景
        if self.ui.sceneBox.count() > 0:
            self._on_scene_changed(0)

    # ────────────────────────────────────────
    #  路径查找（兼容打包后和开发环境）
    # ────────────────────────────────────────
    @staticmethod
    def _find_file(relative_path: str) -> str:
        import sys
        candidates = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "_internal", relative_path))
            candidates.append(os.path.join(exe_dir, relative_path))
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), relative_path))
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[-1]

    # ────────────────────────────────────────
    #  初始化
    # ────────────────────────────────────────
    def _load_scenes(self):
        try:
            config_path = self._find_file("scenes.json")
            with open(config_path, "r", encoding="utf-8") as f:
                self.scenes = json.load(f)
            for key, scene in self.scenes.items():
                self.ui.sceneBox.addItem(f"{scene['icon']}  {scene['name']}", key)
        except Exception as e:
            logger.error(f"加载场景配置失败: {e}")
            self.scenes = {}

    def _setup_connections(self):
        ui = self.ui

        # 工具栏
        ui.tb_act_image.triggered.connect(lambda: self.select_source("image"))
        ui.tb_act_video.triggered.connect(lambda: self.select_source("video"))
        ui.tb_act_camera.triggered.connect(lambda: self.select_source("camera"))
        ui.tb_act_start.triggered.connect(self.startDetection)
        ui.tb_act_stop.triggered.connect(self._stop_detection)
        ui.tb_act_settings.triggered.connect(self._open_settings)

        # 场景切换
        ui.sceneBox.currentIndexChanged.connect(self._on_scene_changed)

        # 流标签栏
        ui.btnAddStream.clicked.connect(self._show_add_stream_menu)

        # 导出记录
        ui.btnExportRecords.clicked.connect(self._export_records)

    # ────────────────────────────────────────
    #  场景切换
    # ────────────────────────────────────────
    def _on_scene_changed(self, index):
        scene_key = self.ui.sceneBox.currentData()
        if not scene_key or scene_key not in self.scenes:
            return

        self.current_scene = self.scenes[scene_key]
        scene_name = self.current_scene['name']

        success = engine_manager.load_scene(scene_key)
        if success:
            self.ui.log_edit.append(f"已切换场景: {scene_name}")
        else:
            self.ui.log_edit.append(f"❌ 场景切换失败: {scene_name}")

        self.ui.statusSceneLabel.setText(f"场景: {scene_name}")
        self.ui.statsSceneLabel.setText(scene_name)

    # ────────────────────────────────────────
    #  ＋ 按钮：弹出菜单选择源类型
    # ────────────────────────────────────────
    def _show_add_stream_menu(self):
        menu = QMenu(self.window)
        act_img = menu.addAction("📷  打开图片")
        act_vid = menu.addAction("🎬  打开视频")
        act_cam = menu.addAction("📡  接入摄像头")

        action = menu.exec(self.ui.btnAddStream.mapToGlobal(
            self.ui.btnAddStream.rect().bottomLeft()
        ))

        if action == act_img:
            self.select_source("image")
        elif action == act_vid:
            self.select_source("video")
        elif action == act_cam:
            self.select_source("camera")

    # ────────────────────────────────────────
    #  源选择 → 创建 StreamSession
    # ────────────────────────────────────────
    def select_source(self, source_type):
        if source_type == "image":
            result = select_image(self)
        elif source_type == "video":
            result = select_video(self)
        elif source_type == "camera":
            result = select_stream(self)
        else:
            return

        # 异步连接（摄像头/视频流）
        if result and 'worker' in result:
            # 防止重复连接
            if hasattr(self, '_connect_worker') and self._connect_worker is not None:
                if self._connect_worker.isRunning():
                    logger.warning("[Controller] 已有连接进行中，跳过")
                    return
                self._connect_worker = None

            worker = result['worker']
            self._connect_worker = worker
            source_name = result['stream_name']
            self.ui.log_edit.append(f"正在连接: {source_name} ...")
            self.ui.label.setText("⏳ 正在连接...")
            self.ui.label.setStyleSheet("color: #60a5fa; font-size: 16px; background: transparent;")
            worker.finished.connect(
                lambda stream, frame, fname: self._on_stream_connected(stream, frame, fname, source_name))
            worker.error.connect(self._on_stream_error)
            worker.start()
            logger.info(f"[Controller] worker 已启动")
            return

        # 同步结果（图片/视频）
        if result and 'frame' in result:
            self._create_session(result, source_type)
        elif result is None:
            pass
        else:
            QMessageBox.critical(self.window, "错误", "无法加载输入源")

    def _on_stream_connected(self, stream, frame, frame_name, source_name):
        """摄像头连接成功"""
        result = {
            'stream': stream,
            'stream_name': source_name,
            'frame': frame,
            'frame_name': frame_name,
        }
        self._create_session(result, "camera")

    def _on_stream_error(self, error_msg):
        self.ui.label.setText("连接失败，请重试")
        self.ui.label.setStyleSheet("color: #ef4444; font-size: 14px; background: transparent;")
        self.ui.log_edit.append(f"❌ 连接失败: {error_msg}")
        QMessageBox.critical(self.window, "连接失败", error_msg)

    def _create_session(self, source, source_type):
        """创建 StreamSession 并添加到管理器"""
        name = str(source['stream_name'])

        session = StreamSession(
            name=name,
            video_stream=source['stream'],
            first_frame=source['frame'],
            frame_name=source['frame_name'],
            source_type=source_type,
        )

        # 注册到管理器
        session_name = self.stream_manager.add(session)

        # 添加 UI 标签
        self.ui.add_stream_tab(
            session_name,
            on_click=self._on_tab_clicked,
            on_close=self._on_tab_close,
        )

        # 切换到新 session
        self._switch_to_session(session_name)

        # 启动推理
        if engine_manager.is_loaded:
            session.start_inference(
                confidence=self._confidence,
                nms=self._nms,
            )
            self.ui.log_edit.append(f"✅ {session_name} 已连接，推理已启动")
        else:
            self.ui.log_edit.append(f"✅ {session_name} 已连接，请选择场景后开始推理")

        # 视频/摄像头自动开始
        if source_type in ("video", "camera"):
            session.running = True
            session.timer.start(33)

    # ────────────────────────────────────────
    #  流标签操作
    # ────────────────────────────────────────
    def _on_tab_clicked(self, name):
        """点击标签切换"""
        self._switch_to_session(name)

    def _on_tab_close(self, name):
        """关闭标签"""
        session = self.stream_manager.get(name)
        if session:
            session.cleanup()
        self.stream_manager.remove(name)
        self.ui.remove_stream_tab(name)
        self.ui.log_edit.append(f"已关闭: {name}")

        # 切换到剩余的某个 session
        active = self.stream_manager.get_active()
        if active:
            self._switch_to_session(active.name)
        else:
            self.ui.show_placeholder()
            self.ui.set_status_disconnected()

    def _switch_to_session(self, name):
        """切换到指定 session"""
        self.stream_manager.switch_to(
            name,
            display_callback=self.display,
            get_label_size=self._get_label_size,
        )
        self.ui.switch_stream_tab(name)
        self.ui.show_video()
        self.ui.set_status_connected(name)

        # 刷新告警和记录显示
        session = self.stream_manager.get_active()
        if session:
            self._refresh_alerts(session)
            self._refresh_records(session)

    # ────────────────────────────────────────
    #  推理控制（操作 active session）
    # ────────────────────────────────────────
    def startDetection(self):
        session = self.stream_manager.get_active()
        if session is None:
            self.ui.log_edit.append("请先接入视频源")
            return
        if not engine_manager.is_loaded:
            self.ui.log_edit.append("请先选择检测场景")
            return

        if session.source_type == "image":
            session.image_queue.put((session.first_frame, session.frame_name))
            return

        if not session.running:
            session.running = True
            session.timer.start(33)
            if session.inference_worker is None:
                session.start_inference(self._confidence, self._nms)
        else:
            session.running = False
            session.timer.stop()

    def _stop_detection(self):
        session = self.stream_manager.get_active()
        if session:
            session.running = False
            session.timer.stop()
            self.ui.log_edit.append(f"检测已停止: {session.name}")

    # ────────────────────────────────────────
    #  显示回调（active session 的 converter 触发）
    # ────────────────────────────────────────
    @profiler.measure("display")
    def display(self, qimg, details=[], path='', original_rgb=None):
        if original_rgb is not None:
            self.current_display_image = original_rgb

        qpix = QPixmap.fromImage(qimg)
        self.ui.label.setPixmap(qpix)

        if details:
            session = self.stream_manager.get_active()
            if session:
                self._process_alerts(details, session)
                self._update_records(details, session)
                self._update_stats(details, session)

    def _process_alerts(self, details, session):
        scene_key = self.ui.sceneBox.currentData()
        scene = self.scenes.get(scene_key, {})
        alert_rules = scene.get('alert_rules', {})

        for det in details:
            class_name = det.get('class', '')
            score = float(det.get('score', 0))
            ocr_text = det.get('text', '')
            level = alert_rules.get(class_name, 'info')
            if score < self._confidence:
                continue

            level_map = {
                'critical': ('🔴', '严重'), 'alert': ('🟠', '告警'),
                'warning': ('🟡', '注意'), 'info': ('🟢', '信息'),
            }
            icon, level_text = level_map.get(level, ('⚪', '信息'))
            detail_text = ocr_text if ocr_text else f"{class_name} ({score:.0%})"
            now = datetime.now().strftime("%H:%M:%S")

            item = QTreeWidgetItem([now, f"{icon} {level_text}", detail_text])
            self.ui.alertList.insertTopLevelItem(0, item)
            if self.ui.alertList.topLevelItemCount() > 100:
                self.ui.alertList.takeTopLevelItem(100)

            if level in ('critical', 'alert'):
                session.alert_count = getattr(session, 'alert_count', 0) + 1
                self.alert_count += 1

    def _update_records(self, details, session):
        now = datetime.now().strftime("%H:%M:%S")
        scene_name = self.current_scene['name'] if self.current_scene else '--'

        for det in details:
            class_name = det.get('class', '')
            score = float(det.get('score', 0))
            ocr_text = det.get('text', '')
            if score < self._confidence:
                continue

            detail_text = ocr_text if ocr_text else f"{score:.0%}"
            row = self.ui.recordTable.rowCount()
            self.ui.recordTable.insertRow(row)
            self.ui.recordTable.setItem(row, 0, QTableWidgetItem(now))
            self.ui.recordTable.setItem(row, 1, QTableWidgetItem(scene_name))
            self.ui.recordTable.setItem(row, 2, QTableWidgetItem(class_name))
            self.ui.recordTable.setItem(row, 3, QTableWidgetItem(detail_text))
            self.ui.recordTable.setItem(row, 4, QTableWidgetItem("📷"))

            session.records.append({
                'time': now, 'scene': scene_name,
                'type': class_name, 'detail': detail_text,
            })

            if self.ui.recordTable.rowCount() > 500:
                self.ui.recordTable.removeRow(0)

    def _update_stats(self, details, session):
        count = len([d for d in details if float(d.get('score', 0)) >= self._confidence])
        total = int(self.ui.statsCountLabel.text() or 0) + count
        self.ui.statsCountLabel.setText(str(total))
        self.ui.statsAlertLabel.setText(str(self.alert_count))

    def _refresh_alerts(self, session):
        """切换 session 时刷新告警区（当前简化：清空）"""
        self.ui.alertList.clear()

    def _refresh_records(self, session):
        """切换 session 时刷新记录表"""
        self.ui.recordTable.setRowCount(0)
        for rec in session.records:
            row = self.ui.recordTable.rowCount()
            self.ui.recordTable.insertRow(row)
            self.ui.recordTable.setItem(row, 0, QTableWidgetItem(rec['time']))
            self.ui.recordTable.setItem(row, 1, QTableWidgetItem(rec['scene']))
            self.ui.recordTable.setItem(row, 2, QTableWidgetItem(rec['type']))
            self.ui.recordTable.setItem(row, 3, QTableWidgetItem(rec['detail']))
            self.ui.recordTable.setItem(row, 4, QTableWidgetItem("📷"))

    def _get_label_size(self):
        try:
            return self.ui.label.size()
        except Exception:
            return None

    # ────────────────────────────────────────
    #  设置
    # ────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(
            self.window, nms=self._nms,
            confidence=self._confidence, timeout=self._timeout,
        )
        if dlg.exec():
            self._nms = dlg.nmsSpin.value()
            self._confidence = dlg.conSpin.value()
            self._timeout = dlg.timeoutSpin.value()
            # 更新当前 active session 的参数
            session = self.stream_manager.get_active()
            if session and session.inference_worker:
                session.inference_worker.confidence = self._confidence
                session.inference_worker.nms = self._nms
            self.ui.log_edit.append(
                f"设置已更新: NMS={self._nms:.2f}, 置信度={self._confidence:.2f}"
            )

    # ────────────────────────────────────────
    #  导出
    # ────────────────────────────────────────
    def _export_records(self):
        session = self.stream_manager.get_active()
        records = session.records if session else []
        if not records:
            QMessageBox.information(self.window, "提示", "暂无检测记录可导出")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self.window, "导出记录",
            f"detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV 文件 (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['time', 'scene', 'type', 'detail'])
                writer.writeheader()
                writer.writerows(records)
            self.ui.log_edit.append(f"✅ 记录已导出: {file_path}")
        except Exception as e:
            self.ui.log_edit.append(f"❌ 导出失败: {e}")

    def cleanup(self):
        self.stream_manager.cleanup_all()
        engine_manager.unload()
