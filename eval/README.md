# 评测（eval）

目标：把"感觉答得还行"变成可对比的数字。

## 目录

```
eval/
├─ build_candidates.py   # 从库里自动出题（LLM），产出 candidates.jsonl
├─ candidates.jsonl      # 机器生成、待人工审核
├─ golden.jsonl          # 人工审核后的黄金集（评测用这个）
├─ run_eval.py           # 跑评测：召回 / 引用 / 拒答 / 延迟
├─ baseline.json         # 指标基线（门禁用）
└─ last_run.json         # 最近一次明细（逐题）
```

## 第一次使用

```bash
# 1. 生成候选题（约 5 分钟，费用几元）
python eval/build_candidates.py --video 45 --pdf 25 --docx 10 --image 2 --neg 15

# 2. 人工审核：打开 candidates.jsonl，逐条看
#    删掉：问题不自然、答案在原文找不到、出处不唯一、重复
#    通过后另存为 golden.jsonl

# 3. 跑评测并存基线
python eval/run_eval.py --file eval/golden.jsonl --save-baseline

# 4. 以后每次改动后对比
python eval/run_eval.py --file eval/golden.jsonl --check
```

## 指标

| 指标 | 含义 | 目标 |
|---|---|---|
| Recall@5 | 正确出处在召回前 5 的比例 | ≥ 0.85 |
| MRR | 正确出处排名的倒数均值 | ≥ 0.70 |
| 引用准确率 | 答案引用落在正确出处上的比例 | ≥ 0.95 |
| 拒答准确率 | 负样本回答"没有提到"的比例 | ≥ 0.90 |
| P95 延迟 | 端到端 95 分位耗时 | ≤ 6000 ms |

## 匹配规则

- 视频：同一 video_id，且 gold 时间落在召回块的 [start-30s, end+30s] 区间内（或起点相差 ≤90 秒）；
- PDF：同一页或相邻页（±1）；
- Word / 图片：同一 locator。

## 门禁

`run_eval.py --check` 会对比 `baseline.json`：

- 低于 `GATE` 里的 `min` → 失败；
- 比基线下降超过 `drop_max` → 失败。

退出码非 0，可接到 CI 或提交前钩子。

## 加题

往 `golden.jsonl` 追加一行即可：

```json
{"id":"q101","type":"fact","question":"…",
 "answer_points":["…"],"sources":[{"video_id":22,"locator":"图1","quote":"…"}]}
```

负样本 `type` 写 `negative`，`sources` 留空。

## 注意

- **别用同一套题调参又验收**：留 30 条不参与调参的测试集；
- 每次只改一个变量，跑一次评测，看哪项升、哪项掉；
- 机器生成的题必须人工过一遍，否则测的是"出题模型"不是"知识库"。
