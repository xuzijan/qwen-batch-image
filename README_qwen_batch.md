# 千问批量生图脚本

## 生成可复制到网页端的完整提示词

打开仓库根目录的 [`prompts_for_web.md`](prompts_for_web.md)，每个代码块都是一条完整提示词：仓库原有的通用图像要求，加上一句具体主体行为描述。复制单个代码块到你使用的生图网页即可手动试图；这个步骤不会调用 API。

重新抽取一组 P0 示例：

```powershell
python .\plan_dataset.py --count 12 --priority P0 --output-dir .\prompt_preview --seed 20261102 --force
```

生成结果中的 `prompts_for_web.md` 是可直接复制的完整提示词；`plans.jsonl` 和 `coverage_report.json` 用于查看主体和计划统计。Prompt 只包含固定总要求和一条主体行为描述，背景由模型自行发挥，层数与遮挡目标只保留在统计字段中。

需要抽取 P1 或所有词条时，将 `--priority P0` 分别改为 `--priority P1` 或 `--priority all`。

## 千问 API 批量生图

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

Benchmark 模式先从 `taxonomy_subjects.tsv` 中按 WordNet 类别与 P0/P1 优先级抽取主体，再为主体生成一句行为描述，并把这句话拼接到仓库固定总 Prompt 末尾。它不会调用生图 API；输出的完整 Prompt 可以直接复制到网页端测试。

生成 12 条 P0 Prompt：

```powershell
python .\plan_dataset.py --count 12 --priority P0 --output-dir .\prompt_preview --seed 20261102
```

输出包括：

- `prompts_for_web.md`：完整可复制 Prompt 清单，每个代码块都是“固定总 Prompt + 一句主体行为描述”。
- `plans.jsonl`：主体、WordNet synset、优先级、行为描述和计划统计字段。
- `prompts.jsonl`：机器可读 Prompt 与计划/Prompt 哈希。
- `coverage_report.json`：本轮类别、优先级、层数目标和遮挡目标的统计。

`--priority` 可设为 `P0`、`P1` 或 `all`；默认是 `P0`。`all` 还会包含尚未匹配 P0/P1 的历史 WordNet 候选词。背景不单独抽样或写入逐图句子，由模型结合行为自行选择。目标层数和遮挡等级只作为计划元数据，不会拼入 Prompt。

检查网页端效果后，如需用生成 API 批量出图，再执行：

```powershell
$env:DASHSCOPE_API_KEY = "你的API Key"
python .\generate_dataset.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl --workers 3
```

该命令固定每条请求 `n=1`，图片保存到 `dataset_demo/images/`，生成参数、任务 ID、图片哈希和状态保存到 `manifest.jsonl`。详细设计见 [`PROMPT_DATASET_DESIGN.md`](PROMPT_DATASET_DESIGN.md)。
