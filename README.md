# 哆啦A梦百宝箱

Python 脚本可视化运行中台，支持 YAML 配置化脚本管理、内置终端交互、深色/浅色主题。
**注意：本项目代码由AI生成**
---

## 功能特性

### 脚本管理
- **YAML 配置驱动**：每个脚本配套 `.yaml` 文件，定义参数类型、默认值、约束条件
- **参数控件自动生成**：根据 YAML 类型（file / directory / string / int / float / bool / choice / list）自动渲染输入控件，支持拖拽
- **参数缓存**：关闭后自动保存上次填入值，重启无需重新填写

### 内置终端
- **进度条捕获**：正则识别 tqdm 进度输出，实时显示百分比进度条
- **stdin 交互**：自动检测脚本中的询问（是否继续？/Continue?/请输入:），弹出对话框注入用户输入
- **彩色输出**：终端支持颜色渲染

### 主题与界面
- **深色/浅色主题切换**：QSS 样式表，实时热切换
- **高 DPI 适配**：窗口可自由缩放，控件自动响应

---

## 目录结构

```
├── main.py              # 应用入口，PySide6 主窗口
├── config/
│   ├── loader.py        # YAML 配置加载
│   └── validator.py     # 参数校验
├── core/
│   ├── registry.py      # 脚本注册表（扫描/过滤/选中）
│   ├── script.py        # 脚本对象模型
│   └── exceptions.py
├── runner/
│   ├── process.py       # QProcess 执行管理
│   ├── stdin_handler.py # stdin 交互弹窗
│   └── tqdm_interceptor.py  # tqdm 输出捕获
├── widgets/
│   ├── parameters.py    # 参数表单控件（按类型渲染）
│   ├── terminal.py      # 内置 QTermWidget 终端
│   └── progress.py
├── styles/
│   ├── dark.qss
│   └── light.qss
└── scripts/             # 放置运行脚本和YAML配置文件
```

---

## 环境要求

- Python 3.9+
- PySide6
- PyYAML
- QTermWidget（可选，终端功能）

安装依赖：
```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

---

## 脚本配置格式

每个脚本对应一个 `.yaml` 文件，放在 `scripts/` 目录：

```yaml
name: 示例脚本
description: 将输入文件做处理后输出
params:
  - name: input_file
    type: file
    label: 输入文件
    required: true
  - name: threads
    type: int
    label: 线程数
    default: 4
    min: 1
    max: 32
  - name: verbose
    type: bool
    label: 详细输出
    default: false
```

支持的参数类型：`file`、`directory`、`multi_file`、`string`、`int`、`float`、`bool`、`choice`、`list`、`multi_choice`、`password`

---

## 许可证

MIT
