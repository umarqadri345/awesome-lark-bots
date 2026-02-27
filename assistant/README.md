# assistant/ — 助手机器人

飞书上的日常工作伴侣：备忘管理 + 日程管理 + 每日简报 + AI 对话。

## 文件说明

| 文件 | 做什么 |
|------|--------|
| `bot.py` | 飞书长连接入口 — 消息处理、意图分发、定时推送 |
| `__main__.py` | 启动入口 — `python3 -m assistant` |

依赖 `memo/`（备忘存储）和 `cal/`（日程聚合）两个模块。

## 快速使用

```bash
python3 -m assistant
```

然后在飞书上发消息：
- `备忘 买牛奶` — 记备忘
- `备忘列表` — 查看备忘
- `明天下午3点开会` — 加日程
- `今天` — 查看今日安排

## 需要的环境变量

`FEISHU_APP_ID` + `FEISHU_APP_SECRET` + `DEEPSEEK_API_KEY`

可选：`FEISHU_TOKEN_CALENDAR_CREATE`（加日程）、`FEISHU_TOKEN_CALENDAR_GET`（查日程）
