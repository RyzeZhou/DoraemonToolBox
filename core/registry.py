"""
脚本注册表：扫描、缓存和管理脚本
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from .script import ScriptConfig
from config.loader import load_config, get_config_path


class ScriptRegistry:
    """脚本注册与管理"""

    def __init__(self, script_dirs: List[Path]):
        """
        初始化注册表

        Args:
            script_dirs: 脚本目录列表
        """
        self.script_dirs = [Path(d).resolve() for d in script_dirs]
        self._scripts: Dict[str, ScriptConfig] = {}
        self._scan_errors: List[str] = []

    def scan(self) -> Dict[str, ScriptConfig]:
        """
        扫描所有脚本目录，加载配置

        Returns:
            脚本 ID 到 ScriptConfig 的映射
        """
        self._scripts.clear()
        self._scan_errors.clear()

        for script_dir in self.script_dirs:
            if not script_dir.exists():
                self._scan_errors.append(f"目录不存在: {script_dir}")
                continue

            # 扫描 .py 文件
            for py_file in script_dir.rglob('*.py'):
                try:
                    config = self._load_script_config(py_file)
                    if config:
                        # 处理 ID 冲突
                        if config.id in self._scripts:
                            # 使用更长的路径作为后缀
                            suffix = py_file.parent.name[:8]
                            new_id = f"{config.id}_{suffix}"
                            config.id = new_id
                        self._scripts[config.id] = config
                except Exception as e:
                    self._scan_errors.append(f"加载脚本失败 {py_file}: {e}")

        return self._scripts

    def _load_script_config(self, script_path: Path) -> Optional[ScriptConfig]:
        """
        加载单个脚本的配置

        优先使用同名配置文件，其次推断配置
        """
        # 1. 查找同名配置文件
        config_path = get_config_path(script_path)
        if config_path:
            config_data = load_config(config_path)
            return ScriptConfig.from_dict(config_data, script_path, config_path)

        # 2. 自动推断（从 docstring 和 argparse）
        return None

    def get_script(self, script_id: str) -> Optional[ScriptConfig]:
        """根据 ID 获取脚本配置"""
        return self._scripts.get(script_id)

    def list_scripts(self) -> List[ScriptConfig]:
        """获取所有脚本配置列表"""
        return list(self._scripts.values())

    @property
    def errors(self) -> List[str]:
        """获取扫描过程中的错误"""
        return self._scan_errors.copy()

    def add_script_dir(self, directory: Path) -> None:
        """添加新的脚本目录并重新扫描"""
        directory = Path(directory).resolve()
        if directory not in self.script_dirs:
            self.script_dirs.append(directory)

    def clear_script_dirs(self) -> None:
        """清空脚本目录列表"""
        self.script_dirs.clear()
