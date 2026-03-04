#!/usr/bin/env bash
set -euo pipefail

# 一键运行 CN MKT 数据归档与复盘
# - 自动加载项目根目录 .env（用于 LLM / 飞书 / Google 凭证）
# - 支持指定 source / targets / project / google 参数
#
# 示例：
#   ./scripts/run_cn_mkt.sh
#   ./scripts/run_cn_mkt.sh --source "$HOME/Downloads/CN MKT data" --targets 1
#   ./scripts/run_cn_mkt.sh --targets 2 --project "CN社媒项目管理"
#   ./scripts/run_cn_mkt.sh --targets 3 --google-sheet-id "xxx" --google-service-account-json "/path/sa.json"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f ".env" ]]; then
  # 安全加载 .env 到当前 shell
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

SOURCE_DIR="${HOME}/Downloads/CN MKT data"
OUT_DIR="${ROOT_DIR}/data/cn_mkt"
TARGETS="1"
PROJECT_NAME=""
TEAM_CODE=""
WITH_INSIGHTS="1"
INSIGHT_FAST="0"
PUBLISH="0"
GOOGLE_SHEET_ID=""
GOOGLE_SA_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --targets)
      TARGETS="$2"
      shift 2
      ;;
    --project)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --team-code)
      TEAM_CODE="$2"
      shift 2
      ;;
    --with-insights)
      WITH_INSIGHTS="1"
      shift
      ;;
    --no-insights)
      WITH_INSIGHTS="0"
      shift
      ;;
    --publish)
      PUBLISH="1"
      shift
      ;;
    --insight-fast)
      INSIGHT_FAST="1"
      shift
      ;;
    --google-sheet-id)
      GOOGLE_SHEET_ID="$2"
      shift 2
      ;;
    --google-service-account-json)
      GOOGLE_SA_JSON="$2"
      shift 2
      ;;
    *)
      echo "[run_cn_mkt] Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

CMD=(python3 -m cn_mkt_data
  --source "${SOURCE_DIR}"
  --out-dir "${OUT_DIR}"
  --targets "${TARGETS}"
)

if [[ "${WITH_INSIGHTS}" == "1" ]]; then
  CMD+=(--with-insights)
fi

if [[ "${INSIGHT_FAST}" == "1" ]]; then
  CMD+=(--insight-fast)
fi

if [[ "${PUBLISH}" == "1" ]]; then
  CMD+=(--publish)
fi

if [[ -n "${PROJECT_NAME}" ]]; then
  CMD+=(--project "${PROJECT_NAME}")
fi

if [[ -n "${TEAM_CODE}" ]]; then
  CMD+=(--team-code "${TEAM_CODE}")
fi

if [[ -n "${GOOGLE_SHEET_ID}" ]]; then
  CMD+=(--google-sheet-id "${GOOGLE_SHEET_ID}")
fi

if [[ -n "${GOOGLE_SA_JSON}" ]]; then
  CMD+=(--google-service-account-json "${GOOGLE_SA_JSON}")
fi

echo "[run_cn_mkt] Running: ${CMD[*]}"
"${CMD[@]}"

