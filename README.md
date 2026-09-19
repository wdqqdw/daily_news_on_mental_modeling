# Daily News on Mental Modeling

网站：https://wdqqdw.github.io/daily_news_on_mental_modeling/

一份持续积累的中文心智建模文献库。最外层是 **没看过 / 看过**，每种阅读状态下分为：

1. **Nature / Science / Cell 正刊**。
2. **Nature / Science / Cell 系列期刊**，每篇显示具体刊名，如 Nature Human Behaviour、Nature Neuroscience、Science Advances、Neuron。
3. **人工智能会议与期刊**，放在同一分类。
4. **arXiv / 预印本**，单列 arXiv 版本；只有独立核验正式发表后才归入期刊或会议。

首版 30 篇，本轮增加 14 篇至 44 篇，兼收近期研究与经典工作。覆盖情感与共情、心智与信念、意图与目标、人的世界模型、人格与心理状态、认知与决策。优先计算建模方法，也收录直接解释心智表征、对模型设计有价值的神经或行为证据。排除公司新闻、产品报告、纯物理世界模型及仅研究 AI 自身内部机制的工作。

## 文档与阅读

连续的文献条目包含中文标题、原题、完整刊物或会议名、原文链接与简述。展开「研究笔记」可查看研究对象、核心方法、研究依据和阅读边界，并写自己的备注。支持关键词搜索、研究方向、来源分类及发表时间排序；默认按最近收录排序，刚补入的旧文也容易找到。

点击「标记看过」会将论文移入已读文献，可撤销或移回。阅读记录和备注保存在当前浏览器，不自动跨设备同步；「导出笔记」保存 JSON 备份，「导入」合并已有论文的阅读状态与备注，保留本地现有备注。旧版阅读标记使用相同稳定标识，继续有效。禁用 JavaScript 时仍可阅读完整文献与原文链接。

旧日报保留在「旧版推送存档」，新首页不再按日生成固定三篇。

## 每日积累

GitHub Actions 在北京时间每天 **09:00**（UTC 01:00）触发，电脑不必开机；GitHub 排队可能导致延后。

- 从 arXiv 官方 Atom API、arXiv 在 DataCite 登记的 DOI 元数据、ACL Anthology 官方 XML 和 Crossref 发现候选；Nature / Science / Cell 系列使用具体 ISSN 检索。覆盖的刊名和 AI 来源白名单位于 `scripts/library_core.py`，检索主题位于 `scripts/library_sources.py`。自动检索不等于穷尽所有论文。
- **每天同时找新文和旧文，不再有两年限制。** 近期通道检索过去 365 天；历史通道从 arXiv 早期记录和 Crossref 1900 年起的记录回溯到一年前，并轮换旧年份 ACL 会议。arXiv 每天检索六个近期主题和三个历史主题；历史检索按主题、刊物轮换与分页，检索位置保存在 `data/collection_state.json`。
- 主题包括心智与社会世界模型、情绪动态与认知评价、信念和意图推断、人格与心理状态、认知和记忆、社会关系与人类行为模拟。arXiv 采用串行请求和至少三秒间隔。某个专题的 Atom API 失败时，使用 DataCite 中相同 arXiv 论文的登记摘要检索；只接受 arXiv DOI 和 arxiv.org 原文地址。按首次 Submitted 日期分新旧，不能把 DOI 登记时间当成论文发表时间；两套来源各自保存历史翻页位置，备用来源写入 fallback_sources。作者自填会议名不自动升级为正式发表；正式版本另核验会议、出版社或 DOI 记录。
- 用 DOI、arXiv 标识、标准化标题、链接及跨版本别名去重；与旧日报历史也去重。发现新题名或正式版本的 DOI 时补全别名，保留原条目 ID 与阅读状态。
- 使用固定版本的本地 Qwen2.5-7B-Instruct 复核主题和贡献，再依据公开摘要生成六个中文字段并复核。没有可用摘要时不生成解读。
- 近期与历史候选交替进入筛选，再兼顾研究方向和来源多样性。每轮最多审阅 24 个候选、尝试生成 8 篇研究笔记，以控制运行时间；**没有最低篇数要求**。不通过的论文 90 天内不反复审阅，处理错误三天后可重试。单篇失败不丢弃已经核验的条目；模型、全部来源或任一 arXiv 专题在两套服务上均失败时保留线上版本并让工作流报错。
- 新论文累积加入文献库，默认进入「没看过」；旧条目保留。没有通过筛选的新论文时记录检查成功，不重复旧论文。

页面的「收录更新」表示最后加入论文的日期，「最近检查」表示最近一次完成收集的时间。机器可读状态位于 `collection-status.json`，包含新增数、总数、新旧候选数、新旧收录数、arXiv 收录数及来源成功与失败情况。

摘要是阅读线索，不代替原文。自动模型筛选和摘要核验可能出错；研究边界包含对证据适用范围的编辑判断。原始摘要只在忽略的临时缓存中，不提交到公开仓库。原文日期仅有年月或年份时保留精度。

## 维护与验证

Python 3.12 标准库。模型、运行器固定版本及校验值见 `scripts/prepare_summary.py`。

```sh
python -m unittest discover -s tests -v
python scripts/build.py
python scripts/check_site.py
python scripts/update_library.py --discover-only
python scripts/prepare_summary.py
python scripts/update_library.py --dry-run --output .cache/verified-library.json
python scripts/update_library.py
```

手动验证：Actions → Mental Modeling · research library → Run workflow → 勾选 `verify_sources`。验证会实际调用全部检索来源，最多审阅 8 篇、尝试生成 2 篇笔记，但不会写入文献库或推进分页。取消勾选则运行一次完整收集。勾选 `discovery_only` 可只检查全部真实检索来源，跳过模型且不写入内容；arXiv 任一专题的两套来源都失败时仍会报错。普通代码推送只构建、验证与发布，不启动模型收集。

数据：`data/library.json` 是累积文献库，`data/collection_status.json` 是最近检查记录，`data/collection_state.json` 保存历史检索分页和近期筛选记录。首页由 `scripts/build.py` 使用 `site/notebook.css` 与 `site/library.js` 生成，页面内嵌样式与脚本。`scripts/build_digest.py` 和 `scripts/update.py` 仅保留旧日报实现供历史兼容测试，不参与每日工作流。普通重建不会改写历史快照。
