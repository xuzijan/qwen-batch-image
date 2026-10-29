# 可控 Prompt 驱动的语义分层 Benchmark 设计

本文档描述对当前 `qwen_batch_image.py` 的下一阶段改造方案。目标是把当前的“同一个 Prompt 加不同 seed 批量生图”，升级为“每张图片都有结构化条件、专属 Prompt、生成参数和可追溯记录”的 benchmark 输入生成流程。

本文档是实现设计，不会自动发起批量生成。后续实现时仍然使用仓库现有的 DashScope / 千问 API，API Key 只从环境变量或运行时输入读取。

## 1. 目标与原则

### 1.1 目标

每个样本需要同时具备以下内容：

1. 一份结构化的场景计划，说明画面包含哪些主体、目标图层数和主体之间的关系。
2. 一份发送给生图模型的最终 Prompt。
3. 一份生成参数记录，包括模型、尺寸、seed、时间和接口版本。
4. 一份结果状态，说明图片是否下载成功、是否通过自动检查、是否需要人工复核。

最终数据集不是一组没有解释的 PNG，而是由图片和 manifest 组成的可复现实验数据：

```text
dataset/
├── images/
│   ├── sample_0001.png
│   └── sample_0002.png
├── plans.jsonl       # 结构化场景计划
├── prompts.jsonl     # 实际发送的最终 Prompt
├── manifest.jsonl    # 图片、Prompt、标签、参数和状态的关联
└── review.csv        # 自动检查和人工评价结果
```

### 1.2 原则

- **条件先于文字**：先选择结构化条件，再渲染自然语言 Prompt。
- **每图一 Prompt**：每张图片拥有独立的 Prompt，不以随机 seed 代替语义描述。
- **可控优先于随机**：seed 只用于复现和同条件下的视觉变化，不负责数据集覆盖。
- **覆盖可计算**：每张样本可以映射回覆盖矩阵中的一个组合。
- **复杂度有预算**：对象数、图层数、遮挡量和关系数量都必须有明确上限。
- **失败可重跑**：单张失败不会丢失计划；修复后可以只重跑失败样本。
- **保留原始记录**：不覆盖原 Prompt、API 返回、错误信息和人工审核结果。

### 1.3 当前阶段的范围

这个仓库负责生成后续 SVG 语义分层 benchmark 的输入图片。后续完整流程是：先由 VLM 提取对象和关系，再进行 AI 补全，最后处理边缘归属并恢复为可独立编辑的 SVG 图层。当前阶段只负责生成适合进入这条流程的图片，不负责定义分层算法指标，也不要求现在就提供每个对象的像素级真值掩码。

筛选标准沿用 DnR FlatPic 的已有经验：优先保留完整、可分离的主体；控制在约 2–6 个语义对象或背景区域；要求至少有清晰的对象关系；拒绝主体残片、拥挤场景、复杂建筑和需要几十个图层的画面。`accept`、`review`、`reject` 是输入适用性筛选状态，不是下游分层算法的性能评价。

## 2. 总体流程

```text
覆盖矩阵配置
    ↓
结构化场景计划器
    ↓
计划校验、配额检查、去重
    ↓
Prompt 渲染器（模板为主，LLM 改写为可选）
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

这样可以在花费 API 费用之前发现图层数超限、关系矛盾、主体重复和覆盖不均匀等问题。

## 3. 覆盖矩阵

覆盖矩阵不是要求每一个维度都做笛卡尔积。它用于定义可选项、最低配额和禁止组合，然后由计划器选择一组规模可控的样本。

矩阵字段首先是**计划与数据分析的元数据**，不代表每一项都必须变成 Prompt 指令。Prompt 只明确 benchmark 必须控制的语义条件；画面比例、镜头距离、对象位置和一般构图默认交给生图模型自行安排。只有为了表达指定遮挡时，才约束相关对象的局部前后关系。

### 3.1 推荐维度

| 维度 | 可选值示例 | 作用 |
| --- | --- | --- |
| `layer_count` | 2、3、4、5、6 | 控制目标语义层数量 |
| `subject_family` | animal、person、food、plant、vehicle、object、building、nature | 控制主体类别覆盖 |
| `scene_type` | indoor、garden、street、shore、forest、workshop、market、fantasy | 控制环境变化 |
| `relation_pattern` | beside、in_front_of、behind、inside、on、holding、riding、supporting | 控制空间和支撑关系 |
| `occlusion_level` | none、light、medium、high | 控制边界被遮挡的程度 |
| `complexity` | simple、moderate、challenging | 控制主体数量、细节和关系密度 |
| `composition` | centered、left_right、diagonal、foreground_background、triangular | 控制构图变化 |
| `viewpoint` | front、three_quarter、side、slightly_top_down | 控制观察角度 |
| `palette` | warm、cool、natural、pastel、high_contrast | 控制色彩变化 |
| `environment_role` | sky、ground、sea、hill、wall、table、floor | 明确背景也是语义层 |

其中 `composition` 和 `viewpoint` 在本轮仅用于记录模型自然生成出的画面特征或抽样分析，不作为强制 Prompt 条件；除非后续实验专门研究构图控制，否则不要将它们写入样本 Prompt。

### 3.2 第一轮实验的选样方式

当前先做约 10 张图片的实验，不要求完整覆盖所有维度，也不要求提前规定每个交叉组合的精确配额。计划器从合法的条件集合中进行受约束随机抽样，并记录抽样结果和随机种子，方便之后复盘哪些组合被抽到、哪些组合尚未出现。

第一轮只需要避免明显偏斜和非法组合：

| 项目 | 建议覆盖 |
| --- | --- |
| 总样本数 | 约 10 |
| 图层数 | 从 2–6 层中受约束随机选择 |
| 主体类别 | 尽量避免全部集中到一个类别 |
| 遮挡程度 | 根据关系随机选择 none、light、medium；暂不强求 high |
| 复杂度 | 以 simple / moderate 为主，少量 challenging |
| 关系模式 | 至少出现并列、接触或一种清晰遮挡关系 |
| 记录内容 | 保存抽样 seed、完整计划、最终 Prompt 和覆盖统计 |

通过这一轮检查后，再决定是否采用更全面的交叉设计扩展到 50、100 或更大的规模。届时可以使用分层抽样或受约束的 pairwise coverage，而不是简单地把所有维度做笛卡尔积。

### 3.3 禁止或限制组合

计划器必须在生成前拒绝明显不符合任务的组合：

- `layer_count=2` 但同时要求 4 个独立主体。
- `complexity=simple` 却要求 crowds、market、city intersection 等高密度场景。
- `occlusion_level=high` 但只有两个互不接触的主体。
- 将 facial feature、衣服、花瓣颜色、车轮等内部细节错误计为独立图层。
- 同一计划同时要求“无重叠”和“明显前后遮挡”。
- 出现文字、招牌、品牌标志、水印、复杂纹理或大段背景建筑。
- 关系图包含环路，例如 A 在 B 上、B 又在 A 后方，且没有明确解释。

## 4. 对象词表与图层模型

### 4.1 对象分类

对象词表应该是有限、可审核、可扩展的，而不是让模型完全自由发挥。第一版可以采用以下分类：

#### 动物 `animal`

`cat`、`dog`、`fox`、`bear`、`rabbit`、`bird`、`elephant`、`turtle`、`fish`、`butterfly`

#### 人物 `person`

`child`、`adult`、`gardener`、`cook`、`cyclist`、`traveler`、`musician`。人物只描述完整人物或完整姿态，不使用“半张脸”“身体片段”等主体残片。

#### 食物 `food`

`bread`、`cake`、`apple`、`sandwich`、`bowl_of_soup`、`tea_cup`、`pizza`、`fruit_basket`

#### 植物 `plant`

`tree`、`flowering_plant`、`potted_plant`、`mushroom`、`bush`、`single_flower`

#### 交通工具 `vehicle`

`bicycle`、`scooter`、`small_boat`、`train_carriage`、`hot_air_balloon`。第一版限制车辆内部结构，避免把发动机、车轮、车灯等误变成过多独立实体。

#### 物体 `object`

`wooden_crate`、`flower_pot`、`bench`、`umbrella`、`backpack`、`lantern`、`book`、`basket`

#### 环境区域 `environment`

`sky`、`cloud`、`ground`、`grass_patch`、`sea`、`hill`、`wall`、`wooden_table`、`floor`。环境区域必须是可以作为一个完整遮罩处理的连贯区域。

### 4.2 语义层与内部细节

每个 `entity` 是一个候选语义层。实体可以包含内部细节，但内部细节不单独占层：

```json
{
  "id": "e2",
  "category": "animal",
  "name": "fox",
  "appearance": ["orange fur", "blue scarf"],
  "role": "main_subject",
  "depth": 2,
  "is_layer": true
}
```

这里的围巾、脸部、眼睛、衣服和颜色斑块仍然属于 `fox`。当前实验沿用已有仓库的对象级口径：一棵树、一个完整人物、一辆完整自行车或一个连贯的天空/地面区域算一个语义层；眼睛、鼻子、花瓣颜色、车轮、阴影和纹理不单独计层。多个同类实例只有在它们作为一个连贯、可解释的重复群组处理时才可以合并，否则按独立对象记录。更细的实例合并规则留到有真实分层标注后再定，不阻塞本轮 10 张实验。

### 4.3 图层预算

计划器应同时记录目标层数和实体清单：

```json
{
  "layer_count_target": 5,
  "entities": [
    {"id": "e1", "name": "sky", "category": "environment", "depth": 0},
    {"id": "e2", "name": "ground", "category": "environment", "depth": 1},
    {"id": "e3", "name": "wooden_crate", "category": "object", "depth": 2},
    {"id": "e4", "name": "fox", "category": "animal", "depth": 3},
    {"id": "e5", "name": "mushroom", "category": "plant", "depth": 4}
  ]
}
```

统一规定：`depth=0` 表示最远、最靠后，数字越大表示越靠前。`depth` 只表示前后顺序，不要求模型输出可编辑 SVG。当前 API 生成结果仍以 PNG 为主；语义层清单是 benchmark 的输入控制条件和后续 VLM 分层流程的先验，不是当前阶段的像素级真值。

## 5. 主体关系与遮挡编码

### 5.1 关系类型

每条关系由一个有向三元组表示：

```text
主体 A —关系→ 主体 B
```

推荐的第一版关系：

| 关系 | 例子 | 遮挡含义 |
| --- | --- | --- |
| `beside` | cat beside flower_pot | 通常无明显遮挡 |
| `in_front_of` | fox in front of crate | A 可能遮挡 B |
| `behind` | cloud behind tree | A 通常被 B 局部遮挡 |
| `inside` | person inside boat | 边界关系复杂度中等 |
| `on` | cup on table | 支撑关系，通常轻微接触 |
| `holding` | person holding umbrella | 局部接触和遮挡 |
| `riding` | cyclist riding bicycle | 多处局部接触，复杂度较高 |
| `covering` | cloud covering sun | 明确局部遮挡 |
| `crossing` | path crossing grass | 环境区域关系，第一版应限制使用 |

### 5.2 遮挡量

`occlusion_level` 是计划条件，不是精确像素标注：

- `none`：主体边界基本完整，只允许接触或并列。
- `light`：一个主体遮挡另一个主体少量边缘，约占被遮挡主体面积的 1%–20%。
- `medium`：存在清晰的前后关系，约遮挡 20%–45%。
- `high`：大面积遮挡但仍能识别两个主体，约遮挡 45%–65%。第一版不建议超过两个高遮挡主体。

Prompt 中不应依赖精确百分比，因为生图模型不保证像素级遵守。百分比用于计划、筛选和后续统计；发送给模型时使用“small part / clear partial occlusion / substantial but recognizable occlusion”等等级化表达。

### 5.3 关系图校验

计划器在渲染前检查：

1. 每个关系的两端都存在于 `entities`。
2. `in_front_of`、`behind` 和 `covering` 能够映射到唯一深度顺序。
3. 无自环和明显循环。
4. 关系数量不超过 `layer_count + 1`，避免场景过密。
5. 高复杂度关系必须提高 `complexity`，不能标为 simple。

## 6. Prompt 结构

每张图的 Prompt 应由固定段落和样本特定段落组成。固定段落保证风格一致，特定段落保证 benchmark 条件可控。

### 6.1 固定段落

固定段落保留当前仓库中的核心约束，但建议压缩成稳定版本：

```text
Create one polished, charming standalone 2D vector-style illustration for a semantic object-level layer separation benchmark. Use complete recognizable objects, appropriate internal details, coordinated flat-color shapes, clean contours, a harmonious lively palette, and a simple supportive background. Let the model choose a natural viewpoint, relative scale, spacing, and composition. Show only the final composite illustration. Do not use photorealism, painterly textures, gradients, intricate patterns, text, labels, watermarks, crowds, or tiny decorative clutter. Never render a listed entity as a featureless single-color cutout.
```

### 6.2 样本特定段落

特定段落只包含必要的语义控制条件：

1. 目标层数。
2. 完整实体列表。
3. 必要的身份描述（例如动物种类或对象种类），不枚举完整造型细节。
4. 对象之间明确需要的关系。
5. 有遮挡时的遮挡对象和大致遮挡等级。

不强制写入每个对象的画面占比、大小排序、精确位置、镜头距离或完整深度列表。没有明确遮挡条件的对象，由模型自行决定自然的相对位置和景深。

示例：

```text
Create a polished, charming 2D vector-style illustration with five main semantic entities: a simple sky, grassy ground, a wooden crate, an orange fox, and a red mushroom. Make the fox partially occlude the crate with a clear but moderate overlap. Keep the listed entities complete and recognizable, with natural internal illustration details. Choose a plausible scale, viewpoint, spacing, and composition for the scene. Do not add other independent objects or create a busy background.
```

### 6.3 Prompt 生成方式

建议采用“两层生成”：

1. **确定性渲染器**：根据结构化计划，用 Python 模板生成可复现 Prompt。这是正式 benchmark 的默认路径。
2. **可选语言改写器**：用一个文本模型把模板改写得更自然，但必须保留实体名称、数字、关系、层数和否定约束。改写后重新解析和校验，校验失败就回退到模板版本。

“提示词生成提示词”可以放在第二层，但不应让语言模型自由决定 benchmark 的标签。标签由覆盖矩阵和计划器决定，语言模型只负责表达和少量同义改写。

## 7. 结构化计划格式

建议使用 JSONL，每一行一个样本计划。下面是一个完整示例：

```json
{
  "sample_id": "sample_0001",
  "taxonomy": {
    "layer_count": 5,
    "subject_families": ["animal", "object", "plant", "environment"],
    "scene_type": "garden",
    "relation_pattern": "behind_and_foreground",
    "occlusion_level": "medium",
    "complexity": "moderate",
    "composition": "centered",
    "viewpoint": "slightly_top_down",
    "palette": "natural"
  },
  "entities": [
    {
      "id": "e1",
      "name": "sky",
      "category": "environment",
      "appearance": ["pale blue"],
      "depth": 0
    },
    {
      "id": "e2",
      "name": "grassy ground",
      "category": "environment",
      "appearance": ["simple green"],
      "depth": 1
    },
    {
      "id": "e3",
      "name": "wooden crate",
      "category": "object",
      "appearance": ["plain rectangular shape", "warm brown"],
      "depth": 2
    },
    {
      "id": "e4",
      "name": "fox",
      "category": "animal",
      "appearance": ["orange fur", "small blue scarf"],
      "depth": 3
    },
    {
      "id": "e5",
      "name": "mushroom",
      "category": "plant",
      "appearance": ["red cap", "short stem"],
      "depth": 4
    }
  ],
  "relations": [
    {"source": "e4", "type": "in_front_of", "target": "e3", "occlusion": "medium"},
    {"source": "e5", "type": "in_front_of", "target": "e3", "occlusion": "none"}
  ],
  "prompt_policy": {
    "allow_extra_objects": false,
    "allow_text": false,
    "allow_gradients": false,
    "background_detail": "low"
  }
}
```

## 8. Manifest 与可复现性

计划和实际生成记录分开保存。推荐的 `manifest.jsonl` 记录如下：

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

这两个量分别描述“目标对象有多少被遮住”和“两个对象的形状区域交叠多少”，不要把它们叫作 mIoU。当前 Qwen 输出主要是 PNG，尚未有对象级 amodal mask，因此本轮只保留 `occlusion_level` 作为 Prompt 条件，并在人工审核中记录 `occlusion_observed`（none / light / medium / high / unclear）。有了可编辑 SVG 的真实图层后，再计算上述比例和下游 mIoU。

## 10. Prompt 校验、去重与覆盖检查

### 10.1 结构校验

在调用 API 前，校验器应检查：

- `layer_count` 等于实体数量。
- 实体 ID 唯一，深度值连续。
- 所有关系引用有效实体。
- 实体数量在 2–6 之间。
- Prompt 中出现目标层数和主要实体名称。
- Prompt 没有“many objects”“crowd”“busy city”等与复杂度冲突的词。
- 禁止词（text、logo、watermark 等）仍然保留。

### 10.2 语义去重

不只比较完整 Prompt 字符串，还比较规范化签名：

```text
(subject names, scene type, relation types, layer count, occlusion)

`composition` 和 `viewpoint` 可以作为计划元数据记录，但在本轮不作为 Prompt 条件，也不应被误解为模型已经严格遵守的标签。
```

例如只改颜色或形容词不算新的语义样本。新样本至少应改变一个主体、场景、关系、层数或构图维度，并限制同一签名的重复次数。

### 10.3 覆盖统计

计划阶段输出 `coverage_report.json` 和可读的 Markdown 表格，至少统计：

- 各图层数数量。
- 各主体类别数量。
- 各场景数量。
- 各关系和遮挡等级数量。
- 各复杂度数量。
- 当前样本中出现的组合及未出现的组合。

第一轮约 10 张只把覆盖报告作为描述性记录，不以“覆盖全面”作为通过条件，也不为每个组合设硬配额。将来扩展正式 benchmark 时，再决定最低配额、允许的偏斜程度和是否使用 pairwise coverage；例如，50 张中大多数都落在同一层数和主体类别时，应视为覆盖不足。

## 11. 图像级筛选

Prompt 和结构化计划只能控制输入，不能保证模型完全遵守。因此生成后还需要一个轻量筛选环节。这个环节的目标是排除明显过难的 benchmark 输入，而不是给下游分层算法计算最终分数：

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

建议在审核表中增加字段：`estimated_layers`、`independent_foreground_entities`、`background_clutter`、`subject_completeness`、`cropped_subject`、`occlusion_observed`、`reason_code`。可以沿用 DnR FlatPic 的量表：`estimated_layers` 是合并内部细节后的预计层数；`independent_foreground_entities` 只数完整且相互独立的前景/中景对象；`background_clutter` 取 1–5（1 是简单空背景，3 需要人工判断，4–5 通常拒绝）；`subject_completeness` 取 0–1（完整主体建议不低于 0.8）；`cropped_subject` 是主对象是否被画面边界截断。生成目标仍是 2–6 层，超过 6 层或没有可解释对象关系时拒绝。本轮以人工确认和记录为主，不把这些估计值冒充精确像素指标。

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

### 12.2 建议新增的模块

第一版可以先保持一个仓库、多个 Python 文件，不必立即拆成复杂的包：

```text
qwen-batch-image/
├── qwen_batch_image.py       # 保留兼容模式：单 Prompt 批量生成
├── taxonomy.py               # 对象词表、关系词表、枚举和禁止组合
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
python .\plan_dataset.py --count 10 --output-dir .\dataset_demo --seed 20261029

# 检查计划、重复和覆盖情况
python .\validate_prompts.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl

# 读取已经冻结的计划并生成图片
$env:DASHSCOPE_API_KEY = "你的Key"
python .\generate_dataset.py --plans .\dataset_demo\plans.jsonl --prompts .\dataset_demo\prompts.jsonl --workers 3

# 生成可读的缩略图总览和审核表
python .\review_dataset.py --dataset-dir .\dataset_demo
```

原有的 `python qwen_batch_image.py --prompt ... --count ...` 继续可用，作为简单模式；benchmark 模式必须使用计划文件。

## 13. 是否使用 LLM 生成 Prompt

### 推荐做法

让代码先决定结构，让语言模型再润色表达：

```text
coverage matrix
→ deterministic plan
→ optional LLM wording
→ parser and validator
→ final prompt
```

这样可以得到自然的 Prompt，同时保持实验条件稳定。

### 不推荐做法

直接让 LLM 自由生成 50 个 Prompt，再从文本中猜测每张图片的图层数和关系。这样会出现：

- 有的 Prompt 漏写背景层。
- 同一个词在不同样本中代表不同粒度的对象。
- “一些树”“几只鸟”导致主体数量不可控。
- 复杂场景和简单场景比例无法统计。
- 生成失败后无法判断是模型问题还是 Prompt 条件问题。

如果使用 LLM 改写，必须保存改写前的结构化计划、改写后的 Prompt 和校验结果。

## 14. 一个 50 张样本的组织示例

可以把 50 张拆成五个小组，每组 10 张：

| 组别 | 层数 | 重点 |
| --- | --- | --- |
| A | 2–3 层 | 简单并列和轻微接触，建立基础成功率 |
| B | 3–4 层 | 动物/物体与背景的常规关系 |
| C | 4–5 层 | 前后遮挡、承载、手持或骑乘 |
| D | 5–6 层 | 多个环境层和中等遮挡，控制细节密度 |
| E | 混合 | 跨类别、跨视角、跨配色的均衡测试 |

每组内部再平衡主体类别和场景，不要把所有困难样本集中在同一个类别。每组都保留计划文件和覆盖统计，便于分别分析。

## 15. 实施顺序与验收标准

### 阶段一：计划器和渲染器

- 新增对象、关系和复杂度词表。
- 生成 10 个计划和 Prompt 草稿。
- 完成结构校验、重复检查和覆盖报告。
- 不调用生图 API。

验收：每个计划都能解释层数、实体、关系和复杂度；Prompt 能从计划重新生成。

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
| 模型忽略精确图层数 | 使用明确实体列表、禁止额外对象，生成后人工筛选 |
| Prompt 文字变化影响实验 | 保存结构化计划和最终 Prompt，固定模型和参数 |
| 组合重复 | 使用规范化签名去重，并做覆盖统计 |
| 复杂关系生成失败 | 逐步增加遮挡等级，先通过 10 张小样本校准 |
| API 限流或任务失败 | 保留现有并发、重试和单张失败机制 |
| Key 泄露 | 只读环境变量或运行时输入，`.gitignore` 排除本地配置 |
| 图片 URL 过期 | 下载后立即保存，manifest 只保留本地路径和 task_id |

## 17. 推荐的第一步

下一步先实现“阶段一”，只生成 10 个结构化计划、10 个最终 Prompt 和一份覆盖报告。确认计划中的主体数量、图层预算和关系表达符合预期后，再接入 API 生成少量图片。这样可以先验证 benchmark 的组织方式，再决定是否需要引入 LLM Prompt 改写器。

