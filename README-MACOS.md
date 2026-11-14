# agpatch — Open AG Patcher for macOS

把上游 [AvenCores/open-antigravity-patcher](https://github.com/AvenCores/open-antigravity-patcher)（Python TUI 菜单）改造成**macOS 终端里一条命令就能用**的 CLI。

上游只发布 Windows / Linux 预编译包，macOS 要自己建 venv、装 `packaging`、进菜单敲数字、再回答一堆 y/n。改造后：

```bash
agpatch            # 看检测结果和补丁状态
agpatch patch      # 一键打补丁（需要时才 sudo）
agpatch doctor     # 环境 / 签名诊断
```

无第三方依赖（只用 Python 标准库），不需要 venv、不需要 pip、不需要 PyInstaller。

---

## 1. 安装

```bash
cd open-ag-patcher-macos
bash install.sh
```

安装内容（全部在用户目录，不需要 sudo）：

| 位置 | 作用 |
| --- | --- |
| `~/.local/bin/agpatch` | 命令入口（符号链接） |
| `~/.local/share/agpatch/source` | 复制过去的代码 |
| `~/.zshrc`（仅当 `~/.local/bin` 不在 PATH 时） | 追加一段带 `# >>> agpatch >>>` 标记的 PATH 配置 |

常用参数：

```bash
bash install.sh --link         # 开发模式：链接当前 checkout，改代码立即生效
bash install.sh --uninstall    # 卸载（不会动 Antigravity 里的备份文件）
bash install.sh --prefix DIR   # 装到别的前缀
bash install.sh --no-path      # 不碰任何 shell 配置文件
```

> 你的机器上 `~/.local/bin` 已在 PATH 里（由 `~/.local/bin/env` 提供），所以安装时不会改任何 rc 文件。

## 2. 命令速查

```
agpatch                        # = agpatch status
agpatch status                 # 列出所有目标：路径 / 版本 / 补丁状态 / 大小
agpatch patch                  # 打补丁：自动检测到哪个打哪个
agpatch patch ide              # 只打 Antigravity IDE（.app 里的 main.js）
agpatch patch app              # 只打 Antigravity 2.0（language_server，机器码）
agpatch patch agy              # 只打 Antigravity CLI（agy 二进制）
agpatch patch vscode           # 只打 VS Code 扩展（extension.js + ~/.gemini/bin 里的二进制）
agpatch patch all              # = agpatch patch
agpatch patch --dry-run        # 只报告会改什么，一个字节都不写
agpatch patch -y               # 不询问确认（stdin 不是终端时自动开启）
agpatch restore [目标...]      # 从备份还原
agpatch doctor                 # macOS 版本 / 架构 / 工具链 / 目标归属 / 签名 / 隔离属性 / 进程
agpatch doctor --path PATH     # 指定路径做诊断（装在非标准位置时用）
agpatch menu                   # 原版交互式菜单（行为与上游一致）
agpatch check-updates          # 查 GitHub 最新 release
agpatch self-uninstall         # 卸载 agpatch
agpatch --version
```

目标别名：`ide` `editor` / `app` `2.0` `manager` `language_server` / `agy` `cli` / `vscode` `extension` / `all`

## 3. 典型流程

```bash
# 1) 看装了什么、当前状态
agpatch status

# 2) 想先确认会改哪里
agpatch patch --dry-run

# 3) 真正打补丁
agpatch patch

# 4) 完全退出 Antigravity / Antigravity IDE，再重新打开
```

打完会自动做三件事，这是 macOS 上必须的：

1. **ad-hoc 重签名**：`.app` 里任何文件被改都会破坏代码签名，Electron + Hardened Runtime 会直接拒绝启动。补丁后自动执行 `codesign --force --deep --sign -` 重新签成 ad-hoc。
2. **清编译缓存**：删掉 `~/Library/Application Support/Antigravity IDE` 下的 `CachedData` / `Code Cache/js`，否则 IDE 可能重放旧编译结果。
3. **清 quarantine**：`xattr -dr com.apple.quarantine`，避免 Gatekeeper 弹窗。

还原：

```bash
agpatch restore          # 全部
agpatch restore ide      # 只还原 IDE
```

备份文件位置：`main.js.bak`（IDE）、`language_server.agybak` / `agy.agybak`（二进制）——就在原文件旁边。

## 4. macOS 专属说明

### sudo 什么时候才需要

上游脚本一启动就问"要不要 sudo 重启"，很烦。现在改成**按需判断**：

- 你是通过 DMG 装的，`/Applications/Antigravity*.app` 归你所有 → **完全不需要 sudo**（你这台机器就是这种情况）。
- 如果 `.app` 属于 `root` / 别的用户 → `agpatch` 会自动 `sudo` 重跑自己，只弹一次密码。

`agpatch status` / `doctor` 里的 `writable: NO (sudo needed)` 就是判断依据。

### Gatekeeper / SIP

- 打补丁只改用户自己的 `.app` 内容，不碰 `/System`，不需要关 SIP。
- 如果 macOS 仍然拦截启动：`系统设置 → 隐私与安全性` 底部点「仍要打开」，或手动
  `xattr -dr com.apple.quarantine "/Applications/Antigravity.app"`。

### "Operation not permitted" / Errno 1

`.app` 里可能带 `uchg` 不可变标志，连 root 也写不进去。补丁流程会先跑
`chflags -R nouchg,noschg` 再写。若仍失败：

```bash
ls -lO "/Applications/Antigravity.app/Contents/Resources/bin/language_server"   # 看 flags 列
sudo chflags -R nouchg,noschg "/Applications/Antigravity.app"
```

### 应用正在运行时能打吗

能。POSIX 写二进制走 `os.replace` 原子替换，运行中的进程继续用旧 inode，下次启动生效。
但 **IDE 的 main.js 必须重启才生效**，CLI 也一样。`doctor` 会列出正在跑的相关进程。

### Apple Silicon vs Intel

- `language_server` / `agy` 是机器码补丁，arm64 和 x86-64 各有一套字节签名，`MultiGate` 自动挑。
- 你这台是 arm64 + `Antigravity.app 2.32.1`，实测匹配到 `hasValidAuth=true (arm64) @ 0x25d2cd0`。
- 如果新版本改了编译结果导致签名匹配不上，补丁会**拒绝修改**并提示不支持该版本——不会写坏文件。

## 5. 排错

先跑这个，绝大多数问题它自己会说：

```bash
agpatch doctor
```

输出里逐项看：

- `tool /usr/bin/codesign` 缺 → `xcode-select --install`
- `writable: NO (sudo needed)` → 让 `agpatch` 自己提权，别手动 `sudo python3`
- `patch: patched` 但 `verification: signature BROKEN` → 执行 `agpatch restore && agpatch patch`
- `quarantine: present` → `xattr -dr com.apple.quarantine <app>`
- 目标找不到 → `agpatch doctor --path '/Applications/Antigravity.app'`

其他常见错误（HTTP 500 / 403 SUBSCRIPTION_REQUIRED / 429 配额）跟本地补丁无关，见上游 README 的对应章节。

## 6. 相对上游改了什么

代码级改动（全部保持向后兼容，`python3 main.py` 原入口仍可用）：

| 文件 | 改动 |
| --- | --- |
| `source/patcher/commands.py` | **新增**：`agpatch` 子命令 CLI（status / patch / restore / doctor / menu / self-uninstall / check-updates），含按需 sudo 重跑、dry-run、目标别名、汇总表 |
| `source/agpatch.py` | **新增**：CLI 入口 |
| `source/patcher/utils/version.py` | **新增**：纯标准库版本比较，替换外部依赖 `packaging` |
| `source/patcher/utils/session.py` | **新增**：全局会话开关（自动确认、不清屏） |
| `install.sh` / `agpatch` | **新增**：安装器与 POSIX sh 启动器 |
| `source/main.py` | 去掉 POSIX 启动时的强制 sudo 询问，改为提示；保留原 TUI |
| `source/patcher/cli.py` | `confirmed()` 支持自动确认；`pause()` 非交互时跳过；`offer_download_and_block()` 非交互时不阻塞 |
| `source/patcher/utils/console.py` | 非交互模式不清屏（输出留在日志里） |
| `source/patcher/utils/captcha.py` | `-y` 时跳过算术验证码 |
| `source/patcher/ide/discovery.py`、`manager/patcher.py` | `packaging.version` → 内置 `patcher.utils.version` |

上游功能一个没删：IDE / Antigravity 2.0 / agy / VS Code 扩展的 patch 与 restore、备份、版本校验、重签名逻辑都保持原样。

## 7. 免责声明

- 本项目是上游的 macOS 可用性改造，逻辑与补丁字节均来自上游，遵循 **GPL-3.0**，版权归原作者 AvenCores 及 `eligibility-antigravity-patcher` 作者。
- 仅修改本地文件，不代理流量、不伪造账号、不上报数据。
- 使用风险自负；作者与改造者不对账号状态、服务条款后果负责。
