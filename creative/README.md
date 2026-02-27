# creative/ — 创意 Prompt 机器人

描述你想要的素材，它生成 Seedance / Nano Banana 等 AI 工具可直接使用的 prompt。

## 文件说明

| 文件 | 做什么 |
|------|--------|
| `bot.py` | 飞书长连接入口 — 消息分类、prompt 生成、讨论模式、品牌切换 |
| `knowledge.py` | 品牌知识库 — 加载品牌 profile、构建提示词 |
| `__main__.py` | 启动入口 — `python3 -m creative` |

## 快速使用

```bash
python3 -m creative
```

然后在飞书上发消息：
- 直接出 prompt：`归来季云海和重逢主题的抖音预告`
- 先聊后出：`聊聊：我想做一个关于重逢的视频` → 讨论后发 `生成`
- 修改：`改一下：更温暖一些`
- 切品牌：`品牌：sky`

## 需要的环境变量

`FEISHU_APP_ID` + `FEISHU_APP_SECRET` + `DEEPSEEK_API_KEY`
