#!/usr/bin/env bash
# install.sh — 把 Open AG Patcher 装成 macOS 终端里的 agpatch 命令
#
#   bash install.sh              # 安装到 ~/.local（无需 sudo、无需 venv、无第三方依赖）
#   bash install.sh --link       # 开发模式：只建符号链接，改代码立即生效
#   bash install.sh --uninstall  # 卸载（不会动 Antigravity 里的备份）
#
# 安装后：
#   agpatch              # 查看检测结果与补丁状态
#   agpatch patch        # 一键打补丁（需要时自动 sudo）
#   agpatch doctor       # 环境 / 签名诊断
set -euo pipefail

SRC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
PREFIX="${AGPATCH_PREFIX:-$HOME/.local}"
TARGET_DIR="$PREFIX/share/agpatch"
BIN_DIR="$PREFIX/bin"
BIN="$BIN_DIR/agpatch"

MODE="copy"
DO_UNINSTALL=0
EDIT_PATH=1
PYTHON_BIN="${AGPATCH_PYTHON:-}"

C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
if [ ! -t 1 ] || [ -n "${NO_COLOR:-}" ]; then
  C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""; C_DIM=""; C_RST=""
fi

info() { printf '%s[*]%s %s\n' "$C_INFO" "$C_RST" "$*"; }
ok()   { printf '%s[+]%s %s\n' "$C_OK" "$C_RST" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_WARN" "$C_RST" "$*"; }
err()  { printf '%s[!]%s %s\n' "$C_ERR" "$C_RST" "$*" >&2; }
dim()  { printf '%s    %s%s\n' "$C_DIM" "$*" "$C_RST"; }

usage() {
  cat <<EOF
用法: bash install.sh [选项]

选项:
  --link              开发模式（符号链接到当前 checkout，不复制）
  --uninstall         卸载 agpatch（保留 Antigravity 内部备份）
  --prefix DIR        安装前缀（默认: \${AGPATCH_PREFIX:-$HOME/.local}）
  --python PATH       指定 python3 解释器
  --no-path           不修改 shell 配置文件里的 PATH
  -h, --help          显示帮助

安装位置:
  启动器   $BIN
  代码     $TARGET_DIR/source
EOF
}

while [ $# -gt 0 ]; do
  case $1 in
    --link) MODE="link" ;;
    --uninstall) DO_UNINSTALL=1 ;;
    --prefix) shift; PREFIX="${1:?--prefix 需要一个目录}"; TARGET_DIR="$PREFIX/share/agpatch"; BIN_DIR="$PREFIX/bin"; BIN="$BIN_DIR/agpatch" ;;
    --prefix=*) PREFIX="${1#*=}"; TARGET_DIR="$PREFIX/share/agpatch"; BIN_DIR="$PREFIX/bin"; BIN="$BIN_DIR/agpatch" ;;
    --python) shift; PYTHON_BIN="${1:?-python 需要一个路径}" ;;
    --python=*) PYTHON_BIN="${1#*=}" ;;
    --no-path) EDIT_PATH=0 ;;
    -h|--help) usage; exit 0 ;;
    *) err "未知参数: $1"; usage; exit 2 ;;
  esac
  shift
done

# ── rc 文件里 PATH 块的增删 ───────────────────────────────────────────────────
RC_FILES=()
case "${SHELL:-}" in
  */zsh) RC_FILES+=("$HOME/.zshrc") ;;
  */bash) RC_FILES+=("$HOME/.bash_profile") ;;
  *) RC_FILES+=("$HOME/.zshrc"); RC_FILES+=("$HOME/.bash_profile") ;;
esac
[ -f "$HOME/.profile" ] && RC_FILES+=("$HOME/.profile")

PATH_MARK_BEGIN="# >>> agpatch >>>"
PATH_MARK_END="# <<< agpatch <<<"

add_path_block() {
  local rc="$1"
  [ -f "$rc" ] || return 0
  if grep -qF "$PATH_MARK_BEGIN" "$rc" 2>/dev/null; then
    return 0
  fi
  {
    printf '\n%s\n' "$PATH_MARK_BEGIN"
    printf '# added by Open AG Patcher install.sh\n'
    printf 'export PATH="%s:$PATH"\n' "$BIN_DIR"
    printf '%s\n' "$PATH_MARK_END"
  } >>"$rc"
  ok "已把 $BIN_DIR 加入 PATH: $rc"
}

remove_path_blocks() {
  local rc="$1"
  [ -f "$rc" ] || return 0
  grep -qF "$PATH_MARK_BEGIN" "$rc" 2>/dev/null || return 0
  # 删除标记块之间的内容（含标记行）
  awk -v b="$PATH_MARK_BEGIN" -v e="$PATH_MARK_END" '
    index($0,b)==1 {skip=1}
    skip==0 {print}
    index($0,e)==1 {skip=0}
  ' "$rc" >"$rc.agpatch.tmp" && mv "$rc.agpatch.tmp" "$rc"
  ok "已从 $rc 移除 PATH 配置"
}

# ── 卸载 ─────────────────────────────────────────────────────────────────────
if [ "$DO_UNINSTALL" -eq 1 ]; then
  if [ -L "$BIN" ] || [ -f "$BIN" ]; then
    rm -f "$BIN"; ok "已删除启动器: $BIN"
  else
    dim "启动器不存在: $BIN"
  fi
  if [ -d "$TARGET_DIR" ]; then
    rm -rf "$TARGET_DIR"; ok "已删除: $TARGET_DIR"
  fi
  for rc in "${RC_FILES[@]}"; do remove_path_blocks "$rc"; done
  ok "卸载完成。Antigravity 里的 .bak/.agybak 备份没有动，可用原 patcher 还原。"
  exit 0
fi

# ── 环境检查 ─────────────────────────────────────────────────────────────────
if [ "$(uname -s)" != "Darwin" ]; then
  warn "当前不是 macOS（$(uname -s)）——patched 逻辑仍可用，但重签名只对 macOS 生效。"
fi

if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3)
  elif [ -x /usr/bin/python3 ]; then
    PYTHON_BIN=/usr/bin/python3
  else
    err "找不到 python3。请先安装 Xcode Command Line Tools: xcode-select --install"
    exit 1
  fi
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys
sys.exit(0 if sys.version_info >= (3, 8) else 1)
PY
then
  err "需要 Python 3.8+，当前: $("$PYTHON_BIN" -V 2>&1)"
  exit 1
fi
dim "python: $PYTHON_BIN ($("$PYTHON_BIN" -V 2>&1))"

# macOS 重签名依赖 codesign
if ! command -v codesign >/dev/null 2>&1; then
  warn "未找到 codesign —— 打补丁后无法自动 ad-hoc 重签。"
  dim "安装命令行工具: xcode-select --install"
fi

# ── 安装 ─────────────────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"

if [ "$MODE" = "link" ]; then
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  ln -s "$SRC_DIR/source" "$TARGET_DIR/source"
  cp "$SRC_DIR/agpatch" "$TARGET_DIR/agpatch"
  chmod +x "$TARGET_DIR/agpatch"
  ok "已链接代码: $TARGET_DIR/source -> $SRC_DIR/source"
else
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  cp -R "$SRC_DIR/source" "$TARGET_DIR/source"
  cp "$SRC_DIR/agpatch" "$TARGET_DIR/agpatch"
  chmod +x "$TARGET_DIR/agpatch"
  # 清掉可能的缓存，避免拷贝后 pyc 与源码不一致
  find "$TARGET_DIR/source" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  ok "已安装代码: $TARGET_DIR/source"
fi

ln -sfn "$TARGET_DIR/agpatch" "$BIN"
ok "已创建命令: $BIN"

PATH_EDITED=0
if [ "$EDIT_PATH" -eq 1 ]; then
  case ":$PATH:" in
    *":$BIN_DIR:"*) dim "PATH 已包含 $BIN_DIR" ;;
    *) for rc in "${RC_FILES[@]}"; do add_path_block "$rc"; PATH_EDITED=1; done ;;
  esac
fi

# ── 冒烟测试 ─────────────────────────────────────────────────────────────────
printf '\n'
info "冒烟测试..."
if "$BIN" --version >/dev/null 2>&1; then
  ok "agpatch 可用: $("$BIN" --version | head -1)"
else
  err "agpatch 启动失败，请手动运行看报错: $BIN --version"
  exit 1
fi

# ── 下一步提示 ───────────────────────────────────────────────────────────────
printf '\n'
ok "安装完成。"
if [ "$PATH_EDITED" -eq 1 ]; then
  echo "新开一个终端窗口，或先执行：source ${RC_FILES[0]:-$HOME/.zshrc}"
fi
cat <<EOF

下一步:

  agpatch              # 看检测结果 + 补丁状态
  agpatch patch        # 一键打补丁（需要时自动 sudo）
  agpatch doctor       # 环境 / 签名诊断
  agpatch restore      # 需要时从备份还原
  agpatch menu         # 原版交互式菜单

直接用绝对路径也能跑: $BIN patch

EOF
