from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox, QSpinBox, QDialogButtonBox,
)


class SettingsDialog(QDialog):
    """设置弹窗：NMS / 置信度 / 超时"""

    def __init__(self, parent=None, nms=0.5, confidence=0.3, timeout=3):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(360)
        self.setObjectName("settingsDialog")

        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.nmsSpin = QDoubleSpinBox()
        self.nmsSpin.setRange(0, 1)
        self.nmsSpin.setSingleStep(0.05)
        self.nmsSpin.setValue(nms)
        layout.addRow("重叠度 (NMS):", self.nmsSpin)

        self.conSpin = QDoubleSpinBox()
        self.conSpin.setRange(0, 1)
        self.conSpin.setSingleStep(0.05)
        self.conSpin.setValue(confidence)
        layout.addRow("置信度阈值:", self.conSpin)

        self.timeoutSpin = QSpinBox()
        self.timeoutSpin.setRange(1, 300)
        self.timeoutSpin.setValue(timeout)
        self.timeoutSpin.setSuffix(" 秒")
        layout.addRow("超时时间:", self.timeoutSpin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
