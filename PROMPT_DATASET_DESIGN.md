# 可控 Prompt 驱动的语义分层 Benchmark 设计

本文档描述对当前 `qwen_batch_image.py` 的下一阶段改造方案。目标是把当前的“同一个 Prompt 加不同 seed 批量生图”，升级为“每张图片都有结构化条件、专属 Prompt、生成参数和可追溯记录”的 benchmark 输入生成流程。

本文档是实现设计，不会自动发起批量生成。后续实现时仍然使用仓库现有的 DashScope / 千问 API，API Key 只从环境变量或运行时输入读取。

## 1. 目标与原则

### 1.1 目标

每个样本需要同时具备以下内容：

1. 一份结构化样本计划，记录 WordNet 白名单主体词、一句行为描述，以及目标图层数和目标遮挡等级。
2. 一份发送给生图模型的最终 Prompt。
3. 一份生成参数记录，包括模型、尺寸、seed、时间和接口版本。
4. 一份结果状态，说明图片是否下载成功、是否通过自动检查、是否需要人工复核。

最终数据集不是一组没有解释的 PNG，而是由图片和 manifest 组成的可复现实验数据：

```text
dataset/
├── images/
│   ├── sample_0001.png
│   └── sample_0002.png
├── taxonomy_subjects.tsv # WordNet 主体词、类别、优先级和 synset
├── plans.jsonl       # 主体行为描述与抽样元数据
├── prompts.jsonl     # 实际发送的最终 Prompt
├── prompts_for_web.md # 可复制到网页端的完整 Prompt
├── manifest.jsonl    # 图片、Prompt、标签、参数和状态的关联
└── review.csv        # 自动检查和人工评价结果
```

### 1.2 原则

- **语义锚点明确**：每张图先确定一个白名单主体和一句行为描述，再渲染 Prompt。
- **每图一 Prompt**：每张图片拥有独立的 Prompt，不以随机 seed 代替语义描述。
- **可控优先于随机**：seed 只用于复现和同条件下的视觉变化，不负责数据集覆盖。
- **覆盖可计算**：每张样本保留主体类别、行为与目标难度元数据，便于统计。
- **复杂度可评估**：记录目标层数和遮挡等级，生成后另行审核实际结果。
- **失败可重跑**：单张失败不会丢失计划；修复后可以只重跑失败样本。
- **保留原始记录**：不覆盖原 Prompt、API 返回、错误信息和人工审核结果。

### 1.3 当前阶段的范围

这个仓库负责生成后续 SVG 语义分层 benchmark 的输入图片。后续完整流程是：先由 VLM 提取对象和关系，再进行 AI 补全，最后处理边缘归属并恢复为可独立编辑的 SVG 图层。当前阶段只负责生成适合进入这条流程的图片，不负责定义分层算法指标，也不要求现在就提供每个对象的像素级真值掩码。

筛选标准沿用 DnR FlatPic 的已有经验：优先保留完整、可分离的主体；控制在约 2–4 个语义对象或背景区域；拒绝主体残片、拥挤场景、复杂建筑和需要更多图层的画面。`accept`、`review`、`reject` 是输入适用性筛选状态，不是下游分层算法的性能评价。

## 2. 总体流程

```text
白名单主体与行为描述
    ↓
结构化样本计划器
    ↓
计划校验、配额检查、去重
    ↓
Prompt 渲染器（固定总 Prompt + 行为句）
    ↓
Prompt 校验和安全过滤
    ↓
DashScope / 千问生图 API
    ↓
下载图片、记录参数和 API 结果
    ↓
图像级自动筛选
    ↓
人工复核 / 标记 Accept、Review、Reject
    ↓
manifest、统计报告和可视化总览
```

建议把流程分成两个阶段：

1. **计划阶段**：不调用生图 API，只生成和检查计划、Prompt 草稿以及覆盖统计。
2. **生成阶段**：读取已经冻结的计划文件，调用 API，写入图片和结果。

这样可以在花费 API 费用之前发现无效行为描述、重复样本和明显的主体类别偏斜。

## 3. 覆盖矩阵

覆盖矩阵不是要求每一个维度都做笛卡尔积。它用于定义可选项、最低配额和禁止组合，然后由计划器选择一组规模可控的样本。

矩阵字段首先是**计划与数据分析的元数据**，不代表每一项都要写入 Prompt。本方案只在固定总 Prompt 后追加一句主体行为描述；目标层数与遮挡等级只用于计划、覆盖统计和生成后审核。主体行为可包含完成动作所必需的互动对象，但不指定预设场景、背景、配色、视角或构图，后者由模型自行选择。

### 3.1 推荐维度

| 维度 | 可选值示例 | 作用 |
| --- | --- | --- |
| `layer_count_target` | 2、3、4、5、6 | 记录目标语义层数量；不写入逐图 Prompt |
| `subject_family` | animal、person、food、plant、vehicle、object | 统计白名单主体类别覆盖 |
| `image_description` | 一句主体行为描述 | 锚定样本主体与动作；追加到逐图 Prompt |
| `occlusion_level_target` | none、light、medium | 记录目标遮挡程度；不写入逐图 Prompt |
| `complexity` | simple、moderate、challenging | 根据目标层数记录计划复杂度 |
| `environment_role` | 生成后标注的背景区域 | 由模型结合动作选择，不作为抽样或 Prompt 指令 |

其中 `layer_count_target`、`occlusion_level_target` 和 `complexity` 均是计划元数据，不写入逐图 Prompt。目标值不代表模型必须严格遵守的约束，生成后应另行记录实际层数和遮挡情况。

### 3.2 第一轮实验的选样方式

当前先做约 10 张图片的实验，不要求完整覆盖所有维度，也不要求提前规定每个交叉组合的精确配额。计划器从白名单主体及其可视化行为描述中进行受约束抽样，并为每张图记录图层数、目标遮挡等级等元数据，并记录抽样结果和随机种子，方便之后复盘哪些组合被抽到、哪些组合尚未出现。

第一轮只需要避免主体类别明显偏斜、重复行为和不可执行动作：

| 项目 | 建议覆盖 |
| --- | --- |
| 总样本数 | 约 10 |
| 图层数 | 从 2–4 层中受约束随机选择 |
| 主体类别 | 尽量避免全部集中到一个类别 |
| 行为描述 | 每张图追加一句明确、可视化且适合主体的动作描述 |
| 遮挡目标 | 仅作计划元数据抽样；生成后记录实际遮挡，不对模型指定目标等级 |
| 复杂度 | 以 simple / moderate 为主，少量 challenging |
| 行为关系 | 由行为描述自然表达，不额外规定空间关系 |
| 记录内容 | 保存抽样 seed、完整计划、最终 Prompt 和覆盖统计 |

通过这一轮检查后，再决定是否采用更全面的交叉设计扩展到 50、100 或更大的规模。届时可以使用分层抽样或受约束的 pairwise coverage，而不是简单地把所有维度做笛卡尔积。

### 3.3 禁止或限制组合

计划器必须在生成前拒绝明显不符合任务的组合：

- 主体行为无法由静态插画清楚表达，或动作与主体不相容。
- `complexity=simple` 却要求 crowds、market、city intersection 等高密度场景。
- 行为描述隐含复杂拥挤场景、许多重复对象或难以分离的交错轮廓。
- 将 facial feature、衣服、花瓣颜色、车轮等内部细节错误计为独立图层。
- 出现文字、招牌、品牌标志、水印、复杂纹理或大段背景建筑。

## 4. 主体词与图层模型

主体词来自 `taxonomy_subjects.tsv`，每条记录包含 WordNet 3.0 synset、英文词形、中文名称、上位类别及 P0/P1 优先级。计划器默认从 P0 中按类别均衡抽样；可选生成 P1 或全部词条。已核对的具体行为句优先使用词条级描述，其余词条使用类别或 WordNet 分支对应的短模板。

每个样本的背景与辅助对象由模型结合动作自行安排，不在计划阶段锁定完整实体列表。生成后再记录实际出现的对象、关系和图层；一棵树、一个完整人物、一辆完整自行车或一个连贯环境区域可作为一个语义层，眼睛、颜色斑块和纹理等内部细节不单独计层。

`layer_count_target` 是样本的目标层数元数据，范围为 2–4，包含背景区域。它不写入样本级 Prompt，也不是模型输出保证。实际层数以生成后审核为准。

## 5. 目标关系与遮挡记录

关系模式与遮挡等级作为计划及生成后评价字段保留，用于描述目标难度和数据集覆盖，不作为逐图 Prompt 指令。行为句可表达动作必要的关系，例如“骑车人正骑着自行车”；不额外附加 `riding`、`in_front_of` 等关系标签，也不指定遮挡对象。生成后由审核者记录实际观察到的对象关系与遮挡程度。

目标层数和目标遮挡等级是计划值，不代表生成模型一定遵守。将 `layer_count_target`、`occlusion_level_target` 与生成后记录的 `estimated_layers`、`occlusion_observed` 分开存储，避免把目标误当成实际结果。

## 6. Prompt 结构

每张图的 Prompt 由固定总 Prompt 和唯一一句样本级主体行为描述组成。固定总 Prompt 保证风格和分层任务要求一致；行为句确定样本的语义锚点。

### 6.1 固定段落

固定段落直接复用仓库 [`qwen_batch_image.py`](qwen_batch_image.py) 中现有的 `PROMPT`，不再为每张图另行生成场景、背景或构图指令。该总 Prompt 保留统一的画风、简洁度和分层任务要求，并允许模型依据行为描述选择自然背景。

### 6.2 样本特定描述

样本特定部分只追加一句简短的主体行为描述。主体词须来自白名单；动作应清楚、可视化，并可包含动作必需的互动对象。不得在这句中追加目标层数、完整实体列表、场景名称、背景类别、配色、视角、构图、关系标签或遮挡等级。环境和背景由模型结合行为自然选择。

示例：

渲染器只在固定总 Prompt 末尾追加行为句，格式如下：

```text
<仓库固定总 Prompt>

A fox is sniffing a mushroom.
```

### 6.3 Prompt 生成方式

建议采用“固定总 Prompt + 行为描述”的确定性渲染：

1. **确定性渲染器**：复用仓库固定总 Prompt，并且只在末尾追加计划中的一句主体行为描述。这是正式 benchmark 的默认路径。
2. **可选语言改写器**：如后续确需加入，只能润色固定总 Prompt 与行为句的衔接，保留主体词和动作，不得添加逐样本控制条件。改写后重新解析和校验，校验失败就回退到模板版本。

本轮不使用语言模型逐图生成或改写 Prompt；行为句由确定性计划提供。

## 7. 结构化计划格式

每行记录一张图的主体行为描述及用于覆盖分析的元数据。背景与完整对象清单由生成模型决定，不预先冻结为 Prompt 条件。

```json
{
  "plan_version": "0.3",
  "sample_id": "sample_0001",
  "image_seed": 20261029,
  "image_description": "A rabbit is nibbling on a leaf.",
  "taxonomy": {
    "subject_families": ["animal"],
    "subject_priority": "P0",
    "action_type": "subject_action_sentence",
    "layer_count_target": 3,
    "occlusion_level_target": "light",
    "complexity": "simple"
  },
  "entities": [
    {"id": "e1", "name": "rabbit", "name_zh": "兔", "category": "animal", "synset": "rabbit.n.01", "role": "main_subject"}
  ],
  "prompt_policy": {
    "allow_extra_objects": false,
    "allow_text": false,
    "allow_gradients": false,
    "background_selection": "model_selected"
  }
}
```

`layer_count_target` 与 `occlusion_level_target` 是目标元数据；`entities` 只标识行为句中的主要主体，不声称是生成图的完整实体真值。生成后另行记录背景、辅助对象和实际关系。

## 8. Manifest 与可复现性

计划和实际生成记录分开保存。计划里的目标层数与目标遮挡等级，必须和生成后审核的实际估计值分开。推荐的 `manifest.jsonl` 记录如下：

```json
{
  "sample_id": "sample_0001",
  "plan_file": "plans.jsonl",
  "prompt_file": "prompts.jsonl",
  "plan_sha256": "...",
  "prompt_sha256": "...",
  "model": "qwen-image-3.0-pro",
  "size": "1536*1024",
  "seed": 20261030,
  "seed_scope": "image_generation",
  "code_revision": "git-commit-or-local-version",
  "api_endpoint": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
  "request_parameters": {"n": 1, "negative_prompt": ""},
  "attempt": 1,
  "submitted_at": "2026-10-29T12:00:00Z",
  "task_id": "task-...",
  "image_path": "images/sample_0001.png",
  "image_sha256": "...",
  "provider_request_id": "...",
  "status": "succeeded",
  "auto_review": "pending",
  "manual_review": "pending",
  "error": null
}
```

必须记录最终实际发送的 Prompt，而不是只记录 Prompt 模板。建议同时记录计划和 Prompt 的 SHA-256、代码版本、接口地址、脱敏后的请求参数、provider request ID、最终图片 SHA-256，以及每次重试的状态和错误摘要。seed 主要保证在相同模型和服务条件下尽量复现，不能承诺服务端或模型版本变化后逐像素一致；这里的目标是让样本来源可追溯、文件可校验、实验尽可能可重跑，而不是保证远端生成结果逐像素相同。API Key、Authorization header、签名图片 URL 和完整敏感响应不得写入 manifest。

## 9. 遮挡指标与 mIoU 的边界

### 9.1 mIoU 是分层结果指标

`mIoU`（mean Intersection over Union，平均交并比）需要两组像素掩码：预测掩码 `P` 和参考掩码 `G`。对每个对象或类别先计算：

```text
IoU(P, G) = |P ∩ G| / |P ∪ G|
mIoU = 所有对象 IoU 的平均值
```

它适合在后续 benchmark 中比较 VLM/AI 生成的分层结果和参考 SVG 图层掩码的重合质量。它不能仅凭一张合成 PNG 判断两个物体实际遮挡了多少，也不能替代 Accept / Review / Reject。

### 9.2 遮挡程度的直接定义

如果未来拥有对象的 amodal mask（包括被遮挡后不可见的部分）和 composite 中的 visible mask，可以记录：

```text
visible_fraction(B) = |M_visible(B)| / |M_amodal(B)|
occlusion_ratio(B) = 1 - visible_fraction(B)
```

如果同时有两个对象的 amodal mask，可以记录它们的几何交叠：

```text
pairwise_overlap(A, B) = |M_amodal(A) ∩ M_amodal(B)| / |M_amodal(A) ∪ M_amodal(B)|
```

这两个量分别描述“目标对象有多少被遮住”和“两个对象的形状区域交叠多少”，不要把它们叫作 mIoU。当前 Qwen 输出主要是 PNG，尚未有对象级 amodal mask，因此本方案将 `occlusion_level_target` 保留为计划目标元数据，不作为逐图 Prompt 条件，并在人工审核中记录 `occlusion_observed`（none / light / medium / high / unclear）。有了可编辑 SVG 的真实图层后，再计算上述比例和下游 mIoU。

## 10. Prompt 校验、去重与覆盖检查

### 10.1 结构校验

在调用 API 前，校验器应检查：

- 每个计划包含一个唯一主要主体和一条简短、可视化的行为描述。
- `layer_count_target` 在 2–4 之间；此值与行为句中的对象数无关，不能作为模型遵守的生成保证。
- `occlusion_level_target` 为 none、light 或 medium。
- Prompt 末尾恰好追加一条与计划一致的主体行为描述；目标层数和遮挡等级不出现在样本特定部分。
- Prompt 没有“many objects”“crowd”“busy city”等与复杂度冲突的词。
- 禁止词（text、logo、watermark 等）仍然保留。

### 10.2 语义去重

不只比较完整 Prompt 字符串，还比较规范化签名：

```text
(subject word, action description)

计划元数据不改变 Prompt，因此不影响语义去重。
```

例如只改颜色或形容词不算新的语义样本。新样本至少应改变主体词或行为描述；层数、遮挡、视角等仅作元数据的变化不应被当作 Prompt 语义去重差异，并限制同一签名的重复次数。

### 10.3 覆盖统计

计划阶段输出 `coverage_report.json` 和可读的 Markdown 表格，至少统计：

- 目标层数与实际估计层数。
- 各主体类别数量。
- 各主体行为描述数量；背景场景在生成后可另行标注统计。
- 目标遮挡等级与实际观察到的遮挡等级数量。
- 各复杂度数量。
- 当前样本中出现的主体类别与层数组合。

第一轮约 10 张只把覆盖报告作为描述性记录，不以“覆盖全面”作为通过条件，也不为每个组合设硬配额。将来扩展正式 benchmark 时，再决定最低配额、允许的偏斜程度和是否使用 pairwise coverage；例如，50 张中大多数都落在同一主体类别或动作类型时，应视为主体行为覆盖不足；计划层数的分布单独报告。

## 11. 图像级筛选

行为描述与目标元数据用于定义样本设计，不能保证模型完全遵守；因此生成后还需要一个轻量筛选环节。这个环节的目标是排除明显过难的 benchmark 输入，而不是给下游分层算法计算最终分数：

### 自动检查

- 图片是否成功下载、尺寸是否正确、文件是否为空。
- 是否检测到明显文字、水印、边框或大面积复杂纹理。
- 主体数量是否明显超出计划。
- 图片是否过于拥挤或主体被裁切。
- 是否存在严重融合、无法区分的轮廓或主体残片。

### 人工状态

- `accept`：主体和关系基本符合计划，可以进入数据集。
- `review`：图片有价值但层数、遮挡或主体边界需要讨论。
- `reject`：出现严重复杂度超标、主体缺失、画面残片或明显不符合 Prompt。

建议在审核表中增加字段：`estimated_layers`、`independent_foreground_entities`、`background_clutter`、`subject_completeness`、`cropped_subject`、`occlusion_observed`、`reason_code`。可以沿用 DnR FlatPic 的量表：`estimated_layers` 是合并内部细节后的预计层数；`independent_foreground_entities` 只数完整且相互独立的前景/中景对象；`background_clutter` 取 1–5（1 是简单空背景，3 需要人工判断，4–5 通常拒绝）；`subject_completeness` 取 0–1（完整主体建议不低于 0.8）；`cropped_subject` 是主对象是否被画面边界截断。生成目标仍是 2–4 层，超过 4 层或没有可解释对象关系时拒绝。本轮以人工确认和记录为主，不把这些估计值冒充精确像素指标。

筛选结果只改变 `review.csv` 和 manifest 状态，不覆盖原图片和原始 Prompt。这样可以分析“哪些条件更容易生成失败”。

## 12. 对当前仓库的代码改造

### 12.1 保留的能力

当前脚本已经具备以下基础能力，可以继续复用：

- DashScope HTTP 调用。
- 已有任务轮询辅助函数；正式接入前需要用当前模型的真实响应确认提交、轮询和结果 URL 的契约，并让生成器统一走这一适配层。
- 图片下载。
- 并发 worker。
- 单张重试。
- API Key 环境变量读取。

### 12.2 当前模块

第一版可以先保持一个仓库、多个 Python 文件，不必立即拆成复杂的包：

```text
qwen-batch-image/
├── qwen_batch_image.py       # 保留兼容模式：单 Prompt 批量生成
├── taxonomy.py               # 白名单读取、行为句、计划采样和校验
├── taxonomy_subjects.tsv     # WordNet 主体词与优先级数据
├── plan_dataset.py           # 生成和校验 plans.jsonl
├── render_prompts.py         # 计划 → 最终 Prompt
├── validate_prompts.py       # 计划/Prompt 对应关系、结构、哈希和重复检查
├── generate_dataset.py       # 读取计划并调用 API
├── review_dataset.py         # 图片基本检查和 review.csv
├── schemas/                  # JSON Schema 或示例配置
└── docs/
    └── PROMPT_DATASET_DESIGN.md
```

如果希望降低改造风险，可以先把这些函数放入 `qwen_batch_image.py`，等第一轮实验稳定后再拆文件。

### 12.3 建议增加的命令

```powershell
# 只生成约 10 个计划和 Prompt，不调用 API
python .\plan_dataset.py --count 12 --priority P0 --output-dir .\prompt_preview --seed 20261102

# 检查计划、重复和覆盖情况
python .\validate_prompts.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl

# 读取已经冻结的计划并生成图片
$env:DASHSCOPE_API_KEY = "你的Key"
python .\generate_dataset.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl --workers 3

# 生成可读的缩略图总览和审核表
python .\review_dataset.py --dataset-dir .\dataset_demo
```

原有的 `python qwen_batch_image.py --prompt ... --count ...` 继续可用，作为简单模式；benchmark 模式必须使用计划文件。

## 13. Prompt 的确定性

本轮不使用 LLM 生成或改写逐图 Prompt。程序从 WordNet 白名单主体对应的行为描述中抽样，复用仓库固定总 Prompt，并原样追加一句动作描述。这样每条 Prompt 都能从计划文件确定性重建，层数和遮挡目标等元数据不会被改写器意外写入。

后续若确需试验 LLM 改写，应作为单独实验分支，并同时保存原始计划、改写前后 Prompt 和校验结果；该改写不属于当前默认生成路径。

## 14. 一个 50 张样本的组织示例

可以把 50 张拆成五个小组，每组 10 张：

| 组别 | 主体行为覆盖 | 计划元数据 |
| --- | --- | --- |
| A | 单主体、简单动作 | 目标层数 2–3，目标遮挡 none / light |
| B | 日常物件与常见动作 | 目标层数 3–4，按类别平衡 |
| C | 必需互动对象的动作（如手持、骑行、放置） | 目标层数 3–5，目标遮挡只作统计 |
| D | 植物、食品、交通工具等跨类主体动作 | 目标层数 4–6，生成后检查实际复杂度 |
| E | 混合主体和行为 | 统计类别、行为和实际观察到的关系 |

每组内部再平衡白名单主体类别和动作类型；背景由模型选择，生成后再统计实际场景。每组都保留计划文件和覆盖统计，便于分别分析。

## 15. 实施顺序与验收标准

### 阶段一：计划器和渲染器

- 新增对象、关系和复杂度词表。
- 生成 10 个主体行为计划和 Prompt 草稿。
- 完成结构校验、重复检查和覆盖报告。
- 不调用生图 API。

验收：每个计划都记录主体词、行为描述、目标层数和目标遮挡；Prompt 能从计划确定性重建，且逐图部分只追加主体行为描述。

### 阶段二：小规模生图

- 读取冻结的 10 个计划。
- 并发生成图片。
- 写入 `manifest.jsonl`，记录每张图的 Prompt、seed、task_id 和状态。
- 生成缩略图总览，人工检查 Accept / Review / Reject。

验收：失败样本可以单独重试；不重新生成已成功样本；没有 API Key 泄露；图片和 manifest 一一对应。

### 阶段三：扩展到 50 张

- 先检查覆盖报告，再调用 API。
- 生成结束后统计各条件的通过率。
- 只对 Reject 样本按原因修订计划或 Prompt。
- 保留原始版本，使用 `revision` 标记重生成版本。

验收：50 张样本都有独立 Prompt，覆盖矩阵没有明显空洞，所有图片都可追溯到一个计划和一次 API 调用。

## 16. 主要风险和对应措施

| 风险 | 措施 |
| --- | --- |
| 生成结果不符合目标层数或遮挡等级 | 目标值只用于计划和统计；生成后审核实际结果 |
| Prompt 文字变化影响实验 | 保存结构化计划和最终 Prompt，固定模型和参数 |
| 组合重复 | 使用规范化签名去重，并做覆盖统计 |
| 主体行为难以表达或执行 | 先用 10 张小样本检查白名单主体的动作描述 |
| API 限流或任务失败 | 保留现有并发、重试和单张失败机制 |
| Key 泄露 | 只读环境变量或运行时输入，`.gitignore` 排除本地配置 |
| 图片 URL 过期 | 下载后立即保存，manifest 只保留本地路径和 task_id |

## 17. 推荐的第一步

下一步先生成 10 个主体行为计划、10 个最终 Prompt 和一份覆盖报告。检查主体类别、动作与元数据分布后，再接入 API 生成少量图片。

