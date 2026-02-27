# AIlarkteams — 飞书 AI 团队协作工具集

一套在飞书上运行的 AI 机器人，覆盖**创意脑暴、项目规划、日常助手、素材 Prompt 生成、舆情监控**五大场景。

## 五个机器人一览

| 机器人 | 一句话介绍 | 在飞书上怎么用 | 启动命令 |
|--------|-----------|---------------|----------|
| **脑暴机器人** | 5 个 AI 角色模拟真人团队讨论，四轮产出创意方案 | 发消息：`洛阳茶馆 × 光遇跨界快闪` | `python3 -m brainstorm` |
| **规划机器人** | 六步结构化决策，从问题定义到执行计划 | 发消息：`Q3 用户增长策略` | `python3 -m planner` |
| **助手机器人** | 记备忘、管日程、每日自动简报 | 发消息：`备忘 买牛奶` / `明天3点开会` | `python3 -m assistant` |
| **创意 Prompt** | 生成 Seedance / Nano Banana 等 AI 工具可用的素材 prompt | 发消息：`云海日出的抖音预告` | `python3 -m creative` |
| **舆情监控** | 从微博/抖音/小红书等 15 个平台采集社媒数据 | 发消息：`周报` / `采集 光遇 @微博 7天` | `python3 -m sentiment` |

五个机器人**共享底层模块**（LLM 调用、飞书 API），各自独立运行、互不干扰。

---

## 新手上路（3 步开始）

### 第 1 步：安装依赖

```bash
# 需要 Python 3.11+
pip3 install -r requirements.txt
```

### 第 2 步：配置环境变量

```bash
cp .env.example .env
```

然后用编辑器打开 `.env`，按需填入以下内容：

| 变量 | 必填？ | 说明 |
|------|--------|------|
| `FEISHU_APP_ID` | 必填 | 飞书应用的 App ID（所有机器人可共用） |
| `FEISHU_APP_SECRET` | 必填 | 飞书应用的 App Secret |
| `DEEPSEEK_API_KEY` | 必填 | DeepSeek 的 API Key（主力大模型） |
| `DOUBAO_API_KEY` | 脑暴必填 | 豆包的 API Key |
| `KIMI_API_KEY` | 脑暴必填 | Kimi 的 API Key |
| `FEISHU_WEBHOOK` | 推荐 | 飞书群 Webhook URL，用于实时推送讨论过程 |
| `JOA_TOKEN` | 舆情必填 | JustOneAPI 的 Token，用于社媒数据采集 |

> 完整变量说明见 `.env.example` 文件中的注释。

### 第 3 步：启动机器人

```bash
# 选一个启动（或同时运行多个）
python3 -m brainstorm    # 脑暴机器人
python3 -m planner       # 规划机器人
python3 -m assistant     # 助手机器人
python3 -m creative      # 创意 Prompt 机器人
python3 -m sentiment     # 舆情监控机器人
```

启动后，在飞书上给对应的机器人发消息就能用了。

---

## 飞书开放平台配置（首次需要）

每个机器人需要一个飞书应用（也可以多个机器人共用一个应用）：

1. 登录 [飞书开放平台](https://open.feishu.cn)，创建一个「自建应用」
2. 在应用详情页获取 **App ID** 和 **App Secret**，填入 `.env`
3. 进入「事件订阅」→ 选择 **「长连接」** 模式
4. 添加事件：**「接收消息 v2.0」**（事件名：`im.message.receive_v1`）
5. 发布应用
6. 运行 `python3 -m xxx` 并保持程序运行

> 程序启动后会自动通过长连接(WebSocket)接收飞书消息，断线自动重连。

---

## 五个机器人详解

### 1. 脑暴机器人 (`brainstorm/`)

给机器人发消息即可触发 AI 多角色脑暴。

**坚果五仁团队**（5 个 AI 角色，各有分工）：

| 角色 | 定位 | 使用的大模型 | 职责 |
|------|------|-------------|------|
| 芝麻仁 | 现实架构师 | DeepSeek | 执行可行性、成本、约束 |
| 核桃仁 | 玩家化身 | 豆包 | 第一人称验证体验真实性 |
| 杏仁 | 体验导演 | Kimi | 设计具体瞬间、情绪峰值 |
| 瓜子仁 | 传播架构师 | Kimi | 设计可分享单元、传播路径 |
| 松子仁 | 体验总成 | DeepSeek | 收敛、裁决、产出最终交付物 |

**四轮讨论流程：**
1. **Idea Expansion（发散）** → 产出约 10 个体验方向
2. **Experience Embodiment（具象）** → 压缩为 6 个可执行候选
3. **Brutal Selection（淘汰）** → 三道筛子，只留 3 个方向
4. **Execution Conversion（交付）** → 讨论总结 + Claude Code prompt + 视觉 prompt

**也可 CLI 运行（不需要飞书）：**
```bash
python3 -m brainstorm.run --topic "洛阳茶馆 × 光遇跨界快闪" --context "背景材料"
```

### 2. 规划机器人 (`planner/`)

给机器人发消息即可启动理性规划。

**五种模式：**
| 模式 | 包含步骤 | 适合场景 |
|------|---------|---------|
| 完整规划 | 问题定义→现状分析→方案生成→评估矩阵→执行计划→反馈机制 | 重大决策 |
| 快速模式 | 问题定义→方案生成→评估→执行计划 | 日常规划 |
| 分析模式 | 问题定义+现状分析 | 想先看看分析 |
| 方案模式 | 生成 3 个方案 | 只要选项 |
| 执行模式 | 执行计划 | 已有方向，要落地步骤 |

**切换模式：** 在消息前加模式名，如 `快速模式：下周产品发布计划`

**也可 CLI 运行：**
```bash
python3 -m planner.run --topic "Q3 用户增长策略" --mode "快速模式"
```

### 3. 助手机器人 (`assistant/`)

日常工作伴侣：记备忘、查日程、每日简报。

**备忘管理：**
```
备忘 买牛奶               → 记一条备忘
任务 写周报               → 同上（「任务」「待办」「todo」都行）
todo 回复邮件 #要事       → 记备忘并标记为「要事」
备忘列表                  → 查看最近 10 条
所有备忘                  → 查看全部
灵感备忘                  → 按分类筛选
清除备忘 3                → 删除第 3 条
第2条标成灵感             → 修改分类
```

**日程管理：**
```
明天下午3点开会            → 自动加入飞书日历
今天 / 明天               → 查看今日/明日全部日程（飞书+Google+备忘汇总）
```

**每日简报（自动推送）：**
- 08:00 晨间简报：今日日程 + 重点 + 注意事项
- 18:00 收尾 checklist：完成情况 + 明日准备

### 4. 创意 Prompt 机器人 (`creative/`)

告诉它你想要什么素材，它生成可以直接复制到 AI 工具的 prompt。

**两种使用方式：**
```
直接生成：归来季云海和重逢主题的抖音预告       → 立即出 prompt
先聊后出：聊聊：我想做一个关于重逢的视频       → 多轮讨论
         生成                                  → 从讨论内容生成正式 prompt
```

**修改和品牌切换：**
```
改一下：更温暖一些         → 基于上次结果修改
品牌：sky                  → 切换到光遇品牌 profile
品牌                       → 查看可用品牌列表
```

**输出内容：**
- 中文结构化 Prompt（画面/场景/镜头/氛围/风格）
- Seedance 英文版（可直接复制粘贴到 AI 工具）
- 超 15 秒需求自动分镜 + 角色一致性建议
- 配套平台文案

### 5. 舆情监控机器人 (`sentiment/`)

从社交媒体平台采集数据，生成结构化分析材料。

**快捷报告（一键使用）：**
```
周报                       → 光遇舆情周报（7天）
双周报 thatskyshop         → thatskyshop 双周报（14天）
月报                       → jenova陈星汉月报（30天）
```

**自定义采集：**
```
采集 原神 崩坏星穹铁道 @微博 @B站 7天
采集 iPhone17 @全平台 3天 200条
光遇 @抖音 @小红书 14天 50条
```

**支持 15 个平台：**
- 国内社媒：微博、抖音、小红书、B站、快手、知乎、头条、微信
- 海外社媒：TikTok、YouTube、Twitter、Instagram、Facebook
- 电商平台：淘宝、拼多多

**可选 AI 分析：** 在指令末尾加 `+分析`，同时生成 AI 分析报告

---

## 项目结构

```
AIlarkteams/
│
├── core/                     # 共享核心模块（所有机器人都用）
│   ├── llm.py                #   大模型调用封装（DeepSeek/豆包/Kimi）
│   ├── feishu_client.py      #   飞书 API（消息、日历、文档）
│   ├── feishu_webhook.py     #   飞书群 Webhook 推送
│   └── utils.py              #   工具函数（截断、时间戳、文件保存）
│
├── brainstorm/               # 脑暴机器人
│   ├── bot.py                #   飞书长连接入口（接收消息 → 启动脑暴）
│   ├── run.py                #   主流程引擎（四轮讨论 + 交付物生成）
│   └── __main__.py           #   启动入口：python3 -m brainstorm
│
├── planner/                  # 规划机器人
│   ├── bot.py                #   飞书长连接入口
│   ├── run.py                #   主流程引擎（六步规划）
│   ├── prompts.py            #   每一步的提示词和输出格式定义
│   └── __main__.py           #   启动入口：python3 -m planner
│
├── assistant/                # 助手机器人
│   ├── bot.py                #   飞书长连接入口（备忘+日程+对话）
│   └── __main__.py           #   启动入口：python3 -m assistant
│
├── creative/                 # 创意 Prompt 机器人
│   ├── bot.py                #   飞书长连接入口（生成+讨论+品牌切换）
│   ├── knowledge.py          #   品牌知识库和提示词构建
│   └── __main__.py           #   启动入口：python3 -m creative
│
├── sentiment/                # 舆情监控机器人
│   ├── bot.py                #   飞书长连接入口（指令解析+引导对话）
│   ├── runner.py             #   采集流程编排（采集→统计→导出→上传）
│   ├── exporter.py           #   数据导出（JSON + Markdown）
│   ├── feishu_api.py         #   飞书 API（舆情机器人专用）
│   ├── github_client.py      #   GitHub 上传
│   └── __main__.py           #   启动入口：python3 -m sentiment
│
├── memo/                     # 备忘模块（助手机器人使用）
│   ├── store.py              #   本地 JSON 存储（线程安全）
│   └── intent.py             #   意图解析（关键词 + LLM）
│
├── cal/                      # 日程模块（助手机器人使用）
│   ├── aggregator.py         #   多源日程聚合（飞书 + Google + 备忘）
│   ├── google_calendar.py    #   Google 日历拉取
│   ├── daily_brief.py        #   每日简报生成与推送
│   └── push_target.py        #   推送接收人管理
│
├── prompts.json              # 脑暴「坚果五仁」角色配置
├── CN-MKT-Skills/            # 营销技能知识库（规划机器人可参考）
├── briefs/                   # 脑暴主题 brief 文件
├── runs/                     # 运行记录输出（自动生成）
├── data/                     # 数据目录（备忘、推送目标等）
│
├── requirements.txt          # Python 依赖列表
├── .env.example              # 环境变量配置模板
├── docker-compose.yml        # Docker 部署配置
└── README.md                 # 本文件
```

---

## LLM 分配策略

本项目同时使用三家大模型服务商，各有分工：

| 大模型 | 擅长 | 在哪用 |
|--------|------|--------|
| **DeepSeek** | 逻辑推理、结构化输出 | 规划机器人全程、助手机器人、脑暴中的策略角色、创意 Prompt |
| **豆包(Doubao)** | 创意发散 | 脑暴中的创意角色（核桃仁） |
| **Kimi** | 长文本理解 | 脑暴中的素材角色、最终交付物生成 |

三家都兼容 OpenAI 的 API 协议，统一通过 `core/llm.py` 调用。

---

## Docker 部署

```bash
# 启动所有机器人
docker-compose up -d

# 启动指定机器人
docker-compose up -d brainstorm planner

# 查看日志
docker-compose logs -f brainstorm
```

---

## 常见问题

**Q: 程序启动后提示连接失败？**
检查：1) App ID / App Secret 是否正确  2) 应用是否已发布  3) 网络是否能访问 open.feishu.cn

**Q: 脑暴/规划结果在飞书群里看不到？**
确认 `FEISHU_WEBHOOK` 是否配置。结果通过 Webhook 推送到群，如果没配，只会保存到本地 `runs/` 目录。

**Q: 助手的日程管理提示「权限不足」？**
往个人日历加日程需要用户身份授权。请在 `.env` 中配置 `FEISHU_TOKEN_CALENDAR_CREATE`。

**Q: 可以只运行其中一个机器人吗？**
可以。每个机器人完全独立，按需启动即可。最低只需要 `FEISHU_APP_ID` + `FEISHU_APP_SECRET` + `DEEPSEEK_API_KEY`。

**Q: 运行记录保存在哪？**
所有运行结果保存在项目根目录的 `runs/` 文件夹，格式为 Markdown。
