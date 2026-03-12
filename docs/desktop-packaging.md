# Bao Desktop — 打包指南

## 概述

Bao Desktop 是项目的主入口交付形态。大多数用户会直接从 GitHub Release 下载桌面安装包；CLI 的 PyPI 分发只面向终端用户，源码路径面向开发者。本页说明桌面端如何稳定产出这条主分发链路。

当前默认发布使用 **PyInstaller onedir** 打包 Python + PySide6 应用，通过 GitHub Actions 自动构建双平台安装包。**Nuitka** 保留为备用方案，用于需要更激进二进制优化时再启用。

### 分发策略（Strategy B — 分架构）

| 平台 | 架构 | 产物 | 安装方式 |
|------|------|------|---------|
| macOS | Apple Silicon (arm64) | `Bao-x.y.z-macos-arm64.dmg` | 拖拽到 Applications |
| macOS | Intel (x86_64) | `Bao-x.y.z-macos-x86_64.dmg` | 拖拽到 Applications |
| macOS | Apple Silicon / Intel | `Bao-x.y.z-macos-<arch>-update.zip` | 桌面端应用内更新 |
| Windows | x64 | `Bao-x.y.z-windows-x64-setup.exe` | Inno Setup 安装向导 |

### 体积目标

| 平台 | 目标 | 说明 |
|------|------|------|
| macOS (单架构) | < 150 MB | 单架构比 universal2 小约 40% |
| Windows x64 | < 150 MB | 可选 UPX 压缩进一步缩小 |

## 技术选型

| 决策 | 选择 | 理由 |
|------|------|------|
| 打包工具 | PyInstaller onedir | 不做 C 编译，构建更快，更适合当前 release 稳定性与 CI 时长目标 |
| 备用方案 | Nuitka | Python→C 编译，适合后续做更激进的体积/启动优化，但目前不作为主链 |
| Qt 依赖 | PySide6-Essentials | 只含核心 22 个 Qt 模块，不含 WebEngine/3D/Multimedia（省 160-320 MB） |
| macOS 安装包 | create-dmg | 生成带拖拽安装 UI 的 .dmg |
| Windows 安装包 | Inno Setup | 成熟的 Windows 安装向导，支持自定义 UI |
| CI/CD | GitHub Actions | 矩阵构建 macOS arm64 + x86_64 + Windows x64 |

## 轻量化策略

### 1. 只装 PySide6-Essentials（最大收益）

`pyproject.toml` 中 desktop 依赖使用 `PySide6-Essentials` 而非 `PySide6`：

```toml
[project.optional-dependencies]
desktop = ["PySide6-Essentials>=6.7.0,<7.0.0"]
```

PySide6 = Essentials + Addons。Addons 含 WebEngine（50-120MB）、3D、Multimedia 等不需要的模块。

### 2. PyInstaller 主链资源收口

PyInstaller 主链统一从 `dist-pyinstaller/` 输出，再由共用封装脚本优先探测 `dist-pyinstaller/dist/Bao.app` / `dist-pyinstaller\dist\Bao`；只有显式切到备用链，或主链产物不存在时，才 fallback 到 Nuitka 产物。

### 3. stdlib 排除

显式排除运行时不需要的标准库：tkinter、unittest、doctest、idlelib、lib2to3、ensurepip、distutils、turtledemo、test。

### 4. macOS 分架构构建

PySide6 macOS wheel 为 universal2（含双架构）。当前主链在 arm64 和 x86_64 runner 上分别构建 PyInstaller `.app`，每个 `.dmg` 只封装对应架构产物；备用 Nuitka 链同样保持分架构。

## 图标流程

平台图标仍以 `assets/logo.jpg` 为源图生成。打包前先生成平台图标：

```bash
uv run --with pillow python app/scripts/generate_app_icons.py
```

产物：`assets/logo.icns`（macOS）、`app/resources/logo.ico`（Windows）。

Windows 安装器品牌图资源也可由脚本生成：

```bash
uv run --with pillow python app/scripts/generate_installer_assets.py
```

产物位于 `app/resources/installer/`，包含 Inno Setup 欢迎图、小图与背景图的 light/dark 两套 PNG；同一次生成也会更新 `app/resources/dmg-background.png`。脚本现在是 Win/mac 安装品牌资源的唯一事实源，统一复用桌面端暖色系 token、圆角和层次节奏，避免 Windows 安装器、macOS DMG 与桌面端首屏各自漂移。`app/scripts/package_win_installer.bat` 和 `app/scripts/create_dmg.sh` 都会在打包前自动重生成这批资源。

运行时窗口图标由 `app/main.py` 按平台解析：Windows 先解析已随桌面端打包的 `app/resources/logo.ico`，只有该资源缺失时才退回 `app/resources/logo-circle.png` 与 `assets/logo.ico|jpg|jpeg|png` 的兼容路径；macOS 与其他平台继续优先使用 `assets/logo.jpg|jpeg|png`。`logo-circle.png` 只保留给应用内 UI，Windows 的窗口/安装器/EXE 图标主路径统一收口到同一个 `.ico` 事实源。

## 本地构建

### 前置条件

```bash
# macOS
xcode-select --install                    # Xcode Command Line Tools
brew install create-dmg                   # DMG 创建工具
uv sync --extra desktop-build-pyinstaller # 默认桌面构建依赖

# Windows — 需要 Visual Studio Build Tools (MSVC)
uv sync --extra desktop-build-pyinstaller
# Inno Setup: https://jrsoftware.org/isinfo.php
```

### macOS

```bash
# 默认 PyInstaller 构建
uv sync --extra desktop-build-pyinstaller
bash app/scripts/build_mac_pyinstaller.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64 --app-path "dist-pyinstaller/dist/Bao.app"
bash app/scripts/create_update_zip.sh --arch arm64 --app-path "dist-pyinstaller/dist/Bao.app"
QT_QPA_PLATFORM=offscreen "dist-pyinstaller/dist/Bao.app/Contents/MacOS/Bao" --smoke

# 备用 Nuitka 构建
bash app/scripts/build_mac.sh --arch arm64
bash app/scripts/create_dmg.sh --arch arm64 --app-path "dist/Bao.app"
bash app/scripts/create_update_zip.sh --arch arm64 --app-path "dist/Bao.app"
```

默认产物：`dist-pyinstaller/dist/Bao.app`、`dist/Bao-x.y.z-macos-arm64.dmg`、`dist/Bao-x.y.z-macos-arm64-update.zip`

备用 Nuitka 产物仍保持 `dist/Bao.app` 主体路径，供需要时手动切换。

两条 macOS 构建链路都会在最终 `Info.plist` 中回写同一组权限元数据：

- `CFBundleIdentifier = io.github.suge8.bao`
- `NSAppleEventsUsageDescription = Bao needs Automation permission to send messages and media through Messages.app.`

这是让打包后的 `Bao.app` 能稳定触发 `Messages` 自动化授权弹窗的单一路径；不要只修某一条构建链路，否则 PyInstaller 与 Nuitka 产物的 TCC 行为会漂移。

另外，构建脚本会在回写 `Info.plist` 后立刻重新执行一次 `codesign`。原因很直接：如果先签名、后改 plist，`tccd` 会因为签名信息失效而无法为 Apple Events 计算 designated requirement，最终表现就是 `-1743` 且不弹 Automation 授权窗。

### iMessage 运行前权限

如果你在桌面端启用了 iMessage，安装后的 macOS 还需要手动授予两条独立权限：

- `System Settings > Privacy & Security > Automation`：允许 `Bao` 控制 `Messages`
- `System Settings > Privacy & Security > Full Disk Access`：允许 `Bao.app` 访问 `~/Library/Messages/chat.db` 与 `~/Library/Messages/Attachments`

症状对应关系：

- `osascript` 返回 `-1743`：Automation 没开，或之前被拒绝后仍处于拒绝状态
- 日志出现 `db unreadable: ROWID=0`：通常是 `Full Disk Access` 没开，无法读取 Messages 数据库

补充：固定 `CFBundleIdentifier` 与 `NSAppleEventsUsageDescription` 解决的是“最终产物能被 macOS 正确识别并进入授权流程”，不是“所有本地重建都自动复用旧授权”。如果你用 ad-hoc 重新签名、替换了旧 `.app`，或者在不同路径反复构建，TCC 仍可能要求重新授权。

### Windows

```cmd
REM 默认 PyInstaller 构建
uv sync --extra desktop-build-pyinstaller
app\scripts\build_win_pyinstaller.bat
app\scripts\package_win_installer.bat

REM 备用 Nuitka 构建
app\scripts\build_win.bat
app\scripts\package_win_installer.bat --build-root dist\build-win-x64\main.dist
```

Windows 默认发布版使用 PyInstaller 的 GUI 模式，安装器 UI 仍由 `app/scripts/bao_installer.iss` 驱动，当前使用 Inno Setup 的 `modern windows11 dynamic` 样式，并接入 `app/resources/installer/` 下的品牌化图像资源。欢迎页与背景图已经收口到与桌面端一致的暖色品牌系统，安装器文案也收短为“安装完成后在应用内继续引导”这一条主路径，减少图像与正文同时堆信息造成的拥挤感。安装器文案支持英文与简体中文，默认按 Windows UI 语言自动匹配（`ShowLanguageDialog=auto` + `LanguageDetectionMethod=uilanguage` + `UsePreviousLanguage=no`），只有未匹配到语言时才显示语言选择对话框，且不会被上一次安装时手动选择的语言覆盖。简体中文 `.isl` 现随仓库一起分发，不再依赖 runner 上的 Inno Setup 安装是否自带该翻译文件。

默认产物：`dist-pyinstaller\dist\Bao\Bao.exe`、`dist\Bao-x.y.z-windows-x64-setup.exe`

## CI/CD 自动构建

正式发版前先完成 `docs/release-checklist.md` 中的通用步骤；本页只保留 Desktop 专项打包说明。

`Desktop Release` 的 macOS job 现在默认仍能完成基础打包；只有在仓库里检测到完整 signing/notary secrets 时，才会额外进入正式分发链：

- 从 GitHub Secrets 导入 Developer ID Application `.p12`
- 在临时 keychain 中给 `codesign` / `xcrun` 开私钥访问
- 对 `Bao.app` 做 `--options runtime --timestamp` 签名
- 先 notarize + staple `.app`，再产出 `update.zip`
- 再 notarize + staple `.dmg`

如需启用签名/公证，需要预先配置这些 GitHub Secrets：

- `BAO_MAC_CODESIGN_IDENTITY`
- `BAO_MAC_CERT_P12_BASE64`
- `BAO_MAC_CERT_P12_PASSWORD`
- `BAO_MAC_NOTARY_APPLE_ID`
- `BAO_MAC_NOTARY_TEAM_ID`
- `BAO_MAC_NOTARY_PASSWORD`（Apple ID 的 app-specific password）

推送版本 tag 触发：

```bash
git tag v0.1.4
git push origin v0.1.4
```

`.github/workflows/desktop-release.yml` 会在 macOS 14 (arm64)、macOS 15 Intel (x86_64)、GitHub-hosted Windows runner 上分别构建，并在成功后直接创建正式 Release 附带所有安装包；其中 macOS 额外产出 `*-update.zip` 供桌面端应用内更新使用。也支持手动触发 `workflow_dispatch`，并要求显式传入现有 tag（如 `v0.3.11`）用于“同版本重建”。手动重建时，workflow 会把**目标 release tag** 与**当前所选分支源码**分离：release 仍指向你填写的旧 tag，但构建使用的是你手动触发时选择的分支快照，因此修复过的 workflow / 打包脚本可以直接用于重建，不需要重新推 tag；前提是该分支里的版本号仍与目标 tag 一致。为避免单一矩阵失败直接中断其他构建，release workflow 显式设置了 `strategy.fail-fast: false`，并加入了 uv 缓存与 artifact 保留期配置；macOS 侧默认用 PyInstaller 构建 `.app`，共用封装脚本默认优先选 PyInstaller 产物，仅在主链产物不存在时回退到备用 Nuitka 路径；Windows 侧继续保留独立 preflight job，会在长时间构建开始前先解析 Inno Setup 编译器并验证 `Default.isl` 是否可用，而安装器脚本默认也优先选择 `dist-pyinstaller\dist\Bao`，只在显式传参或主链缺失时使用 Nuitka 输出；简体中文语言文件直接使用仓库内自带资源，避免不同 runner 的 Inno Setup 安装内容差异把失败拖到整轮构建末尾才暴露；同时对 `.dmg` / `.zip` / `.exe` 这类已压缩产物关闭 artifact 二次压缩，减少 CPU 与上传时间。

`.github/workflows/desktop-update-feed.yml` 会在 Release `published` 后运行：下载 update 资产、计算 SHA-256、生成 `desktop-update.json`，再部署到 GitHub Pages。由于桌面 release 现在默认直接发布正式 Release，tag 推送成功后会自动推进到 feed 更新，无需再手动点击 Publish Release。

### GitHub-native 桌面更新

桌面端更新使用 GitHub 基建闭环：

- `GitHub Releases`：托管更新资产
- `GitHub Pages`：托管稳定地址的 `desktop-update.json`
- `desktop-release.yml`：构建并上传 `.dmg` / `update.zip` / `setup.exe`
- `desktop-update-feed.yml`：在 Release 发布后生成 feed 并部署到 Pages

桌面端运行时交互也已收口为单一路径：

- 自动检查：启动后按 `ui.update.autoCheck` 静默执行，不打断 UI
- 手动检查：仅在 Settings 的「桌面更新」区域触发
- 无更新：显示 toast，不展开额外状态区
- 有更新：弹出确认模态，确认后才进入安装路径
- feed 返回 `404`：按“暂无更新”处理，不视为错误

当前 feed 是单一 JSON，按 channel + platform 选中更新资产：

```json
{
  "app": "bao-desktop",
  "channels": {
    "stable": {
      "version": "0.3.8",
      "releaseUrl": "https://github.com/Suge8/Bao/releases/tag/v0.3.8",
      "notesMarkdown": "- shipped",
      "platforms": {
        "macos-arm64": {
          "url": "https://github.com/Suge8/Bao/releases/download/v0.3.8/Bao-0.3.8-macos-arm64-update.zip",
          "kind": "app-zip",
          "size": 123,
          "sha256": "..."
        },
        "windows-x64": {
          "url": "https://github.com/Suge8/Bao/releases/download/v0.3.8/Bao-0.3.8-windows-x64-setup.exe",
          "kind": "installer-exe",
          "size": 456,
          "sha256": "...",
          "silentArgs": ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
        }
      }
    }
  }
}
```

另外提供 `.github/workflows/desktop-ci-lite.yml` 作为轻量流水线：在 PR/非 tag push 上只做单 mac runner（arm64）+ Windows smoke；其中 Windows 已前移为真实 `PyInstaller -> Inno Setup` 打包链验证，但不上传正式 release 资产，把双 mac 架构成本收敛到 release 阶段。为保证三端依赖行为一致，`lancedb` 统一约束为 `<0.26.0`。

## 签名与公证（macOS）

```bash
# 签名
codesign --deep --force --options runtime \
    --sign "Developer ID Application: NAME (TEAM_ID)" dist-pyinstaller/dist/Bao.app

# 公证
xcrun notarytool submit dist/Bao-x.y.z-macos-arm64.dmg \
    --apple-id "email" --team-id "TEAM_ID" --password "pwd" --wait

# Staple
xcrun stapler staple dist/Bao-x.y.z-macos-arm64.dmg
```

未签名的 .app 会被 Gatekeeper 拦截，用户需右键→打开。

如果你把签名/公证交给 GitHub Actions，证书和 notarization 凭据不要直接写进 workflow 文件，也不要贴进聊天或仓库；统一放进上面的 GitHub Secrets，由 `desktop-release.yml` 在 runner 的临时 keychain 中导入后使用。未配置这些 secrets 时，workflow 会给出 warning，并继续产出未签名的 macOS 资产。

## 已知问题与 Workaround

### 1. 备用 Nuitka 链版本收敛

CI 现已直接使用 `uv.lock` 锁定的 Nuitka `4.0.3`，不再在 workflow 里对 `.venv` 内部文件做运行时补丁。这样构建链路只有一个依赖事实源：`pyproject.toml` + `uv.lock`。

### 2. PySide6-Essentials 破损 QML 插件

PySide6-Essentials 附带了引用 PySide6-Addons 专属 framework 的 QML 插件，Nuitka 在 DLL 路径解析时会 FATAL 报错。

构建脚本会自动删除以下 8 个破损插件目录（位于 `PySide6/Qt/qml/` 下）：

| 插件路径 | 缺失的 Framework |
|---------|-----------------|
| `QtQml/StateMachine` | QtStateMachineQml.framework |
| `QtQml/XmlListModel` | — |
| `QtQml/WorkerScript` | — |
| `QtQuick/Pdf` | QtPdf.framework, QtPdfQuick.framework |
| `QtQuick/Scene2D` | Qt3DCore.framework, Qt3DQuickScene2D.framework |
| `QtQuick/Scene3D` | Qt3DQuickScene3D.framework |
| `QtQuick/Shapes/DesignHelpers` | QtQuickShapesDesignHelpers.framework |
| `QtQuick/VirtualKeyboard` | QtVirtualKeyboard.framework |

> 构建脚本 `build_mac.sh` 已内置自动清理逻辑，无需手动操作。

### 3. PySide6 Meta-Package 兼容性

当只安装 `PySide6-Essentials`（不含 `PySide6` meta-package）时，`PySide6.__file__` 为 `None`（缺少 `__init__.py`），Nuitka 的 pyside6 插件会崩溃。

**修复**：构建脚本自动检测并安装 meta-package（不拉 Addons）：

```bash
uv pip install PySide6==$(python -c "import PySide6.QtCore; print(PySide6.QtCore.qVersion())") --no-deps
```

> ⚠️ `uv run` / `uv sync` 会重新同步依赖并移除手动安装的包，因此每次构建前都需要执行此修复。构建脚本已自动处理。

### 4. lark_oapi（飞书 SDK）构建瓶颈

飞书 SDK `lark_oapi` 包含 10,103 个 Python 文件（57 个 API 模块），Nuitka 会逐一分析。但 Bao 只使用 `lark_oapi.api.im.v1`（即时消息）。

**修复**：通过 `--nofollow-import-to` 排除 54 个未使用的 API 模块，将模块分析量从 10,000+ 降至 ~4,500。

完整排除列表见 `build_mac.sh` 和 `build_win.bat` 中的 `lark_oapi` 裁剪段。

### 5. 数据目录与 package data 语义

普通静态目录与 Python package 资源要分开处理：

```bash
# ✅ 普通静态目录：走独立 data/ 前缀，避免和编译模块输出冲突
--include-data-dir=bao/skills=data/skills

# ✅ Python package 内的模板资源：仅声明 package data，避免与包输出路径重复冲突
--include-package-data=bao.templates.workspace.en:*.md
--include-package-data=bao.templates.workspace.zh:*.md
```

`bao/templates/workspace` 是真正的 Python package。若把它手工映射到 `bao/templates/...`，或同时再对同一路径叠加 `--include-package=bao.templates.workspace*`，在 macOS app bundle 下都会和编译产物的包命名空间冲突，触发 `NotADirectoryError`。因此模板资源必须按单一路径的 package data 语义打包。

### 6. Nuitka API 版本差异

Nuitka 4.x 中 `--noinclude-module` 选项不存在，正确选项为 `--nofollow-import-to=MODULE`。

### 7. TapTest.qml 占位文件

Nuitka 构建时会尝试复制 `app/qml/TapTest.qml`，但该文件不存在于项目中（疑似 Nuitka PySide6 插件的 QML 扫描缓存产物）。

**修复**：在 `app/qml/` 下创建空占位文件：

```qml
// Placeholder for Nuitka build compatibility
import QtQuick
Item {}
```

> 该文件已提交到仓库，无需手动操作。

### 8. pydoc 不可排除

`pyarrow.vendored.docscrape` 在运行时 import `pydoc`。Nuitka standalone 模式会主动阻止被排除模块的 import，导致 `ImportError`。

**结论**：不要将 `pydoc` 加入 `--nofollow-import-to` 排除列表。

### 9. Qt TLS 插件与 macOS OpenSSL 扫描

当前 Desktop 打包只需要 QML 相关 Qt 插件，不需要 QtNetwork 的 TLS 后端。保留 `tls` 插件会在 Intel macOS runner 上把 Homebrew 的 OpenSSL 动态库拉进 Nuitka 依赖扫描，导致类似下面的构建失败：

```text
FATAL: Error, problem with dependency scan of '/usr/local/lib/libcrypto.dylib' ...
```

**修复**：显式排除 Qt `tls` 插件：

```bash
--include-qt-plugins=qml
--noinclude-qt-plugins=tls
```

Desktop 当前未使用 `PySide6.QtNetwork`，因此这是收敛依赖面的结构性修复，不是环境补丁。

### 10. GUI 打包产物没有控制台 stderr

PyInstaller 的 `--windowed` Windows GUI 进程，以及 macOS 上从 Finder 启动的 `.app`，都可能没有可写的 `sys.stderr` / `sys.__stderr__`。若桌面启动路径无条件把它传给 `loguru.logger.add()`，应用会在 UI 起来前直接崩溃，报错类似：

```text
TypeError: Cannot log to objects of type 'NoneType'
```

**当前收口**：`bao/runtime_diagnostics.py` 会先探测可写控制台 sink；只有存在可写 stderr 时才接 console sink。无控制台时自动退化为“文件日志 + runtime diagnostics 内存尾部”单一路径，因此不会再因为 GUI 打包环境缺少 stderr 而启动失败。
## 实测构建数据

### 环境

- 机器：MacBook Air M4
- Python：3.11（Homebrew）
- Nuitka：4.0.3
- uv：0.10.5

### 构建时间

| 阶段 | 耗时 |
|------|------|
| 模块分析 | ~10 分钟 |
| C 编译（4,517 文件） | ~20 分钟 |
| 总计（首次） | ~30-40 分钟 |
| 后续构建（ccache） | 预计更快 |

### 产物体积

| 产物 | 大小 | 说明 |
|------|------|------|
| Bao.app | 599 MB | 未压缩 |
| DMG (arm64) | 177 MB | ~73% 压缩率 |

### 体积构成

| 组件 | 大小 | 占比 |
|------|------|------|
| Bao 主二进制 | ~244 MB | 41% |
| lancedb + Arrow | ~168 MB | 28% |
| PySide6 | ~57 MB | 10% |
| 其他依赖 | ~130 MB | 21% |

> 当前 DMG 177MB 超出 150MB 目标。潜在优化方向：`--lto=yes`、strip debug symbols、进一步排除未使用模块。

## 实测经验

1. 不要用 `--collect-all PySide6` — 会把未使用 Qt 模块打进包，体积暴涨
2. QML/资源目录必须通过 `--include-data-dir` 显式包含
3. `pyarrow` / `lancedb` 误裁剪会延迟爆雷 — UI 能启动但向量操作时崩溃
4. 优先 `standalone`（目录模式），不用 `onefile` — 首启更快、排障更易、杀软误报少
5. 每次瘦身都跑完整回归：启动、聊天、设置、网关、会话历史
6. 构建前务必清除 Nuitka bytecode 缓存（修补 bug 后）
7. `uv sync` 会重置 `.venv` 中的 Nuitka 补丁和 PySide6 meta-package — CI/CD 需在构建步骤中重新应用
8. workspace 模板建议按实际语言目录分别打包（`workspace/en`、`workspace/zh`），避免对仅含子目录的根目录使用 `--include-data-dir` 时产生 `No data files in directory ...` 告警
## 发布前检查清单

- [ ] 应用能启动并加载 Main.qml
- [ ] 会话列表、聊天、设置页正常
- [ ] 网关启动/停止/重启正常
- [ ] 图标正确（mac 圆角风格，win .ico）
- [ ] 浅色主题下欢迎胶囊、聊天空态 icon、侧栏标题/空态/chevron icon 保持清晰可见；发布前至少检查一张 `--smoke-screenshot` 的 chat 视图截图
- [ ] mac 分发前完成签名与 notarization

## 文件清单

```
app/scripts/
├── build_mac.sh          # macOS Nuitka 构建
├── build_win.bat         # Windows Nuitka 构建
├── package_win_installer.bat # 从 pyproject 动态注入版本并打包安装器
├── create_update_zip.sh  # 从 .app 生成桌面端更新 zip
├── generate_update_feed.py # 根据发布资产生成 desktop-update.json
├── validate_build_win_bat.py # Windows 批处理续行安全校验
├── create_dmg.sh         # macOS DMG 安装包
├── bao_installer.iss     # Windows Inno Setup 脚本
└── generate_app_icons.py # 图标生成（已有）

.github/workflows/
├── desktop-release.yml   # tag 发布：产出 macOS DMG/update zip + Windows setup.exe
├── desktop-update-feed.yml # release published：发布 desktop-update.json 到 GitHub Pages
└── desktop-ci-lite.yml   # PR/分支轻量验证：依赖可安装性 + 基础脚本校验

assets/
└── logo.icns             # macOS 应用图标

app/resources/
├── logo-circle.png       # 应用内 UI logo
└── logo.ico              # Windows 应用/窗口/安装器图标
```

## 产物清理

```bash
rm -rf dist/ build/
```
