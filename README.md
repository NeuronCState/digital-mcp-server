# Digital MCP 服务

这是一个用于 [Digital](https://github.com/hneemann/Digital) 逻辑电路模拟器的
stdio MCP 服务。它让 MCP 客户端可以直接创建、检查、验证、仿真和导出
`.dig` 电路文件，不需要手动操作窗口或截图。

## 能做什么

- 根据结构化设计生成 Digital `.dig` 电路文件。
- 检查电路元件、坐标、属性和连接线。
- 调用 Digital 的无头 CLI 验证内置测试用例。
- 导出静态电路图为 SVG 或高分辨率 PNG。
- 设置 `In` 输入或 `Button` 按钮状态，导出真实仿真状态图片。
- 从 `.dig` 中读取 Testcase，生成带 PASS/FAIL 结果的真值表图片。
- 将电路安全加载到 macOS Digital.app。

仿真图片不依赖 GUI 鼠标点击，而是创建 Digital 模型、写入输入状态并重新计算，
因此可以稳定复现“一个按钮激活”“两个按钮激活”等状态。

## 安装和运行

在 MCP 仓库根目录运行：

```bash
python3 digital_mcp_server.py
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "digital": {
      "command": "python3",
      "args": ["/绝对路径/digital-mcp-server/digital_mcp_server.py"],
      "env": {
        "DIGITAL_PROJECT_ROOT": "/绝对路径/Digital",
        "DIGITAL_JAR": "/绝对路径/Digital/source/target/Digital.jar",
        "DIGITAL_APP": "/绝对路径/Digital/modern/dist/Digital.app"
      }
    }
  }
}
```

如果 MCP 服务和 Digital 不在同一个目录，可使用以下环境变量：

```text
DIGITAL_PROJECT_ROOT       Digital 项目根目录，可选
DIGITAL_JAR                Digital.jar 路径，建议明确设置
DIGITAL_JAVA               Java 21 可执行文件路径，可选
DIGITAL_APP                Digital.app 路径，用于加载电路
DIGITAL_SVG_CONVERTER      SVG 转 PNG 程序，可选
DIGITAL_MCP_OUTPUT_DIR     默认生成文件目录，可选
```

PNG 导出需要以下任意一种程序：`rsvg-convert`、`magick`、`convert` 或
`inkscape`。也可以通过 `DIGITAL_SVG_CONVERTER` 指定路径。

## 主要 MCP 工具

### `digital_build_circuit`

根据 `design` 对象生成 `.dig` 文件。可选参数：

- `run_tests: true`：运行内置测试。
- `render_svg: true`：同时导出 SVG。
- `open: true`：在 macOS 中加载到 Digital。

最小设计示例：

```json
{
  "elements": [
    {"id": "a", "type": "In", "label": "A", "x": 200, "y": 100},
    {"id": "g", "type": "And", "x": 280, "y": 100},
    {"id": "y", "type": "Out", "label": "Y", "x": 380, "y": 100}
  ],
  "wires": [
    {"from": "a", "to": "g", "input": 0},
    {"from": "g", "to": "y"}
  ],
  "tests": [
    {"inputs": {"A": 0}, "outputs": {"Y": 0}},
    {"inputs": {"A": 1}, "outputs": {"Y": 1}}
  ]
}
```

支持的常用元件包括 `In`、`Out`、`And`、`Or`、`XOr`、`XNOr`、`NAnd`、
`NOr`、`Not`、`Clock`、`Const`、`Ground`、`VDD` 和 `Testcase`。
需要完整字段或引脚规则时，先调用 `digital_design_schema`。

### `digital_inspect_circuit` 和 `digital_run_tests`

```json
{"path": "/绝对路径/example.dig"}
```

`digital_inspect_circuit` 返回元件和连线信息；`digital_run_tests` 调用 Digital
模拟器运行测试，并返回 `passed`、退出码和命令输出。

### `digital_export_rendered_image`

导出静态电路图：

```json
{
  "path": "/绝对路径/motor_fault_indicator.dig",
  "format": "png",
  "output_path": "/绝对路径/motor_fault_indicator.png",
  "pixel_width": 4096
}
```

- `format`：`svg` 或 `png`，默认是 `png`。
- `pixel_width`：PNG 宽度，默认 2048，可设置为 4096 或更高。
- `output_path`：建议使用绝对路径；相对路径只能写入输入文件所在目录。

SVG 直接由 Digital CLI 导出；PNG 先生成 SVG，再用 SVG 转换器按指定宽度渲染。

### `digital_export_simulation_image`

设置输入或按钮状态后导出仿真图片：

```json
{
  "path": "/绝对路径/motor_fault_indicator.dig",
  "inputs": {"A": 1, "B": 0},
  "format": "png",
  "pixel_width": 4096,
  "scale": 30
}
```

输入值支持数字、布尔值和字符串。`In` 元件使用信号名匹配，`Button` 元件使用
按钮标签匹配：

- `A=1,B=0`：一个电机工作，黄灯应亮。
- `A=1,B=1`：两个电机工作，绿灯应亮。
- `A=0,B=0`：两个电机故障，红灯应亮。

也可以将 `inputs` 写成字符串：`"A=1,B=0"`。`scale` 控制 SVG 的逻辑尺寸，
`hide_test` 默认隐藏 Testcase 框。

### `digital_export_truth_table_image`

读取 `.dig` 中的 Testcase 数据，先执行 Digital 测试，再生成真值表 SVG/PNG：

```json
{
  "path": "/绝对路径/motor_fault_indicator.dig",
  "format": "png",
  "output_path": "/绝对路径/motor_fault_indicator_truth_table.png",
  "pixel_width": 4096
}
```

返回值同时包含 `columns`、`rows` 和 `validation`，图片标题会显示 `PASS` 或
`FAIL`。如果电路没有嵌入 Testcase 数据，工具会返回明确错误。

### `digital_load_circuit`

```json
{
  "path": "/绝对路径/motor_fault_indicator.dig",
  "app_path": "/绝对路径/Digital.app"
}
```

MCP 不再直接执行 `Digital.app/Contents/MacOS/Digital`。macOS 上该原生启动器
由 Python 拉起时可能在 Java/AWT 注册阶段触发 `SIGABRT`。现在工具只使用已经
验证过的外部 Java runtime，并进行启动存活检查；runtime 不可用时会返回错误，
不会再次尝试高风险启动路径。成功返回 `loaded: true` 和
`launcher: "managed-runtime"`。

## 生成文件位置

独立 MCP 仓库运行时默认写入服务目录下的 `generated/`。也可以用
`DIGITAL_MCP_OUTPUT_DIR` 自定义目录。

## 本地验证

运行 Python 测试：

```bash
python3 -m py_compile digital_mcp_server.py
```

仿真快照的底层 CLI 也可以直接运行：

```bash
java -Djava.awt.headless=true \
  -cp source/target/Digital.jar CLI snapshot \
  -dig /绝对路径/Digital/mcp/generated/motor_fault_indicator.dig \
  -svg /tmp/motor_fault_indicator_A1_B0.svg \
  -inputs A=1,B=0 -scale 30
```
