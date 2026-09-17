# Daily News on Mental Modeling

网站：https://wdqqdw.github.io/daily_news_on_mental_modeling/

每天三篇**对人进行心智计算建模的方法论文**，中文标题、短摘要、建模对象、核心方法、实验依据和研究边界。独立于 `daily_news`，没有公司新闻或跨学科泛热点。

## 研究范围

- 情感智能：认知评价、情绪推理、多模态情绪理解、共情建模。
- 心智与信念：Theory of Mind、信念追踪、认知状态、贝叶斯心智推断。
- 意图与目标：意图识别、目标推断、逆向规划、行为背后的动机。
- 人的世界模型：社会信念、社会互动和人的行为状态转移；排除纯物理世界模型。
- 人格与心理状态：人格差异、长期心理状态、个体认知与情绪动态。

主题相关性和方法贡献优先，兼顾新近程度及主题多样性。优先近半年，最长回溯 730 天；不限定 Nature/Science/Cell，不设置引用次数门槛，避免漏掉新会议工作。每期三个位置不硬性绑定主题。

期刊、会议与研究预印本均可候选，预印本明确标注“未经同行评审”。仅有 arXiv 的作者自报会议名不会自动升级为正式录用。创刊期 SWM 的 ICML 2026 记录另经会议官方列表核对。公司作者的正式研究论文可以收录；公司新闻、产品报告、泛技术报告、纯综述、纯数据集及没有方法贡献的评测不收录。

## 自动更新

GitHub Actions 在北京时间每天 **09:00**（UTC 01:00）触发，电脑不必开机。不依赖付费 API 或个人模型密钥。GitHub 可能排队，09:00 不是上线时间保证。网站更新即“推送”，不发送邮件或系统消息。

1. 抓取 ACL Anthology 官方 XML、Crossref 正式论文元数据与 arXiv 公开摘要。
2. 以标题中的明确心智对象、摘要中的计算方法及实验内容初筛。缺少可用摘要不生成解读。
3. 根据 DOI、arXiv ID、规范链接、中英文标题及跨版本别名永久去重。
4. 本地运行固定版本 Qwen2.5-7B-Instruct，判断是否真正提出人的建模方法；优先选择不同研究方向。
5. 生成六个中文解读字段，再对照同一摘要复核；输出不完整则不发布。
6. 写入当天数据、历史 HTML 与永久清单，构建并发布 GitHub Pages。

**模型筛选与自查可能出错，不能代替人工阅读全文。** 解读只依据公开摘要，不声称阅读全文；研究边界包含对证据适用范围的编辑判断。没有合格新论文、来源失败或解读失败时，保留上一期。页面始终显示真实期号日期，过期会提示。不会重推旧论文凑数，也不会生成虚构论文。

原文仅有年月或年份时，保留其日期精度；不伪造发表日。排序所需补齐的月日仅用于内部比较。

## 阅读与归档

每篇可标记“已了解”；历史页分为已了解和未了解，两栏分别搜索标题、方法、作者、期刊、DOI 和日期。状态保存在该网站当前浏览器的 localStorage，不跨设备同步。该状态与推送去重无关。独立 HTML 快照内嵌样式与交互脚本，普通重建不修改历史快照。

## 维护

Python 3.12 标准库；摘要运行器与模型的固定版本、哈希见 `scripts/prepare_summary.py`。缓存与原始摘要不进入公开仓库。

```sh
python -m unittest discover -s tests -v
python scripts/build.py
python scripts/check_site.py
python scripts/update.py --discover-only
python scripts/prepare_summary.py
python scripts/update.py --dry-run --output .cache/verified-issue.json
python scripts/update.py
```

手动验证：Actions → Mental Modeling · daily papers → Run workflow → 勾选 `verify_sources`。验证会产生一份新的候选日报，但不会覆盖已发布当天内容。取消勾选则生成当天新一期；当天已存在时保留。显式修订历史样式可用 `python scripts/build.py --rebuild-archive`，常规每日更新不使用这个参数。

预印本偏好配置位于 `data/policy.json` 的 `include_preprints`。正式的每日运行记录与错误可在仓库 Actions 查看。新站保留自己的去重清单，与旧站互不影响。
