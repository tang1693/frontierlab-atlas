#!/usr/bin/env python3
"""
检查 FrontierLab Atlas 所需的所有依赖
"""
import sys

print("=" * 60)
print("FrontierLab Atlas 依赖检查")
print("=" * 60)

required_packages = {
    'flask': 'Flask',
    'requests': 'requests',
    'dotenv': 'python-dotenv',
    'bs4': 'beautifulsoup4',
    'lxml': 'lxml',
}

optional_packages = {
    'feedparser': 'feedparser',
    'numpy': 'numpy',
    'cv2': 'opencv-python-headless',
    'PIL': 'Pillow',
    'gtts': 'gTTS',
    'socks': 'pysocks',
    'stem': 'stem',
}

print("\n必需依赖:")
print("-" * 60)
missing_required = []
for module, package in required_packages.items():
    try:
        __import__(module)
        print(f"✅ {package:25s} - 已安装")
    except ImportError:
        print(f"❌ {package:25s} - 未安装 (必需!)")
        missing_required.append(package)

print("\n可选依赖 (不影响核心功能):")
print("-" * 60)
for module, package in optional_packages.items():
    try:
        __import__(module)
        print(f"✅ {package:25s} - 已安装")
    except ImportError:
        print(f"⚪ {package:25s} - 未安装 (可选)")

print("\n" + "=" * 60)
if missing_required:
    print(f"❌ 缺少 {len(missing_required)} 个必需依赖:")
    for pkg in missing_required:
        print(f"   - {pkg}")
    print("\n修复命令:")
    print(f"   pip3 install {' '.join(missing_required)}")
    print("=" * 60)
    sys.exit(1)
else:
    print("✅ 所有必需依赖已安装")
    print("=" * 60)
    sys.exit(0)
