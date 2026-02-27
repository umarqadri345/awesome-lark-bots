#!/usr/bin/env bash
# 洛阳茶馆 × 光遇创作者雅集脑暴
# 使用前先确保 .env 中已配置 FEISHU_WEBHOOK（或在下面 export 你自己的）

set -e
cd "$(dirname "$0")"

# export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook'

TOPIC='在洛阳茶馆里办《光遇》创作者雅集：低成本、让创作者被打动、引起更大范围玩家注意'
CONTEXT='CN-MKT-Skills briefs/luoyang_teahouse_guangyu.md'

python3 -m brainstorm.run --topic "$TOPIC" --context "$CONTEXT"
