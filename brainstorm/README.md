# brainstorm/ — 脑暴机器人

5 个 AI 角色（坚果五仁）模拟真人团队，四轮结构化讨论，产出可落地的创意方案。

## 文件说明

| 文件 | 做什么 |
|------|--------|
| `bot.py` | 飞书长连接入口 — 接收消息、解析主题、启动脑暴流程 |
| `run.py` | 脑暴主引擎 — 编排四轮讨论、角色发言、生成交付物 |
| `__main__.py` | 启动入口 — `python3 -m brainstorm` 就是运行这个 |

## 快速使用

```bash
# 方式一：飞书长连接（推荐）
python3 -m brainstorm
# 然后在飞书上给机器人发消息

# 方式二：命令行直接运行
python3 -m brainstorm.run --topic "你的脑暴主题"
```

## 需要的环境变量

`FEISHU_APP_ID` + `FEISHU_APP_SECRET` + `DEEPSEEK_API_KEY` + `DOUBAO_API_KEY` + `KIMI_API_KEY`

可选：`FEISHU_WEBHOOK`（推送到飞书群）
