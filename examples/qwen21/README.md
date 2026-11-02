# 本地千问 2.1 image 示例

把本地平台生成的示例图片放在这个目录，并为每张图片记录以下信息：

- 图片文件名；
- 使用的完整 Prompt 或 Prompt 文件；
- WordNet 主体和 synset；
- 模型名称和 seed；
- 是否出现黑边、阴影、渐变或复杂背景；
- 是否适合后续语义分层。

根目录 README 会汇总这些示例。收到新图片后，可以使用下面的条目格式补充：

```markdown
### 示例 001：单只牛

![单只牛](cow_001.png)

- 模型：Qwen 2.1 image
- 主体：cow / cattle.n.01
- Prompt：[`cow_prompt.md`](../../cow_prompt.md)
- 观察：记录黑边、阴影、背景可见性和主体复杂度。
```
