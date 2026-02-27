#!/usr/bin/env bash
# 三体卖地球脑暴
# 使用前先确保 .env 中已配置 FEISHU_WEBHOOK（或在下面 export 你自己的）

set -e
cd "$(dirname "$0")"

# export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook'

TOPIC='给三体卖地球卖个高价：形成可执行、有记忆点的体验或传播方案（三体 IP、事件营销、创作者/玩家向均可）'
CONTEXT='briefs/santi_earth_brainstorm.md'

python3 -m brainstorm.run --topic "$TOPIC" --context "$CONTEXT"
