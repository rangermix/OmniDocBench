# Docling / Granite / Paddle：同一100页对比

状态：complete。更新：2026-09-08T22:38:40.070127+00:00。全量任务已按用户要求取消。

样本固定为原始清单前100页（索引0–99）：全部为 equation_hard，76页英文、24页中文。它是公式困难的顺序子集，不代表整个 OmniDocBench。

Docling、Granite复用已经完成的对应100页预测，只重新计算这100页的分数；Granite不再推理新页面。Paddle只推理这100页。三组均使用相同真值和固定官方评分实现。

| 方法 | 页数 | Overall ↑ | 文本编辑距离 ↓ | 公式 CDM ↑ | 表格 TEDS ↑ | 阅读顺序编辑距离 ↓ | 评分有效 |
|---|---:|---:|---:|---:|---:|---:|---|
| Docling（OCR、公式/代码增强） | 100/100 | 54.63 | 0.7144 | 68.93 | 66.40 | 0.4287 | 有效 |
| Docling + Granite 258M | 100/100 | 62.30 | 0.3112 | 70.99 | 47.03 | 0.2676 | 有效（匹配回退警告） |
| Docling + PaddleOCR-VL-1.6（自定义组合） | 100/100 | 77.10 | 0.3651 | 71.64 | 96.16 | 0.3281 | 有效 |

Docling + Granite 258M有1页文本匹配达到300秒上限，使用固定上游的匹配回退算法；该页仍计分，未修改预测或重跑以消除警告。CDM/TEDS有效性单独检查。

本子集的表格TEDS只有2个样本，不能据此判断整体表格能力；Overall包含这一小样本表格分数，须结合公式与文本指标阅读。

在这100页上，Paddle组合的Overall高于Granite 14.80分，其中表格项贡献16.38分，超过净差距；文本项抵消了一部分。Paddle公式CDM略高，Granite文本及阅读顺序编辑距离更低。Docling增强版累计推理时间最短。此结论不外推到其他页面类别。
完整性：三组各100页；Docling/Granite/Paddle分别有0/3/0页空白预测，分别有21/22/2页触及生成上限。三组CDM/TEDS超时、错误、异常均为0；Granite另有上述1次文本匹配回退。

## 时间与完整性

| 方法 | 100页累计推理分钟 | 首页面秒 | 后续页面平均秒 | 后续页面中位秒 | 生成上限命中 | 页面状态 |
|---|---:|---:|---:|---:|---:|---|
| Docling（OCR、公式/代码增强） | 59.56 | 73.30 | 35.36 | 28.05 | 28 | {'success': 100} |
| Docling + Granite 258M | 183.12 | 45.30 | 110.52 | 72.04 | 22 | {'success': 97, 'empty': 3} |
| Docling + PaddleOCR-VL-1.6（自定义组合） | 113.56 | 40.56 | 68.42 | 48.53 | 3 | {'success': 100} |

空白、失败和达到生成上限的页面全部保留在100页分母中。生成上限计数按区域/调用，不等于受影响页数。Overall = ((1−文本编辑距离)×100 + CDM + TEDS) / 3。
时间来自共享 Windows RTX 4090 主机上的不同运行时段；Paddle推理期间可能同时进行CPU评分。首页面包括Docling加载，Paddle模型初始化位于页面计时之前，不能据此推断纯GPU速度。曾跨越休眠的Granite第217页不在此100页子集中。
Paddle组合使用Docling版面/顺序及Paddle区域识别，并非官方Paddle完整管线；Granite为整页VLM路径，不使用标准Docling OCR/增强开关。

## 已有全量结果，仅作独立参考

以下结果覆盖1,651页，不能与上述100页分数直接混排。公开模型没有在本机重跑。

| 方法 | 范围 | Overall ↑ |
|---|---|---:|
| 本次已完成的Docling增强版 | 本机1,651页 | 57.46 |
| PaddleOCR-VL-1.6 | 上游公开全量 | 96.34 |
| MinerU2.5-Pro | 上游公开全量 | 95.75 |
| GLM-OCR | 上游公开全量 | 95.22 |
| PaddleOCR-VL-1.5 | 上游公开全量 | 94.93 |
| PaddleOCR-VL | 上游公开全量 | 94.18 |
| Youtu-Parsing | 上游公开全量 | 93.74 |
| Qianfan-OCR | 上游公开全量 | 93.90 |
| Ovis2.6-30B-A3B | 上游公开全量 | 93.70 |
| Logics-Parsing-v2 | 上游公开全量 | 93.33 |
| ABot-OCR | 上游公开全量 | 93.30 |
| FireRed-OCR | 上游公开全量 | 93.26 |
| MinerU-2.5 | 上游公开全量 | 93.04 |
| Gemini 3 Pro | 上游公开全量 | 92.91 |
| Gemini 3 Flash | 上游公开全量 | 92.62 |
| dots.ocr | 上游公开全量 | 90.77 |
| OpenDoc-0.1B | 上游公开全量 | 90.67 |
| DeepSeek-OCR 2 | 上游公开全量 | 90.25 |
| HunyuanOCR | 上游公开全量 | 89.95 |
| Qwen3-VL-235B | 上游公开全量 | 89.78 |
| Dolphin-v2 | 上游公开全量 | 89.50 |
| OCRVerse | 上游公开全量 | 88.60 |
| MonkeyOCR-pro-3B | 上游公开全量 | 88.57 |
| GPT-5.2 | 上游公开全量 | 86.59 |
| Dolphin-1.5 | 上游公开全量 | 86.52 |
| MinerU-Pipeline | 上游公开全量 | 86.47 |
| olmOCR | 上游公开全量 | 85.74 |
| Mistral OCR | 上游公开全量 | 85.66 |
| Kimi K2.5 | 上游公开全量 | 84.53 |
| InternVL3.5-241B | 上游公开全量 | 83.76 |
| Nanonets-OCR-s | 上游公开全量 | 83.61 |
| POINTS-Reader | 上游公开全量 | 83.37 |
| Marker | 上游公开全量 | 78.44 |

公开成绩来源：[固定版本 OmniDocBench v1.6_full](https://github.com/opendatalab/OmniDocBench/blob/193627ae9e97d89188468ed1ee3b7a856ff76044/README.md)。
结果、范围与评分计数见 [summary.json](summary.json)，固定100页清单见 [manifest.json](manifest.json)，模型与包版本见上级版本锁。全部原预测、记录、评分日志和复制凭据保存在本地运行证据中。
