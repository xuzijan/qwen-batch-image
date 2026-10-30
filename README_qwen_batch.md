# 千问批量生图脚本

脚本文件是 [`qwen_batch_image.py`](qwen_batch_image.py)。它使用阿里云 DashScope 的千问图片生成接口，并把返回的图片下载到本地。每张图使用不同的 `seed`，因此同一提示词会生成不同结果。

## 快速使用

1. 安装 Python 3.9 或更高版本。脚本只使用 Python 标准库，不需要 `pip install`。
2. 打开 `qwen_batch_image.py` 顶部的配置区，填写 `PROMPT`、`COUNT`，必要时修改 `MODEL`、`SIZE` 和 `OUTPUT_DIR`。
3. 推荐把 API Key 放到环境变量中（PowerShell）：

```powershell
$env:DASHSCOPE_API_KEY = "你的API Key"
python .\qwen_batch_image.py
```

也可以直接运行脚本，按提示输入 Key；或者在命令行传入：

```powershell
python .\qwen_batch_image.py --prompt "一只在月球上喝茶的猫" --count 50 --workers 3
```

图片默认保存到 `qwen_outputs` 文件夹，文件名为 `qwen_0001.png`、`qwen_0002.png` 等。失败的单张会自动重试，其他图片不会因此停止。

## 常用参数

```text
--count 50                 生成数量
--model qwen-image-plus    千问模型名称，以控制台实际可用模型为准
--size 1024*1024           图片尺寸，以模型支持的值为准
--workers 3                并发任务数；遇到限流时改为 1 或 2
--negative-prompt "..."    负面提示词
--output-dir my_images     输出文件夹
--base-seed 20261027       起始随机种子；换一个值可得到另一组结果
```

## 接口或模型不同怎么办

脚本默认使用中国内地 DashScope 地址：
`https://dashscope.aliyuncs.com/api/v1/services/aigc/text-to-image/image-synthesis`。
当前脚本默认使用新版 `qwen-image-3.0-pro` 和多模态生成接口。如果你的 Key 属于其他地域，或控制台给了不同的 Endpoint，需要把脚本顶部的 `SUBMIT_URL` 改成控制台文档中的地址。`MODEL` 也要改为你的账号实际开通的千问生图模型。

不要把 API Key 提交到 Git 或公开网页。可以复制 `.env.example` 为本地 `.env`，填入 `DASHSCOPE_API_KEY`；`.env` 已被 Git 忽略，脚本会自动读取。

## Benchmark 计划模式

Benchmark 模式不会用一个高层 Prompt 配不同 seed 来生成所有图片，而是先根据统一的高层生成策略抽取一份结构化场景计划，再渲染出该图片专属的 Prompt，并让这一条 Prompt 只生成一张图片。第一轮使用确定性模板，不让文本模型自由改写；seed 只用于复现，不负责语义覆盖。

第一阶段只生成计划和 Prompt，不调用 API：

```powershell
python .\plan_dataset.py --count 10 --output-dir .\dataset_demo --seed 20261029
python .\validate_prompts.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl
```

输出包括：

- `plans.jsonl`：每张图的对象、图层数、深度、关系和遮挡条件。
- `prompts.jsonl`：每张图实际要发送给千问的 Prompt，以及计划和 Prompt 哈希。
- `coverage_report.json`：本轮随机抽样的覆盖统计。

Prompt 渲染器直接复用此前 50 张图片使用的总 Prompt 原文，只在末尾追加当前样本抽中的矩阵条件、对象列表和必要空间关系。矩阵条件包括图层数、主体类别、场景、关系、遮挡、复杂度、配色倾向、视角和构图倾向，但不规定精确坐标或比例。生成脚本默认使用 `1024*1024`，与旧样本保持一致；这样每张图片仍有独立 Prompt，同时尽量保持旧有视觉风格。

检查完这 10 条 Prompt 后，再执行单图生成：

```powershell
$env:DASHSCOPE_API_KEY = "你的API Key"
python .\generate_dataset.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl --workers 3
```

该命令固定每条请求 `n=1`，图片保存到 `dataset_demo/images/`，生成参数、任务 ID、图片哈希和状态保存到 `manifest.jsonl`。详细设计见 [`PROMPT_DATASET_DESIGN.md`](PROMPT_DATASET_DESIGN.md)。
