"""
ScriptConfig: 脚本配置数据模型
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class ScriptConfig:
    """单个脚本的配置信息"""
    id: str
    name: str
    description: str = ""
    script_path: Path = None
    config_path: Path = None
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)
    docstring: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], script_path: Path, config_path: Path) -> 'ScriptConfig':
        """
        从字典创建 ScriptConfig

        Args:
            data: 配置字典
            script_path: 脚本路径
            config_path: 配置文件路径

        Returns:
            ScriptConfig 实例
        """
        # 提取基本字段
        script_id = data.get('id', script_path.stem)
        name = data.get('name', script_path.stem)
        description = data.get('description', '')
        parameters = data.get('parameters', [])
        output = data.get('output', {})
        tags = data.get('tags', [])

        # 规范化 tags：支持 list 或逗号分隔的 string
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]

        metadata = {k: v for k, v in data.items()
                    if k not in ['id', 'name', 'description', 'script_path',
                                 'parameters', 'output', 'tags']}

        return cls(
            id=script_id,
            name=name,
            description=description,
            script_path=script_path,
            config_path=config_path,
            parameters=parameters,
            output=output,
            tags=tags,
            metadata=metadata
        )

    def get_parameter_names(self) -> List[str]:
        """获取所有参数名称"""
        return [p['name'] for p in self.parameters]

    def get_required_parameters(self) -> List[Dict[str, Any]]:
        """获取必填参数"""
        return [p for p in self.parameters if p.get('required', False)]

    def get_optional_parameters(self) -> List[Dict[str, Any]]:
        """获取可选参数"""
        return [p for p in self.parameters if not p.get('required', False)]

    def has_progress_file(self) -> bool:
        """检查是否存在断点续传文件"""
        # 根据脚本名称推测 progress 文件
        progress_file = self.script_path.with_suffix('.progress.json')
        return progress_file.exists()
