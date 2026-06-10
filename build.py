"""
Smart-Client 打包脚本
用法: python build.py
输出: dist/SmartClient/SmartClient.exe
"""

import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist", "SmartClient")
BUILD_DIR = os.path.join(BASE_DIR, "build")


def clean():
    """清理旧的构建产物"""
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  清理: {d}")


def build():
    """执行 PyInstaller 打包"""
    spec = os.path.join(BASE_DIR, "build.spec")
    cmd = [sys.executable, "-m", "PyInstaller", spec, "--noconfirm"]
    print(f"  执行: {' '.join(cmd)}")
    ret = subprocess.run(cmd, cwd=BASE_DIR)
    if ret.returncode != 0:
        print("❌ 打包失败")
        sys.exit(1)


def post_check():
    """检查打包结果"""
    exe = os.path.join(DIST_DIR, "SmartClient.exe")
    if os.path.exists(exe):
        size_mb = os.path.getsize(exe) / 1024 / 1024
        print(f"\n✅ 打包成功!")
        print(f"   路径: {DIST_DIR}")
        print(f"   EXE:  {exe} ({size_mb:.1f} MB)")

        # 检查模型文件（PyInstaller 6+ 放在 _internal/ 下）
        internal = os.path.join(DIST_DIR, "_internal")
        for model_dir in ["coco_yolo11n", "smart_parking"]:
            path = os.path.join(internal, "models", model_dir)
            if os.path.exists(path):
                files = os.listdir(path)
                print(f"   模型: {model_dir}/ → {files}")
            else:
                print(f"   ⚠️  模型目录缺失: {model_dir}/")

        print(f"\n发布方式:")
        print(f"   1. 将 {DIST_DIR} 整个文件夹打包为 zip")
        print(f"   2. 用户解压后双击 SmartClient.exe 即可运行")
        print(f"   3. 需要安装 VC++ 运行库（大部分 Windows 已自带）")
    else:
        print("❌ 打包产物不存在")


def main():
    print("=" * 50)
    print("  Smart-Client 打包工具")
    print("=" * 50)

    # 检查 PyInstaller
    try:
        import PyInstaller
        print(f"  PyInstaller: {PyInstaller.__version__}")
    except ImportError:
        print("❌ 请先安装 PyInstaller: pip install pyinstaller")
        sys.exit(1)

    # 检查依赖
    for pkg in ["PySide6", "cv2", "numpy", "onnxruntime", "PIL", "termcolor"]:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} 未安装")
            sys.exit(1)

    print()
    print("步骤 1/3: 清理旧构建...")
    clean()

    print("\n步骤 2/3: 打包中（可能需要 2~5 分钟）...")
    build()

    print("\n步骤 3/3: 检查结果...")
    post_check()


if __name__ == "__main__":
    main()
