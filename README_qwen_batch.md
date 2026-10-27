# 千问批量生图脚本

脚本文件是 [`qwen_batch_image.py`](qwen_batch_image.py)。它使用阿里云 DashScope 的异步文生图接口，逐个提交任务、等待完成并把图片下载到本地。每张图使用不同的 `seed`，因此同一提示词会生成不同结果。

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
如果你的 Key 属于国际站，或控制台给了不同的地域 Endpoint，需要把脚本顶部的 `SUBMIT_URL` 和 `TASK_URL` 改成控制台文档中的地址。`MODEL` 也要改为你的账号实际开通的千问生图模型。

不要把 API Key 提交到 Git 或公开网页；使用环境变量最安全。
