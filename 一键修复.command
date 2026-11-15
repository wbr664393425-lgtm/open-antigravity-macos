#!/bin/bash
# 一键修复.command —— 在 Finder 里双击即可运行
#
#   ./一键修复.command              打补丁 → 校验签名 → 重启原来开着的 App
#   ./一键修复.command restore      从备份还原 → 校验签名 → 重启
#   ./一键修复.command doctor       只做诊断，不改任何文件
#   ./一键修复.command dry          只演示补丁计划（--dry-run），不写文件
#
# 默认会先问你一句才动手（回车 = 取消）。确认后才会关闭正在运行的 App。
# 无人值守时可加 -y 跳过确认：./一键修复.command -y
#
# 双击运行时窗口不会自动关闭，方便看结果。

set -uo pipefail

DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)

APP_MAIN="/Applications/Antigravity.app/Contents/MacOS/Antigravity"
IDE_MAIN="/Applications/Antigravity IDE.app/Contents/MacOS/Electron"
APP_NAME="Antigravity"
IDE_NAME="Antigravity IDE"

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
[ -t 1 ] || { C_OK=""; C_WARN=""; C_ERR=""; C_DIM=""; C_RST=""; }

say()  { printf '  %s\n' "$*"; }
ok()   { printf '%s  [+]%s %s\n' "$C_OK" "$C_RST" "$*"; }
warn() { printf '%s  [!]%s %s\n' "$C_WARN" "$C_RST" "$*"; }
err()  { printf '%s  [!]%s %s\n' "$C_ERR" "$C_RST" "$*"; }
dim()  { printf '%s      %s%s\n' "$C_DIM" "$*" "$C_RST"; }
title() { printf '\n%s── %s %s\n' "$C_DIM" "$*" "$(printf '─%.0s' {1..36})${C_RST}"; }

pause_exit() {
  [ "${AGPATCH_NO_PAUSE:-0}" = "1" ] && exit "${1:-0}"
  [ -t 0 ] || exit "${1:-0}"
  printf '\n  %s按回车关闭窗口…%s' "$C_DIM" "$C_RST"
  read -r _ || true
  exit "${1:-0}"
}

# ── 参数 ─────────────────────────────────────────────────────────────────────
MODE="patch"
ASSUME_YES=0
[ "${AGPATCH_YES:-0}" = "1" ] && ASSUME_YES=1

for arg in "$@"; do
  case "$arg" in
    patch|restore|doctor|dry) MODE="$arg" ;;
    -y|--yes) ASSUME_YES=1 ;;
    --no-pause) AGPATCH_NO_PAUSE=1 ;;
    -h|--help)
      printf '用法: %s [patch|restore|doctor|dry] [-y]\n' "$0"
      exit 0 ;;
    *) err "未知参数: $arg"; exit 2 ;;
  esac
done

# ── 找 agpatch ───────────────────────────────────────────────────────────────
AG=""
if command -v agpatch >/dev/null 2>&1; then
  AG=$(command -v agpatch)
elif [ -x "$DIR/agpatch" ]; then
  AG="$DIR/agpatch"
elif [ -x "$HOME/.local/share/agpatch/agpatch" ]; then
  AG="$HOME/.local/share/agpatch/agpatch"
else
  err "找不到 agpatch。请在仓库目录执行一次：bash install.sh"
  pause_exit 1
fi

[ -t 1 ] && clear 2>/dev/null
printf '\n  ╔══════════════════════════════════════════════════╗\n'
printf '  ║  Open AG Patcher — 一键修复（macOS）             ║\n'
printf '  ╚══════════════════════════════════════════════════╝\n'
dim "工具: $AG"

# ── 只诊断 / 只演示：不需要确认，也不碰运行中的 App ──────────────────────────
if [ "$MODE" = "doctor" ]; then
  title "诊断"
  "$AG" doctor
  pause_exit $?
fi

if [ "$MODE" = "dry" ]; then
  title "演示（不写任何文件）"
  "$AG" patch --dry-run
  pause_exit $?
fi

# ── 记录当前运行状态（结束后按原样恢复） ─────────────────────────────────────
APP_WAS_RUNNING=0
IDE_WAS_RUNNING=0
pgrep -f "$APP_MAIN" >/dev/null 2>&1 && APP_WAS_RUNNING=1
pgrep -f "$IDE_MAIN" >/dev/null 2>&1 && IDE_WAS_RUNNING=1

# ── 清楚说明要做什么，并请求确认 ─────────────────────────────────────────────
title "本次将执行"
if [ "$MODE" = "restore" ]; then
  say "从备份还原 → 重签 → 重启原来开着的 App"
else
  say "打补丁 → 重签 → 重启原来开着的 App"
fi

TO_CLOSE=()
[ "$APP_WAS_RUNNING" = "1" ] && TO_CLOSE+=("$APP_NAME")
[ "$IDE_WAS_RUNNING" = "1" ] && TO_CLOSE+=("$IDE_NAME")

if [ ${#TO_CLOSE[@]} -gt 0 ]; then
  warn "会先关闭正在运行的：${TO_CLOSE[*]}（未保存的窗口会被关掉）"
else
  dim "当前没有正在运行的 App，不需要关闭任何窗口"
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  if [ ! -t 0 ]; then
    err "当前没有可交互的终端，无法确认。"
    dim "无人值守请显式加参数：$0 $MODE -y"
    pause_exit 2
  fi
  printf '\n  %s继续？(y/N): %s' "$C_WARN" "$C_RST"
  read -r answer || answer=""
  case "$answer" in
    y|Y|yes|YES|是) : ;;
    *) say "已取消，没有修改任何文件。"; pause_exit 0 ;;
  esac
fi

# ── 关掉 App ─────────────────────────────────────────────────────────────────
quit_app() {
  local name=$1 main=$2 waited=0
  pgrep -f "$main" >/dev/null 2>&1 || return 0
  say "正在退出 $name …"
  osascript -e "quit app \"$name\"" >/dev/null 2>&1 || true
  while pgrep -f "$main" >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    [ "$waited" -ge 15 ] && break
  done
  if pgrep -f "$main" >/dev/null 2>&1; then
    warn "$name 15 秒内没有退出（可能有未保存的内容或正在确认对话框）"
    return 1
  fi
  ok "$name 已退出"
}

title "退出 App"
[ "$APP_WAS_RUNNING" = "1" ] && quit_app "$APP_NAME" "$APP_MAIN"
[ "$IDE_WAS_RUNNING" = "1" ] && quit_app "$IDE_NAME" "$IDE_MAIN"
[ "$APP_WAS_RUNNING" = "0" ] && dim "$APP_NAME 未在运行"
[ "$IDE_WAS_RUNNING" = "0" ] && dim "$IDE_NAME 未在运行"

# ── 执行 ─────────────────────────────────────────────────────────────────────
if [ "$MODE" = "restore" ]; then
  title "还原"
  "$AG" restore -y
  RESULT=$?
else
  title "打补丁"
  "$AG" patch -y
  RESULT=$?
fi

# ── 校验 ─────────────────────────────────────────────────────────────────────
title "校验"
"$AG" status | grep -E "Target:|Patch:" || true
printf '\n'
"$AG" doctor >/tmp/agpatch-doctor.log 2>&1
DOCTOR=$?
if [ "$DOCTOR" -eq 0 ]; then
  ok "签名与权限检查通过"
else
  warn "诊断发现问题，详情："
  grep -E "\[!\]|verification|codesign" /tmp/agpatch-doctor.log | sed 's/^/      /' | head -12
  dim "完整日志: /tmp/agpatch-doctor.log"
fi

# ── 恢复原来开着的 App ───────────────────────────────────────────────────────
title "重启 App"
if [ "$APP_WAS_RUNNING" = "1" ]; then
  open -a "$APP_NAME" 2>/dev/null && ok "已启动 $APP_NAME" || warn "启动 $APP_NAME 失败，请手动打开"
else
  dim "$APP_NAME 之前没开着，跳过"
fi
if [ "$IDE_WAS_RUNNING" = "1" ]; then
  open -a "$IDE_NAME" 2>/dev/null && ok "已启动 $IDE_NAME" || warn "启动 $IDE_NAME 失败，请手动打开"
else
  dim "$IDE_NAME 之前没开着，跳过"
fi

# ── 结果 ─────────────────────────────────────────────────────────────────────
printf '\n'
if [ "$RESULT" -eq 0 ]; then
  ok "完成。如果首次启动被 Gatekeeper 拦住，去「系统设置 → 隐私与安全性」点「仍要打开」。"
else
  err "执行失败（退出码 $RESULT），可再跑一次：$AG doctor"
fi
dim "回滚：$AG restore   状态：$AG status   日志：/tmp/agpatch-doctor.log"
pause_exit "$RESULT"
