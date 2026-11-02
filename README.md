# 主体分类 Prompt 与千问生图工具

这个仓库用于为大规模插画数据集生成主体 Prompt，并按照相同的总要求批量生成图片。当前方案面向后续的语义分层任务：每张图尽量只包含一个明确主体、少量纯色面片和简单背景，便于后续识别主体、背景、遮挡关系和边界归属。

当前固定的视觉方向是：简洁、扁平、卡通化的矢量风格。图片使用少量大面积纯色形状，不使用黑色描边、线稿、阴影、渐变和复杂纹理。每张图的 Prompt 由两部分组成：

```text
固定总 Prompt
+
一句具体的主体行为描述
```

主体行为描述只说明“谁在做什么”，不单独指定风格。风格、背景、语义层数量和复杂度要求统一放在固定总 Prompt 中。

## 两项主要功能

### 1. 使用 API 批量生成图片

这条路径直接调用阿里云 DashScope / 千问图片生成接口。它可以：

- 使用固定总 Prompt 或自定义 Prompt；
- 为每张图片使用不同的 `seed`；
- 并发提交多张图片；
- 自动重试失败任务；
- 保存图片、任务 ID、Prompt 哈希、seed 和生成状态；
- 通过独立的 `negative_prompt` 参数抑制黑边、线稿、阴影、渐变、纹理和多余对象。

单一 Prompt 批量生成：

```powershell
$env:DASHSCOPE_API_KEY = "你的 API Key"
python .\qwen_batch_image.py --prompt "一只猫正在纸箱里睡觉" --count 50 --workers 3
```

按结构化计划批量生成：

```powershell
$env:DASHSCOPE_API_KEY = "你的 API Key"
python .\generate_dataset.py `
  --plans .\dataset_demo\plans.jsonl `
  --prompts .\dataset_demo\prompts.jsonl `
  --workers 3
```

API 路径默认发送仓库内置的负面提示词。如果模型或接口不接受该字段，可以显式覆盖：

```powershell
python .\qwen_batch_image.py --negative-prompt ""
```

### 2. 导出 Prompt 到本地生图平台

这条路径不调用 API，只生成可以复制到本地千问 2.1 image 平台或其他网页端的完整 Prompt。它可以：

- 从 WordNet 主体白名单抽取主体；
- 按 P0、P1 或全部词条筛选；
- 为主体生成一句行为描述；
- 把固定总 Prompt 与行为句拼接；
- 输出 Markdown、JSONL 和覆盖统计；
- 让使用者手动检查 Prompt 和图片效果。

生成 12 条 P0 Prompt：

```powershell
python .\plan_dataset.py `
  --count 12 `
  --priority P0 `
  --output-dir .\prompt_preview `
  --seed 20261102 `
  --force
```

之后打开 `prompt_preview\prompts_for_web.md`，复制其中任意一个代码块到本地生图平台。

仓库根目录也保留了一份当前示例：[prompts_for_web.md](prompts_for_web.md)。单只牛的完整案例见：[cow_prompt.md](cow_prompt.md)。

本地平台如果没有独立的 Negative Prompt 输入框，导出的单一 Prompt 仍然包含“无黑边、无阴影、必须有可见背景”等固定要求，但无法像 API 路径一样把负面提示词作为单独接口参数发送。

## 这个任务要生成什么图片

每张图的目标不是复杂的风景插画，而是适合语义分层的简单主体插画。理想图片具有以下特征：

- 只有一个主要主体，例如一只牛、一辆自行车或一个苹果；
- 主体占据画面的主要视觉位置，轮廓完整、容易识别；
- 背景是一个可见的单色或极简色块区域，而不是复杂风景；
- 可以有一个简单的地面或承托面；
- 整体约 2–4 个语义层；
- 主体由少量大面积纯色面片组成；
- 不出现黑色外轮廓、线稿、投影、接触阴影、渐变、纹理和细碎装饰；
- 不出现第二只动物、人物、花朵、云朵、远景或大量重复对象。

例如，牛的主体行为句是：

```text
A single cow is grazing on a flat patch of grass.
```

它描述的是主体和行为；“扁平卡通、无描边、简单背景”等要求来自固定总 Prompt。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `qwen_batch_image.py` | 直接调用千问 API 批量生图；包含固定总 Prompt、模型、尺寸、seed、并发和默认负面提示词。 |
| `generate_dataset.py` | 读取结构化计划和 Prompt，一条计划生成一张图片，并写入 `manifest.jsonl`。 |
| `taxonomy.py` | 读取 WordNet 主体词库，生成主体行为句、计划元数据并校验计划。 |
| `taxonomy_subjects.tsv` | 主体白名单；包含 WordNet synset、英文词、中文名、类别、分支和 P0/P1 优先级。 |
| `plan_dataset.py` | 抽样生成 `plans.jsonl`、`prompts.jsonl`、`prompts_for_web.md` 和覆盖统计。 |
| `render_prompts.py` | 把固定总 Prompt 与每张图的一句行为描述拼接成完整 Prompt。 |
| `validate_prompts.py` | 校验计划、Prompt、哈希和主体描述是否一一对应。 |
| `test_prompt_structure.py` | 检查 Prompt 拼接结构、WordNet 白名单和输出格式。 |
| `PROMPT_DATASET_DESIGN.md` | 记录数据集设计、抽样字段、计划格式和后续审核流程。 |
| `prompts_for_web.md` | 当前可直接复制到网页端的完整 Prompt 清单。 |
| `cow_prompt.md` | 单只牛案例的完整 Prompt。 |
| `images/` | 历史批量生成图片。 |
| `contact_sheet_5x10.png` | 历史图片的缩略图总览。 |
| `examples/qwen21/` | 后续收集的本地千问 2.1 image 结果及其说明。 |

## 生成结果和记录

计划模式通常会输出：

```text
dataset_demo/
├── plans.jsonl
├── prompts.jsonl
├── prompts_for_web.md
├── coverage_report.json
├── images/
└── manifest.jsonl
```

`plans.jsonl` 保存主体、WordNet synset、行为句、seed 和计划统计；`prompts.jsonl` 保存实际拼接后的 Prompt；`manifest.jsonl` 保存 API 生成状态、任务 ID、图片路径和哈希。

当前计划字段中的目标层数和遮挡等级用于统计与后续审核，不会追加到逐图 Prompt 中。逐图 Prompt 始终保持“固定总 Prompt + 一句主体行为描述”的规范结构。

## 本地千问 2.1 image 示例

仓库中已有一组历史生成结果缩略图，可用于快速查看早期整体风格：

![历史批量生成图片总览](contact_sheet_5x10.png)

这组图片主要用于回顾早期结果；后续收到本地千问 2.1 image 的新结果后，会在下面的示例目录中按 Prompt 和模型信息单独记录。

后续每收到一张本地千问 2.1 image 生成结果，就在 `examples/qwen21/` 中保存图片，并在本节记录对应 Prompt、主体和观察结果。建议每个示例包含：

| 字段 | 内容 |
| --- | --- |
| 图片 | 本地模型生成的 PNG 或 JPG |
| 主体 | WordNet 白名单中的主体词 |
| Prompt | 使用的完整 Prompt 或对应文件 |
| 模型 | 例如 Qwen 2.1 image |
| seed | 如果平台提供 |
| 观察 | 黑边、阴影、背景、主体数量、复杂度和分层适用性 |

示例目录中的说明文件模板见 [`examples/qwen21/README.md`](examples/qwen21/README.md)。图片会用于记录实际生成效果，不把单张结果当作模型一定遵守 Prompt 的证明。

## 开发和验证

项目只使用 Python 标准库。修改代码后运行：

```powershell
python -m py_compile qwen_batch_image.py generate_dataset.py taxonomy.py plan_dataset.py render_prompts.py validate_prompts.py
python -m unittest -v
```

API Key 只从环境变量、`.env` 或运行时输入读取，不要提交到 GitHub。
