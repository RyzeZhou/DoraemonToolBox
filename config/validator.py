"""
参数验证器
"""
from typing import Dict, Any, List, Optional
from pathlib import Path


class ValidationError(Exception):
    """参数验证失败异常"""
    pass


def validate_parameters(params: Dict[str, Any], schema: List[Dict[str, Any]]) -> List[str]:
    """
    验证参数是否符合 schema 定义

    Args:
        params: 用户输入的参数字典 {name: value}
        schema: 参数定义列表（来自配置）

    Returns:
        错误消息列表，空列表表示验证通过
    """
    errors = []

    # 构建参数快速查找表
    param_map = {p['name']: p for p in schema}

    for param_def in schema:
        name = param_def['name']
        required = param_def.get('required', False)
        value = params.get(name)

        # 必填检查
        if required and (value is None or value == ''):
            errors.append(f"参数 '{param_def.get('label', name)}' 是必填项")
            continue

        # 如果值为空且非必填，跳过后续验证
        if value is None or value == '':
            continue

        # 类型特定验证
        ptype = param_def.get('type', 'string')
        try:
            if ptype in ['file', 'directory']:
                path = Path(value)
                if not path.exists():
                    errors.append(f"参数 '{param_def.get('label', name)}' 路径不存在: {value}")
        except Exception as e:
            errors.append(f"参数 '{name}' 验证出错: {e}")

    return errors
