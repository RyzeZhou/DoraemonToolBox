"""
tqdm 进度条拦截器：从 stdout 中提取进度百分比和进度文本
"""
import re
from typing import Optional
from PySide6.QtCore import QObject, Signal, QTimer


class TqdmInterceptor(QObject):
    """
    tqdm 进度拦截器

    检测 stdout 中的 tqdm 进度行，提取百分比，并发送进度更新信号

    支持的 tqdm 格式：
    - 33%|██         | (33/100)
    - 100%|███████████| (100/100)
    """

    # tqdm 标准进度正则：匹配类似 "33%|" 或 "50.0% |"（支持整数、浮点、空格）
    TQDM_PATTERN = re.compile(r'(\d+(?:\.\d+)?)%\s*\|')
    TQDM_LINE_PATTERN = re.compile(r'[^\r\n]*\d+(?:\.\d+)?%\s*\|[^\r\n]*')
    TQDM_BAR_DETAIL_PATTERN = re.compile(r'\s*\d+(?:\.\d+)?%\s*\|[^|]*\|\s*')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_percentage = 0
        self.last_text = ""
        self.last_detail = ""
        self._buffer = ""
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush_buffer)
        self._pending_update = 0
        self._debounce_ms = 100  # 防抖延迟

    def process_output(self, text: str) -> Optional[int]:
        """
        处理输出文本，尝试提取进度百分比

        Args:
            text: 要处理的文本

        Returns:
            如果提取到进度，返回 0-100 的整数；否则返回 None
        """
        self._buffer += text

        # 尝试在缓冲区中匹配最后一条 tqdm 进度行
        line_matches = list(self.TQDM_LINE_PATTERN.finditer(self._buffer))
        match = line_matches[-1] if line_matches else None
        if match:
            try:
                line = match.group(0).strip()
                percent_match = self.TQDM_PATTERN.search(line)
                if not percent_match:
                    return None
                # 支持整数或浮点数，转换为整数百分比
                percentage = float(percent_match.group(1))
                percentage = int(round(percentage))
                # 限制在 0-100
                percentage = max(0, min(100, percentage))

                # 记录最后一次的百分比
                self.last_percentage = percentage
                self.last_text = line
                self.last_detail = self._clean_progress_detail(line)

                # 清空已处理的部分（保留最后几行以防多行进度）
                self._buffer = self._buffer[match.end():]

                # 设置防抖定时器，避免快速刷屏
                self._pending_update = percentage
                self._timer.start(self._debounce_ms)

                return percentage
            except (ValueError, TypeError):
                pass

        return None

    def _flush_buffer(self):
        """定时器触发，发出待处理的进度更新"""
        if self._pending_update != self.last_percentage:
            # 如果pending和last不同，说明有多个连续更新，取最新的
            self._pending_update = self.last_percentage

    def get_last_percentage(self) -> int:
        """获取最后一次的百分比"""
        return self.last_percentage

    def get_last_text(self) -> str:
        """获取最后一次 tqdm 进度行文本"""
        return self.last_text

    def get_last_detail(self) -> str:
        """获取去掉百分比和 ASCII 进度条后的 tqdm 文本"""
        return self.last_detail

    def _clean_progress_detail(self, line: str) -> str:
        cleaned = self.TQDM_BAR_DETAIL_PATTERN.sub(" ", line, count=1).strip()
        return re.sub(r'\s+', ' ', cleaned)

    def clean_tqdm_from_text(self, text: str) -> str:
        """
        从文本中移除 tqdm 进度行，保留业务日志

        Args:
            text: 原始文本（可能包含多行）

        Returns:
            清洗后的文本
        """
        lines = text.splitlines(keepends=True)
        cleaned_lines = []

        for line in lines:
            # 如果行看起来像 tqdm 进度行，跳过
            if self.TQDM_PATTERN.search(line) and ('|' in line or '#' in line):
                continue
            cleaned_lines.append(line)

        return ''.join(cleaned_lines)

    def flush_remaining(self) -> list[str]:
        """
        刷新缓冲区中剩余的日志行（已清洗）

        Returns:
            剩余的日志行列表（每行带换行符）
        """
        if not self._buffer.strip():
            return []

        # 清洗缓冲区内容
        cleaned = self.clean_tqdm_from_text(self._buffer)
        # 分割为行并保留换行符
        lines = cleaned.splitlines(keepends=True)
        # 清空缓冲区
        self._buffer = ""
        return lines
