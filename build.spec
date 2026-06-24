# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Smart-Client Windows 打包配置

import os

block_cipher = None
base_dir = os.path.dirname(os.path.abspath(SPEC))

def res(rel_path):
    return os.path.join(base_dir, rel_path)

a = Analysis(
    ['app.py'],
    pathex=[base_dir],
    binaries=[],
    datas=[
        (res('resources/style.qss'), 'resources'),
        (res('resources/app.ico'), 'resources'),
        (res('scenes.json'), '.'),
        (res('models/coco_yolo11n/config.json'), 'models/coco_yolo11n'),
        (res('models/coco_yolo11n/detect.onnx'), 'models/coco_yolo11n'),
        (res('models/smart_parking/config.json'), 'models/smart_parking'),
        (res('models/smart_parking/plate_recognition.onnx'), 'models/smart_parking'),
        (res('models/smart_parking/plate_ocr.onnx'), 'models/smart_parking'),
    ],
    hiddenimports=[
        'engine.onnx_engine',
        'engine.plate_ocr_engine',
        'engine.pipeline',
        'engine.manager',
        'engine.base',
        'core.stream_session',
        'core.stream_manager',
        'core.converter',
        'core.inference_worker',
        'core.stream',
        'core.queue',
        'ui.main_controller',
        'ui.settings_dialog',
        'utils.logger',
        'utils.general',
        'utils.profiler',
        'info',
        'cv2',
        'numpy',
        'PIL',
        'termcolor',
        'onnxruntime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'tensorflow', 'matplotlib', 'scipy',
        'pandas', 'sklearn', 'jupyter', 'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SmartClient',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=res('resources/app.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartClient',
)
