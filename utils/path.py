"""
路径工具：跨平台路径规范化，WSL/Windows 转换
"""
import os
import sys
from pathlib import Path
from typing import Union


def get_platform() -> str:
    """检测当前平台"""
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('linux') and os.path.exists('/mnt/c'):
        # 可能是 WSL
        return 'wsl'
    elif sys.platform.startswith('darwin'):
        return 'macos'
    else:
        return 'linux'


def is_wsl() -> bool:
    """是否运行在 WSL 环境"""
    return get_platform() == 'wsl'


def normalize_path(path: Union[str, Path]) -> str:
    """
    规范化路径：统一使用正斜杠，处理 ~ 展开

    Args:
        path: 原始路径

    Returns:
        规范化后的路径字符串
    """
    p = Path(path).expanduser().resolve()
    return str(p).replace('\\', '/')


def to_wsl_path(win_path: str) -> str:
    """
    将 Windows 路径转换为 WSL 路径

    例如: C:\\Users -> /mnt/c/Users
    """
    if not win_path:
        return win_path

    # 移除盘符并转小写
    path = win_path.replace('\\', '/')
    if len(path) >= 2 and path[1] == ':':
        drive = path[0].lower()
        wsl_path = f"/mnt/{drive}{path[2:]}"
        return wsl_path
    return path


def to_win_path(wsl_path: str) -> str:
    """
    将 WSL 路径转换为 Windows 路径

    例如: /mnt/c/Users -> C:\\Users
    """
    if not wsl_path.startswith('/mnt/'):
        return wsl_path.replace('/', '\\')

    parts = wsl_path[5:].split('/', 1)
    if len(parts) == 2:
        drive = parts[0].upper()
        subpath = parts[1].replace('/', '\\')
        return f"{drive}:\\{subpath}"
    return wsl_path


def path_might_be_network(path: Union[str, Path]) -> bool:
    """检查路径是否可能是网络路径（UNC）"""
    p = str(path)
    # Windows UNC 路径: \\server\share
    if p.startswith('\\\\'):
        return True
    # WSL 下 /mnt/ 通常是 Windows 盘符，不是网络
    return False


def convert_path_for_platform(path: Union[str, Path], target_platform: str = None) -> str:
    """
    根据目标平台转换路径

    Args:
        path: 原始路径
        target_platform: 目标平台（'wsl', 'windows', 'linux', 'macos'），默认自动检测

    Returns:
        转换后的路径
    """
    if target_platform is None:
        target_platform = get_platform()

    p = str(path)

    if target_platform == 'wsl':
        # 在 WSL 中运行，确保路径是 WSL 格式
        if is_wsl():
            # 如果在 WSL，且传入的是 Windows 路径，转换
            if ':' in p and '\\' in p:
                return to_wsl_path(p)
        return normalize_path(p)

    elif target_platform == 'windows':
        # 在 Windows 中运行
        if is_wsl():
            # 从 WSL 传给 Windows 脚本，需要转换
            if p.startswith('/mnt/'):
                return to_win_path(p)
        return p  # Windows 原生路径

    else:
        # Linux/macOS 原生路径
        return normalize_path(p)
