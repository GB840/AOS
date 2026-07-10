# code_review —— 单 skill 核心逻辑示例（不依赖 brain/fabric）

把某个「代码审查」类 skill 的核心逻辑抽出来独立运行，证明 skill 的能力本身是
自洽的，brain 只是调度壳。对应战略建议：让每个核心 skill 都能脱离大脑独立演示。

## 3 行启动

```bash
cd examples/code_review
pip install -r requirements.txt
python app.py --file ../src/skills/vimax.py
```

`--file` 可传单个文件或目录（递归审查 .py/.js/.ts，单次最多 5 个文件）。
模型配置同 chat_bot。
