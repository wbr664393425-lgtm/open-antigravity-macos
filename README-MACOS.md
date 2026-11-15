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

### 一键脚本（Finder 双击）

```bash
./一键修复.command            # 打补丁 → 校验签名 → 重启原来开着的 App
./一键修复.command restore    # 还原
./一键修复.command doctor     # 只诊断（不改文件、不动 App）
./一键修复.command dry         # 只演示补丁计划（--dry-run）
./一键修复.command -y          # 跳过确认（无人值守）
```

流程：先列出"会关闭哪些 App"，等你输入 `y` 确认 → 退出正在跑的 Antigravity / IDE → 打补丁 → `codesign` 校验 + `doctor` → 把**原本开着**的 App 重新拉起来。窗口不会自动关，方便看结果。

安全约束（防止误双击把你正在用的 App 关掉）：

- 默认**必须输入 `y`** 才动手，直接回车 = 取消，什么都不改
- `doctor` / `dry` 两种模式完全不碰运行中的 App
- 没有交互终端（管道、脚本里调用）又没加 `-y` 时，直接拒绝并退出码 2

想真正"一键"，把它拖到桌面或程序坞：

```bash
cp 一键修复.command ~/Desktop/
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

## 4. 原理：补丁到底改了什么

一句话：**这些产品在本地用"客户端判断"决定要不要拦你，补丁把这个判断改成恒真**。服务端鉴权没被改（所以 403 `SUBSCRIPTION_REQUIRED`、429 配额、HTTP 500 这些跟补丁无关）。

### 4.1 Antigravity IDE —— 改 JS 判断（文本替换）

`main.js` 里有一处：

```js
resetIsTierGCPTos(), this._productService.isGoogleInternal
```

`isGoogleInternal` 为真时，客户端认为"这是 Google 内部流量"，跳过区域/资格校验。补丁用一条正则把它换成常量：

```python
IDE_RE  = r"(resetIsTierGCPTos\(\),)this\.[A-Za-z_$0-9]+\.isGoogleInternal"
IDE_RE  ->  r"\1true"        # 结果：resetIsTierGCPTos(),true
```

你机器上命中 **1 处**（如果不命中，说明这版代码结构变了，补丁会拒绝修改并提示不支持）。

改完还要删 `~/Library/Application Support/Antigravity IDE/{CachedData,Code Cache/js}` —— V8 有编译缓存，不清的话旧的字节码还会被重放，改了等于没改。

### 4.2 Antigravity 2.0 —— 改 Go 二进制机器码（字节补丁）

`language_server` 是 Go 编译的原生二进制（你这台 196 MB，arm64），不能按文本改。它的鉴权函数大概长这样：

```
ldrb  w3, [x0, #8]      ; 读结构体第 8 字节 -> hasValidAuth (bool)
tbz   w3, #0, skip      ; 为 0 就跳到失败分支
... 正常流程 ...
skip: 失败/需要订阅
```

补丁把"读取"换成"写入常量 1"：

```
ldrb  w3, [x0, #8]   (03 20 40 39)   ->   mov  w3, #1   (23 00 80 52)
                                           strb w3, [x0, #8]  (03 20 00 39)
```

于是后面那个 `tbz` 永远走"成功"分支，`hasValidAuth` 恒为 true。

定位方式不是固定偏移（每次编译偏移都会变），而是**字节签名 + 唯一性校验**：签名在你机器上只匹配到一处，才会动手：

```
hasValidAuth=true (arm64) @ 0x25d2cd0      # 200 MB 文件里的唯一匹配
```

`MultiGate` 同时带 x64 和 arm64 两套签名，按架构自动挑；如果某个新版本编译结果变了导致签名匹配不上，或者匹配到多处（无法确定改哪个），补丁会**直接报错退出，不写任何字节**。

### 4.3 Antigravity CLI（agy）

同一个思路，目标是启动时的 "Eligibility Check" 门控。不同版本的寄存器不同，所以有多个子签名：`mov w1,#1` / `mov w4,#1` / `mov w2,#1`，命中哪个改哪个（1.2.7 需要同时改 w2 和 w4 两处，否则"Eligibility check failed"屏幕仍会出现）。

### 4.4 VS Code 扩展

两件事：改 `extension.js`（让它在已有二进制时直接复用、跳过版本检查下载），以及对 `~/.gemini/bin` 里下载下来的 agy 二进制做 4.3 同样的机器码补丁。

### 4.5 为什么必须重新签名

`.app` 里每个文件的哈希都封在 `_CodeSignature/CodeResources` 里。改了 `main.js` 或 `language_server`，封条立刻失效；Electron 带 Hardened Runtime，签名不符时**内核直接 SIGKILL**（连 Gatekeeper 弹窗都来不及）。

所以每次 patch 后自动做 ad-hoc 重签：

```bash
codesign --force --sign - <二进制>        # 先签内层
codesign --force --deep --sign - <xx.app>  # 再签外层 bundle（封条按最终字节重算）
```

顺序不能反 —— 反了就会得到 `a sealed resource is missing or invalid`（这是我这一版修掉的 bug，详见第 7 节）。

ad-hoc 签名（`-`）表示"本机自签"，不需要 Apple 开发者证书，足够本地运行。副作用：

- 签名身份变了 → **TCC 权限（屏幕录制、麦克风、辅助功能）可能需要重新授权一次**
- 首次启动可能被 Gatekeeper 拦一次，去「系统设置 → 隐私与安全性」点「仍要打开」

### 4.6 为什么可逆、为什么安全

- 改之前把原始字节复制成 `main.js.bak` / `language_server.agybak`，还原就是把这些字节原子替换回去再重签（`agpatch restore`）
- 不联网、不代理流量、不改账号、不上报数据；只改本地文件的若干个字节
- 不碰 `/System`，不需要关 SIP

## 5. macOS 专属说明

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

## 6. 排错

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

## 7. 相对上游改了什么

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
| `source/patcher/utils/file.py` | **修 bug**：新增 `resign_macos_targets()`，先签内层二进制、再签 `.app`。上游顺序相反（先 `--deep` 签 bundle 再签 `language_server`），会让封条失效，`codesign --verify` 报 `a sealed resource is missing or invalid` / `file modified: .../language_server` |
| `source/patcher/manager/patcher.py`、`agy/patcher.py` | **修 bug**：`_make_backup()` 在“实时文件已打补丁、备份仍是原始文件”时不再覆盖备份（上游 re-patch 会把干净备份替换成已打补丁的字节，毁掉还原点） |

上游功能一个没删：IDE / Antigravity 2.0 / agy / VS Code 扩展的 patch 与 restore、备份、版本校验、重签名逻辑都保持原样。

## 8. 免责声明

- 本项目是上游的 macOS 可用性改造，逻辑与补丁字节均来自上游，遵循 **GPL-3.0**，版权归原作者 AvenCores 及 `eligibility-antigravity-patcher` 作者。
- 仅修改本地文件，不代理流量、不伪造账号、不上报数据。
- 使用风险自负；作者与改造者不对账号状态、服务条款后果负责。
