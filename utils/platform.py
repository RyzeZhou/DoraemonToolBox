"""
平台检测和特性判断
"""
import os
import sys
from typing import Dict, Any


def get_platform_info() -> Dict[str, Any]:
    """
    获取当前平台信息

    Returns:
        包含 platform, is_wsl, is_windows, is_linux, is_macos 的字典
    """
    platform = sys.platform
    is_windows = platform.startswith('win')
    is_linux = platform.startswith('linux')
    is_macos = platform.startswith('darwin')
    is_wsl = is_linux and os.path.exists('/proc/version') and 'microsoft' in open('/proc/version', 'r').read().lower()

    return {
        'platform': platform,
        'is_windows': is_windows,
        'is_linux': is_linux,
        'is_macos': is_macos,
        'is_wsl': is_wsl,
        'sys_ver': sys.version,
    }
