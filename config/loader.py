"""
配置加载器：支持 YAML 和 JSON 格式
"""
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional


def load_config(config_path: Path) -> Dict[str, Any]:
    """
    加载配置文件（YAML 或 JSON）

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置格式错误
    """
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    suffix = config_path.suffix.lower()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f) or {}
            elif suffix == '.json':
                return json.load(f)
            else:
                # 尝试 YAML 作为 fallback
                return yaml.safe_load(f) or {}
    except Exception as e:
        raise ValueError(f"配置文件解析失败 {config_path}: {e}")


def save_config(config: Dict[str, Any], config_path: Path, format: str = 'yaml') -> None:
    """保存配置到文件"""
    with open(config_path, 'w', encoding='utf-8') as f:
        if format == 'yaml':
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        elif format == 'json':
            json.dump(config, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"不支持的格式: {format}")


def get_config_path(script_path: Path) -> Optional[Path]:
    """
    根据脚本路径查找对应的配置文件

    查找顺序：
    1. script_path.with_suffix('.yaml')
    2. script_path.with_suffix('.json')
    3. script_path.stem + '.yaml' 同名文件
    """
    # 同名配置文件
    yaml_path = script_path.with_suffix('.yaml')
    json_path = script_path.with_suffix('.json')

    if yaml_path.exists():
        return yaml_path
    if json_path.exists():
        return json_path

    # 检查同名的其他格式（如 script_config.yaml）
    stem = script_path.stem
    for suffix in ['.yaml', '.yml', '.json']:
        alt_path = script_path.parent / f"{stem}{suffix}"
        if alt_path.exists():
            return alt_path

    return None
