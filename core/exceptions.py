"""
自定义异常定义
"""


class ScriptRunnerError(Exception):
    """脚本运行器基础异常"""
    pass


class ScriptNotFoundError(ScriptRunnerError):
    """脚本不存在"""
    pass


class ScriptExecutionError(ScriptRunnerError):
    """脚本执行错误"""
    def __init__(self, message: str, exit_code: int = None, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class ConfigurationError(ScriptRunnerError):
    """配置错误"""
    pass


class ValidationError(ScriptRunnerError):
    """参数验证错误"""
    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.errors = errors or []
