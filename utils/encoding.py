"""
编码工具：智能解码进程输出
"""
import chardet
from typing import Union


def decode_output(data: Union[bytes, str], default: str = 'utf-8') -> str:
    """
    智能解码字节数据为字符串

    尝试多种编码：
    1. 如果已经是 str，直接返回
    2. 尝试 UTF-8
    3. 尝试 GBK (中文 Windows)
    4. 使用 chardet 检测
    5. 使用指定默认编码

    Args:
        data: 字节数据或字符串
        default: 默认编码

    Returns:
        解码后的字符串
    """
    if isinstance(data, str):
        return data

    if not data:
        return ''

    # 尝试 UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # 尝试 GBK
    try:
        return data.decode('gbk')
    except UnicodeDecodeError:
        pass

    # 使用 chardet 检测
    try:
        result = chardet.detect(data)
        encoding = result['encoding'] or default
        confidence = result['confidence']
        if confidence > 0.5:
            return data.decode(encoding)
    except Exception:
        pass

    # 最后的 fallback
    return data.decode(default, errors='replace')
