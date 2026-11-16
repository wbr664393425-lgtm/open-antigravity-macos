# agpatch — Open AG Patcher for macOS

**一条命令，在 macOS 上解锁 Antigravity 的区域限制**（Antigravity IDE / Antigravity 2.0 / Antigravity CLI / VS Code 扩展）。

这是 [AvenCores/open-antigravity-patcher](https://github.com/AvenCores/open-antigravity-patcher) 的 macOS 改造版：上游是俄文 TUI 菜单 + 需要 venv/pip + 只发 Windows/Linux 预编译包；本仓库把它变成一个**零依赖、可在终端直接调用**的 CLI，并修了两个 macOS 上会真出问题的 bug。

<p>
  <img alt="platform" src="https://img.shields.io/badge/platform-macOS%20(arm64%20%2F%20x86__64)-black">
  <img alt="python" src="https://img.shields.io/badge/python-3.8%2B-3776AB">
  <img alt="license" src="https://img.shields.io/badge/license-GPL--3.0-blue">
  <img alt="deps" src="https://img.shields.io/badge/dependencies-none-brightgreen">
</p>

```bash
agpatch status       # 检测装了哪些、补丁打没打
agpatch patch        # 打补丁（需要时才 sudo）
agpatch doctor       # 环境 / 签名 / 权限诊断
agpatch restore      # 一键还原
```

---

## English quick start

```bash
git clone https://github.com/wbr664393425-lgtm/open-antigravity-macos.git
cd open-antigravity-macos
bash install.sh          # installs the `agpatch` command into ~/.local/bin (no sudo, no pip)
agpatch patch            # patch every detected Antigravity target, ad-hoc re-signs the .app
agpatch doctor           # verify code signature / writability / running processes
agpatch restore          # roll back from backups
```

This is a macOS-focused fork of [AvenCores/open-antigravity-patcher](https://github.com/AvenCores/open-antigravity-patcher) (GPL-3.0). It replaces the interactive TUI with a scriptable CLI, removes the external `packaging` dependency, and fixes two macOS bugs (ad-hoc signing order, backup overwrite on re-patch). Full guide below is in Chinese; the upstream Russian README is kept in [UPSTREAM.md](./UPSTREAM.md).

---

## 目录

- [和上游的区别](#和上游的区别)
- [安装](#安装)
- [快速开始](#快速开始)
- [一键脚本（双击运行）](#一键脚本双击运行)
- [命令速查](#命令速查)
- [典型场景](#典型场景)
- [原理：补丁到底改了什么](#原理补丁到底改了什么)
- [macOS 专属说明](#macos-专属说明)
- [排错](#排错)
- [项目结构](#项目结构)
- [本地开发与测试](#本地开发与测试)
- [致谢与许可](#致谢与许可)
- [免责声明](#免责声明)

---

## 和上游的区别

| | 上游 | 本仓库 |
|---|---|---|
| 交互 | TUI 菜单，敲数字 + 一堆 y/n | `agpatch status/patch/restore/doctor` 子命令 |
| 依赖 | 需要 `venv` + `pip install packaging` | **零第三方依赖**，纯标准库 |
| sudo | 启动就问"要不要 sudo 重启" | **按需**：只有目标文件不可写才提权 |
| macOS 产物 | 需要自己 PyInstaller 打包 | `bash install.sh` 一条命令装好，免打包 |
| Bug | — | 修了 ad-hoc 签名顺序、re-patch 覆盖干净备份两个问题 |

最近一次验证环境：macOS 27.3 / Apple Silicon / Python 3.14 / Antigravity IDE 2.5.5 / Antigravity 2.0 2.32.1。

## 安装

### 一行安装（推荐）

```bash
bash install.sh
```

安装内容（全在用户目录，**不需要 sudo**）：

| 位置 | 作用 |
|---|---|
| `~/.local/bin/agpatch` | 命令入口（指向下面的启动器） |
| `~/.local/share/agpatch/source` | 复制过去的代码（约 660 KB） |
| `~/.zshrc`（仅当 `~/.local/bin` 不在 PATH 时） | 追加带 `# >>> agpatch >>>` 标记的 PATH 配置 |

安装脚本自带冒烟测试，末尾会打印 `agpatch 可用: agpatch x.y.z`。

其他参数：

```bash
bash install.sh --link         # 开发模式：符号链接当前 checkout，改代码立即生效
bash install.sh --uninstall    # 卸载（不会动 App 里的备份文件）
bash install.sh --prefix DIR   # 装到别的前缀
bash install.sh --no-path      # 不碰任何 shell 配置文件
```

### 不安装，直接跑

```bash
./agpatch patch      # 仓库根目录的启动器，逻辑完全一样
```

### 卸载

```bash
agpatch self-uninstall     # 或 bash install.sh --uninstall
```

> 卸载只删 `agpatch` 本身，**不会**还原已经打上的补丁。要还原先 `agpatch restore`。

## 快速开始

```bash
# 1) 看装了什么、当前状态
agpatch status

# 2) 想先确认会改哪里（不写任何字节）
agpatch patch --dry-run

# 3) 真正打补丁
agpatch patch

# 4) 完全退出 Antigravity / Antigravity IDE（Cmd+Q），再重新打开
```

打完会自动做三件 macOS 上必须做的事：

1. **ad-hoc 重签名** —— `.app` 里任何文件被改都会破坏代码签名，Electron + Hardened Runtime 会直接拒绝启动。补丁后自动 `codesign --force --deep --sign -` 重签成 ad-hoc。
2. **清编译缓存** —— 删掉 `~/Library/Application Support/Antigravity IDE/{CachedData,Code Cache/js}`，否则 IDE 可能重放旧编译结果。
3. **清 quarantine** —— `xattr -dr com.apple.quarantine`，避免 Gatekeeper 弹窗。

真实输出长这样：

```
  ─ PATCH — Antigravity 2.0 (language_server) ─────
  [*] Creating backup -> language_server.agybak
  [+] Backup: language_server.agybak (195.8 MB)
  [*] Re-signing language_server (ad-hoc)...
  [+] Ad-hoc signature applied
  [*] Re-signing Antigravity.app (ad-hoc)...
  [+] Ad-hoc signature applied
  ✓ Patch manager binary — hasValidAuth=true (arm64)

  ╔═══════════════════════════════════════════════╗
  ║  PATCH COMPLETE                               ║
  ╟───────────────────────────────────────────────╢
  ║  Gate:  hasValidAuth=true (arm64) @ 0x25d2cd0 ║
  ╚═══════════════════════════════════════════════╝
```

## 一键脚本（双击运行）

`一键修复.command` —— 双击就跑，适合不想开终端的人：

```bash
./一键修复.command             # 打补丁 → 校验 → 重启原来开着的 App
./一键修复.command restore     # 还原
./一键修复.command doctor      # 只诊断（不改文件、不动 App）
./一键修复.command dry         # 只演示补丁计划（--dry-run）
./一键修复.command -y          # 跳过确认（无人值守）
```

流程：先列出"会关闭哪些 App"→ 等你输入 `y` 确认 → 退出正在跑的 Antigravity/IDE → 打补丁 → `codesign` 校验 + `doctor` → 把**原本开着**的 App 重新拉起来。窗口不自动关，方便看结果。

安全约束：

- 默认**必须输入 `y`** 才动手，直接回车 = 取消，什么都不改
- `doctor` / `dry` 完全不碰运行中的 App
- 没有交互终端又没加 `-y` → 直接拒绝（退出码 2）

想更顺手就拖到桌面：

```bash
cp 一键修复.command ~/Desktop/
```

## 命令速查

```
agpatch                        # = agpatch status
agpatch status                 # 所有目标：路径 / 版本 / 补丁状态 / 大小
agpatch patch                  # 打补丁：检测到哪个打哪个
agpatch patch ide              # 只打 Antigravity IDE（.app 里的 main.js）
agpatch patch app              # 只打 Antigravity 2.0（language_server 机器码）
agpatch patch agy              # 只打 Antigravity CLI（agy 二进制）
agpatch patch vscode           # 只打 VS Code 扩展（extension.js + ~/.gemini/bin 二进制）
agpatch patch --dry-run        # 只报告会改什么，一个字节都不写
agpatch patch -y               # 不询问确认（stdin 不是终端时自动开启）
agpatch restore [目标...]       # 从备份还原
agpatch doctor                 # macOS/架构/工具链/归属/签名/quarantine/进程 全量诊断
agpatch doctor --path PATH     # 指定路径诊断（装在非标准位置）
agpatch menu                   # 原版交互式菜单（与上游一致）
agpatch check-updates          # 查 GitHub 最新 release
agpatch self-uninstall         # 卸载 agpatch
agpatch --version
```

目标别名：`ide`/`editor`、`app`/`2.0`/`manager`/`language_server`、`agy`/`cli`、`vscode`/`extension`、`all`

退出码：`0` 成功 / `1` 失败或有目标没打上 / `2` 参数错误 / `130` Ctrl+C

## 典型场景

**只解锁 IDE，不动 Antigravity 2.0**

```bash
agpatch patch ide
```

**先看状态，再决定**

```bash
agpatch status
agpatch doctor          # 看签名是否 valid、文件是否可写
```

**打完了但界面还是老样子**

```bash
# IDE：确认已完全退出（Cmd+Q），再打开
pgrep -fl "Antigravity IDE"     # 应该没有输出
agpatch status                  # 应显示 already patched
```

**要还原**

```bash
agpatch restore          # 全部
agpatch restore ide      # 只还原 IDE
```

备份就在原文件旁边：`main.js.bak`、`language_server.agybak`、`agy.agybak`。

**装到非标准位置**

```bash
agpatch doctor --path "/Volumes/External/Antigravity.app"
agpatch patch app --path "/Volumes/External/Antigravity.app"
```

## 原理：补丁到底改了什么

一句话：**这些产品在本地用"客户端判断"决定要不要拦你，补丁把这个判断改成恒真**。服务端鉴权没被改（所以 403 `SUBSCRIPTION_REQUIRED`、429 配额、HTTP 500 跟补丁无关）。

### 1. Antigravity IDE —— 改 JS 判断（文本替换）

`main.js` 里有一处：

```js
resetIsTierGCPTos(), this._productService.isGoogleInternal
```

`isGoogleInternal` 为真时，客户端认为"这是 Google 内部流量"，跳过区域/资格校验。补丁用一条正则把它换成常量：

```python
IDE_RE = r"(resetIsTierGCPTos\(\),)this\.[A-Za-z_$0-9]+\.isGoogleInternal"
# 替换为: \1true   →   resetIsTierGCPTos(),true
```

实测在某台机器上命中 **1 处**（不命中说明这版代码结构变了，补丁会拒绝修改）。改完必须清 V8 编译缓存，否则旧字节码会被重放。

### 2. Antigravity 2.0 —— 改 Go 二进制机器码

`language_server` 是 Go 编译的原生二进制（约 196 MB，arm64），不能按文本改。鉴权函数大致是：

```
ldrb  w3, [x0, #8]      ; 读结构体第 8 字节 -> hasValidAuth (bool)
tbz   w3, #0, skip      ; 为 0 就跳到失败分支
...
skip: 失败 / 需要订阅
```

补丁把"读取"换成"写入常量 1"：

```
ldrb  w3, [x0, #8]   (03 20 40 39)  ->  mov  w3, #1      (23 00 80 52)
                                        strb w3, [x0, #8] (03 20 00 39)
```

于是后面的 `tbz` 永远走"成功"分支，`hasValidAuth` 恒为 true。

定位靠**字节签名 + 唯一性校验**，不是固定偏移（每次编译偏移都会变）。只匹配到一处才动手：

```
hasValidAuth=true (arm64) @ 0x25d2cd0     # 196 MB 文件里的唯一匹配
```

`MultiGate` 同时带 x64 和 arm64 两套签名，按架构自动挑。如果新版本编译结果变了导致匹配不上、或匹配到多处（无法确定改哪个），补丁**直接报错退出，不写任何字节**。

### 3. Antigravity CLI（agy）

同一思路，目标是启动时的 "Eligibility Check" 门控。不同版本寄存器不同，所以有多个子签名：`mov w1,#1` / `mov w4,#1` / `mov w2,#1`，命中哪个改哪个（1.2.7 需要同时改 w2 和 w4 两处，否则 "Eligibility check failed" 屏幕仍会出现）。

### 4. VS Code 扩展

两件事：改 `extension.js`（已有二进制时直接复用、跳过版本检查下载），以及对下载到 `~/.gemini/bin` 的 agy 二进制做上面同样的机器码补丁。

### 5. 为什么必须重新签名

`.app` 里每个文件的哈希都封在 `_CodeSignature/CodeResources` 里。改了 `main.js` 或 `language_server`，封条立刻失效；Electron 带 Hardened Runtime 时签名不符，**内核直接 SIGKILL**（连 Gatekeeper 弹窗都来不及）。

所以每次 patch 后自动 ad-hoc 重签：

```bash
codesign --force --sign - <二进制>            # 先签内层
codesign --force --deep --sign - <xx.app>     # 再签外层 bundle（封条按最终字节重算）
```

**顺序不能反** —— 反了会得到 `a sealed resource is missing or invalid`（上游就有这个问题，本仓库已修）。

ad-hoc 签名（`-`）表示"本机自签"，不需要 Apple 开发者证书。副作用：

- 签名身份变了 → **TCC 权限（屏幕录制、麦克风、辅助功能）可能需要重新授权一次**
- 首次启动可能被 Gatekeeper 拦一次，去「系统设置 → 隐私与安全性」点「仍要打开」

### 6. 为什么可逆、为什么安全

- 改之前把原始字节复制成 `main.js.bak` / `language_server.agybak`，还原就是原子替换回去再重签
- 不联网、不代理流量、不改账号、不上报数据；只改本地文件的若干字节
- 不碰 `/System`，不需要关 SIP

## macOS 专属说明

### sudo 什么时候才需要

按需判断，不再一启动就催：

- DMG 装的 `/Applications/Antigravity*.app` 归你所有 → **不需要 sudo**
- `.app` 属于 `root` / 别的用户 → `agpatch` 自动 `sudo` 重跑自己，只弹一次密码

判断依据就是 `agpatch status` / `doctor` 里的 `writable:` 一行。

### Gatekeeper / SIP

- 只改用户自己的 `.app` 内容，不碰 `/System`，不需要关 SIP
- 仍被拦：`系统设置 → 隐私与安全性` 底部点「仍要打开」，或
  `xattr -dr com.apple.quarantine "/Applications/Antigravity.app"`

### `Operation not permitted` / Errno 1

`.app` 里可能带 `uchg` 不可变标志，root 也写不进去。补丁流程会先跑 `chflags -R nouchg,noschg`。仍失败：

```bash
ls -lO "/Applications/Antigravity.app/Contents/Resources/bin/language_server"   # 看 flags 列
sudo chflags -R nouchg,noschg "/Applications/Antigravity.app"
```

### 应用正在运行时能打吗

能。POSIX 写二进制走 `os.replace` 原子替换，运行中的进程继续用旧 inode，下次启动生效。但 **IDE 的 main.js 必须重启才生效**。`agpatch doctor` 会列出正在跑的相关进程。

### Apple Silicon vs Intel

- `language_server` / `agy` 是机器码补丁，arm64 与 x86-64 各有一套字节签名，`MultiGate` 自动挑
- 如果新版本导致签名匹配不上，补丁会**拒绝修改**并提示不支持该版本，不会写坏文件

## 排错

先跑这个，绝大多数问题它会自己说：

```bash
agpatch doctor
```

| 输出 | 含义 / 处理 |
|---|---|
| `tool /usr/bin/codesign` 缺失 | `xcode-select --install` |
| `writable: NO (sudo needed)` | 让 `agpatch` 自己提权，别手动 `sudo python3` |
| `patch: patched` 但 `verification: signature BROKEN` | `agpatch restore && agpatch patch` |
| `quarantine: present` | `xattr -dr com.apple.quarantine <app>` |
| 目标找不到 | `agpatch doctor --path '/Applications/Antigravity.app'` |
| `gate signature not found (unsupported version?)` | 版本太新/太旧，签名没覆盖；先 `agpatch check-updates` 看是否有新版 |
| `Running as root, but the target is still not writable` | 权限已提但被更高层挡住：`ls -lO` 看 `uchg/schg`、`mount` 看是否只读卷、`系统设置 → 隐私与安全性 → 应用管理` 放行你用的终端（**root 也不能绕过 TCC**） |
| `Backup error: [Errno 1] Operation not permitted` | 同上；也可能是终端本身是被别 App 沙盒化拉起的，换成 `Terminal.app` 直接跑 |

其他常见错误（HTTP 500 / 403 `SUBSCRIPTION_REQUIRED` / 429 配额）**与本地补丁无关**，详见 [UPSTREAM.md](./UPSTREAM.md) 对应章节。

## 项目结构

```
open-antigravity-macos/
├── agpatch                  # POSIX sh 启动器（仓库内直接可跑）
├── install.sh               # 安装器：复制 / --link / --uninstall / PATH
├── 一键修复.command          # 双击运行的一键脚本
├── source/
│   ├── agpatch.py           # CLI 入口
│   ├── main.py              # 原版 TUI 入口（保持兼容）
│   └── patcher/
│       ├── commands.py      # ★ 子命令实现：status/patch/restore/doctor/menu
│       ├── cli.py           # 原版 TUI 逻辑（保留）
│       ├── ide/             # Antigravity IDE（main.js 正则补丁）
│       ├── manager/         # Antigravity 2.0（language_server 机器码补丁）
│       ├── agy/             # Antigravity CLI（agy 机器码补丁）
│       ├── vscode/          # VS Code 扩展
│       └── utils/           # console / file / atomic / version / session / captcha
├── test-agy/                # 上游的 CLI 发布版兼容性测试
├── UPSTREAM.md              # 上游俄文 README（原样保留）
└── LICENSE                  # GPL-3.0
```

## 本地开发与测试

```bash
# 改完直接跑（免安装）
./agpatch status
./agpatch patch --dry-run

# 开发模式安装：改代码立即生效
bash install.sh --link

# 语法/导入检查
python3 -m compileall -q source

# 版本比较逻辑自测
python3 -c "
import sys; sys.path.insert(0,'source')
from patcher.utils.version import Version
assert Version('1.2.7-beta') < Version('1.2.7')
assert Version('1.2') == Version('1.2.0')
print('version logic OK')"
```

**安全测试补丁逻辑**（不碰真实安装）：把目标文件复制到临时目录，用 `--path` 指向副本跑一遍 patch → 校验 → restore，对比哈希应回到原始值。

## 贡献

欢迎 issue / PR。改补丁逻辑时请遵守：

1. **宁可不改，不可乱改** —— 签名不唯一匹配时必须 `LookupError` 退出，绝不猜偏移
2. 动签名相关代码后，至少在 `agpatch doctor` 里确认 `verification: signature valid`
3. 新增目标类型请沿用 `Gate` / `MultiGate` 结构，并在 `commands.py` 的 `WRITE_FILES` 里登记

## 致谢与许可

- 原始项目：[AvenCores/open-antigravity-patcher](https://github.com/AvenCores/open-antigravity-patcher)（作者 **AvenCores**），本仓库是其 macOS 改造版 fork，上游 README 见 [UPSTREAM.md](./UPSTREAM.md)
- 上游的字节签名研究来自 [QNIX-Dev/eligibility-antigravity-patcher](https://github.com/QNIX-Dev/eligibility-antigravity-patcher)（MIT）
- 协议：**GPL-3.0**（见 [LICENSE](./LICENSE)）。本 fork 的所有修改同样以 GPL-3.0 发布。

## 免责声明

- 仅修改本地文件，不代理流量、不伪造账号、不上报数据
- 这类修改通常违反 Google 的服务条款，可能导致账号受限；风险自负
- 与本项目作者无关的第三方预编译产物请自行甄别
