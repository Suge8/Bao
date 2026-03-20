# Bao Desktop App

Bao 的桌面端主入口。

它的目标很简单：**下载后就能用，打开后就能聊**。

---

## 你可以拿它做什么

- 和 Bao 聊天
- 让 Bao 记住你的偏好和长期上下文
- 切换不同会话
- 切换模型和服务
- 查看运行状态与日志
- 在桌面上管理更新、设置和计划

---

## 安装与启动

### 方式 1：直接安装

前往 [GitHub Releases](https://github.com/Suge8/Bao/releases) 下载对应平台安装包。

- **macOS**：`Bao-x.y.z-macos-arm64.dmg` 或 `Bao-x.y.z-macos-x86_64.dmg`
- **Windows**：`Bao-x.y.z-windows-x64-setup.exe`

安装后直接打开 Bao Desktop。

### 方式 2：本地运行

```bash
uv sync --extra desktop
uv run python app/main.py
```

如需本地打包或验证桌面产物，使用：

```bash
uv sync --extra desktop-build-pyinstaller
```

---

## 首次使用

第一次打开时，按这三步走：

1. 选择界面语言
2. 配置 AI 服务
3. 选择默认聊天模型

完成后就可以开始使用了。

---

## 常用命令

Bao Desktop 支持这些基础命令：

| 命令 | 作用 |
|------|------|
| `/new` | 新建对话 |
| `/stop` | 停止当前任务 |
| `/session` | 查看并切换会话 |
| `/delete` | 删除当前会话 |
| `/model` | 切换模型 |
| `/memory` | 管理记忆 |
| `/help` | 查看帮助 |

---

## 常用入口

- **左下角 logo**：进入 Settings
- **logo 右侧 Diagnostics**：查看运行状态与日志
- **侧边栏**：切换会话、profile 和计划
- **Settings**
  - `回复方式与模型 / Response Setup`
  - `高级 / Advanced`
  - `桌面更新 / Desktop Updates`

---

## 常见问题

### 不知道从哪开始

先完成首次使用的三步配置，然后直接聊天。

### 想看当前状态

点左下角 logo 右侧的 Diagnostics。

### 想快速换会话

直接用侧边栏，或者输入 `/session`。

### 想停止当前任务

输入 `/stop`。

---

## 打包与资源

桌面发布默认以 **PyInstaller** 为 primary 主链，**Nuitka** 只保留为 backup 备用链。常用脚本：

- `app/scripts/build_mac_pyinstaller.sh`
- `app/scripts/build_win_pyinstaller.bat`
- `app/scripts/generate_installer_assets.py`

更完整的桌面打包说明见 [DESKTOP_PACKAGING.md](/Users/sugeh/Project/Bao/app/DESKTOP_PACKAGING.md)。

---

## 权限与运行前提

- macOS 桌面产物会写入 `NSAppleEventsUsageDescription`
- 若启用 iMessage，需要允许 Bao 控制 `Messages`
- 还需要为 `Bao.app` 打开 `Full Disk Access`

---

## 资源事实源

- Windows 安装器与应用图标统一使用 `app/resources/logo.ico`
- `logo-circle.png` 只保留给应用内 UI 预览
- 应用级字体统一使用 `app/resources/fonts/OPPO Sans.ttf`
- 字体加载入口收口在 `app/main.py`，只保留应用级这一处字体决策
- 安装器与 DMG 品牌资源统一由 `generate_installer_assets.py` 生成
- 统一产出 `dmg-background.png`，并保持 `windowContentInsetTop/Side/Bottom` 的同一视觉节奏
- 这条路径的目标是避免 Win/mac 安装体验与桌面端首屏漂移

---

## 一句话

**下载即用，打开即聊。**
