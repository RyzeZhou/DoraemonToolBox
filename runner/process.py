"""
QProcess 封装：异步执行脚本，处理输出和错误
"""
import sys
import os
from pathlib import Path
from PySide6.QtCore import QProcess, QByteArray, Signal, QObject
from typing import Optional, List, Dict, Any, Callable
from utils.encoding import decode_output
from utils.path import convert_path_for_platform


class ProcessManager(QObject):
    """
    进程管理器：封装 QProcess，提供异步执行和输出处理
    """
    output_received = Signal(str)  # stdout 输出
    error_received = Signal(str)   # stderr 输出
    progress_update = Signal(int)  # 进度百分比 (0-100)
    stdin_request = Signal(str)    # 请求用户输入（询问）
    finished = Signal(int, str, str)  # 退出码, stdout, stderr
    started = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process: Optional[QProcess] = None
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._working_directory: Optional[Path] = None

    def set_working_directory(self, path: Path) -> None:
        """设置工作目录"""
        self._working_directory = Path(path)

    def start(self, script_path: Path, arguments: List[str], env: Optional[Dict[str, str]] = None) -> bool:
        """
        启动脚本

        Args:
            script_path: 脚本路径
            arguments: 命令行参数列表（格式: ['--file', 'path', '--count', '10']）
            env: 环境变量字典

        Returns:
            是否成功启动
        """
        if self.process and self.process.state() != QProcess.NotRunning:
            return False

        self.process = QProcess()
        self._stdout_buffer = ""
        self._stderr_buffer = ""

        # 合并通道：stdout 和 stderr 合并到同一个流，便于统一处理
        self.process.setProcessChannelMode(QProcess.MergedChannels)

        # 连接信号
        self.process.readyReadStandardOutput.connect(self._on_stdout_ready)
        # 注意：合并通道后 readyReadStandardError 不会发射，但保留连接无害
        self.process.readyReadStandardError.connect(self._on_stderr_ready)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        # 设置工作目录
        if self._working_directory:
            self.process.setWorkingDirectory(str(self._working_directory))

        # 设置环境变量（强制 Python 脚本使用 UTF-8 编码输出）
        proc_env = self.process.processEnvironment()
        if script_path.suffix == '.py':
            # 仅对 Python 脚本设置，避免影响其他可执行文件
            proc_env.insert('PYTHONIOENCODING', 'utf-8')
            # 同时设置 PYTHONUTF8=1（Python 3.7+）
            proc_env.insert('PYTHONUTF8', '1')
        # 合并用户自定义环境变量
        if env:
            for key, value in env.items():
                proc_env.insert(key, value)
        self.process.setProcessEnvironment(proc_env)

        # 构建命令
        # 优先使用 python 执行 .py 文件，如果是 .exe 或其他则直接执行
        script_file = str(script_path)
        if script_path.suffix == '.py':
            # 使用 sys.executable 确保使用相同的 Python 环境
            program = sys.executable
            args = [script_file] + arguments
        else:
            program = script_file
            args = arguments

        # 启动进程
        self.process.start(program, args)

        if not self.process.waitForStarted(5000):
            self.finished.emit(-1, "", f"启动失败: {self.process.errorString()}")
            return False

        self.started.emit()
        return True

    def _on_stdout_ready(self):
        """stdout 数据可读"""
        if not self.process:
            return

        data = self.process.readAllStandardOutput()
        text = decode_output(data.data())

        self._stdout_buffer += text
        self.output_received.emit(text)

    def _on_stderr_ready(self):
        """stderr 数据可读"""
        if not self.process:
            return

        data = self.process.readAllStandardError()
        text = decode_output(data.data())

        self._stderr_buffer += text
        self.error_received.emit(text)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        """进程结束"""
        stdout = self._stdout_buffer
        stderr = self._stderr_buffer
        self.finished.emit(exit_code, stdout, stderr)
        self._cleanup()

    def _on_error(self, error: QProcess.ProcessError):
        """进程错误"""
        error_msg = self.process.errorString() if self.process else "Unknown error"
        stderr = self._stderr_buffer
        self.finished.emit(-1, self._stdout_buffer, f"{stderr}\nProcess error: {error_msg}")
        self._cleanup()

    def write_stdin(self, text: str) -> None:
        """
        向进程 stdin 写入文本

        Args:
            text: 要写入的文本（会自动添加换行）
        """
        if self.process and self.process.state() == QProcess.Running:
            self.process.write(text.encode('utf-8'))
            self.process.write(b'\n')
            self.process.waitForBytesWritten(1000)

    def terminate(self, timeout: int = 5000) -> bool:
        """
        终止进程

        Args:
            timeout: 等待终止的超时时间（毫秒）

        Returns:
            是否成功终止
        """
        if not self.process or self.process.state() != QProcess.Running:
            return False

        self.process.terminate()
        if not self.process.waitForFinished(timeout):
            self.process.kill()
            return self.process.state() == QProcess.NotRunning

        return True

    def is_running(self) -> bool:
        """进程是否正在运行"""
        return self.process is not None and self.process.state() == QProcess.Running

    def get_output(self) -> str:
        """获取完整的 stdout"""
        return self._stdout_buffer

    def get_error(self) -> str:
        """获取完整的 stderr"""
        return self._stderr_buffer

    def _cleanup(self):
        """清理资源"""
        if self.process:
            self.process.deleteLater()
            self.process = None
