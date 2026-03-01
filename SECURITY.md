# 安全配置

### 1. 工作区沙箱 (`restrictToWorkspace`)

将 Agent 的所有文件和命令操作限制在工作区目录内。

```json
{
  "tools": {
    "restrictToWorkspace": true
  }
}
```

启用后：

- `read_file` / `write_file` / `edit_file` 仅能访问 `~/.bao/workspace/` 下的文件
- `exec` 的工作目录被锁定在工作区内
- 路径穿越（`../`）会被拦截

> **生产环境强烈建议启用此选项。**

### 2. 渠道访问控制 (`allowFrom`)

通过用户白名单限制谁能与你的 Bot 对话。

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["123456789"]
    },
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["+8613800138000"]
    }
  }
}
```

- `allowFrom` 为空数组时**允许所有人**访问（个人使用默认值）
- Telegram 用户 ID 可通过 `@userinfobot` 获取
- WhatsApp 需填写完整国际号码（含国家代码）
- 建议定期检查访问日志，排查未授权访问

### 3. API Key 管理

**关键原则**：永远不要将 API Key 提交到版本控制。

```bash
# ✅ 正确：配置文件设置严格权限
chmod 600 ~/.bao/config.jsonc

# ❌ 错误：硬编码在代码中或提交到 Git
```

建议：

- API Key 存放在 `~/.bao/config.jsonc`，文件权限设为 `0600`
- 可使用环境变量传入敏感信息
- 生产环境建议使用 OS Keyring / 密钥管理器
- 定期轮换 API Key
- 开发和生产使用不同的 Key

### 4. Shell 命令安全

`exec` 工具可执行 Shell 命令。虽然内置了危险命令拦截，你仍应注意：

- ✅ 审查 Agent 日志中的所有工具调用
- ✅ 使用专用系统用户运行，限制权限
- ✅ 永远不要以 root 运行 bao
- ❌ 不要禁用安全检查
- ❌ 不要在含敏感数据的系统上未经审查运行

说明：当前子代理默认不对内部目录做额外硬拦截；如果你需要更强隔离，请启用 `restrictToWorkspace` 并通过系统权限限制敏感目录。

**内置拦截的危险命令**：

- `rm -rf /` — 根目录删除
- Fork 炸弹
- `mkfs.*` — 文件系统格式化
- 裸磁盘写入
- 其他破坏性操作

### 5. 文件系统保护

文件操作内置路径穿越防护，但仍建议：

- ✅ 使用专用用户账户运行
- ✅ 通过文件系统权限保护敏感目录
- ✅ 定期审计日志中的文件操作
- ✅ 启用 `restrictToWorkspace` 进一步限制
- ✅ 通过系统权限将 `lancedb/`、`memory/`、`.bao/` 等目录按需设为只读/受限
- ❌ 不要给予不受限的敏感文件访问权限

### 6. 网络安全

**API 调用**：

- 所有外部 API 调用默认使用 HTTPS
- 配置了超时以防止请求挂起
- 可通过防火墙限制出站连接

**WhatsApp Bridge**：

- Bridge 绑定在 `127.0.0.1:3001`（仅本地访问，外部网络不可达）
- 配置 `bridgeToken` 启用 Python 与 Node.js 之间的共享密钥认证
- 认证数据存于 `~/.bao/whatsapp-auth`，权限应为 `0700`

### 7. 依赖安全

```bash
# Python 依赖审计
pip install pip-audit
pip-audit

# Node.js 依赖审计（WhatsApp Bridge）
cd bridge
npm audit
npm audit fix

# 更新到最新安全版本
pip install --upgrade bao-ai
```

`ws` 已更新至 `>=8.17.1` 修复 DoS 漏洞
建议定期执行 `pip-audit` 和 `npm audit`

## 生产部署建议

### 环境隔离

```bash
# 容器化运行
docker run --rm -it python:3.11
pip install bao-ai
```

### 专用用户

```bash
sudo useradd -m -s /bin/bash bao
sudo -u bao bao
```

### 权限设置

```bash
chmod 700 ~/.bao
chmod 600 ~/.bao/config.jsonc
chmod 700 ~/.bao/whatsapp-auth
```

### 运行时安全

- 在 API 提供商处配置用量上限
- 监控异常用量
- 配置日志监控

## 内置安全控制一览

| 层面 | 机制 |
|------|------|
| 输入验证 | 路径穿越防护、危险命令模式检测、HTTP 请求长度限制 |
| 访问认证 | `allowFrom` 白名单、认证失败日志、默认开放（个人使用） |
| 资源保护 | 命令超时 60s、输出截断 10KB、HTTP 超时 10-30s |
| 凭据保护 | `SecretStr` 防日志/序列化泄露、`model_dump()` 输出 `**********` |
| 工作区沙箱 | `restrictToWorkspace` 限制所有工具操作、路径穿越拦截 |
| 安全通信 | 外部 API 全 HTTPS、Telegram TLS、WhatsApp Bridge 仅本地绑定 + Token 认证 |

## 已知限制

⚠️ **当前安全限制**：

1. **无内置速率限制** — 用户可发送无限消息（需自行添加）
2. **运行时内存中明文** — SecretStr 防止日志/序列化泄露，但运行时 `.get_secret_value()` 仍为明文（生产环境建议使用 Keyring）
3. **无会话过期** — 无自动会话超时机制
4. **有限的命令过滤** — 仅拦截明显的危险模式
5. **有限的审计日志** — 安全事件日志不完整（可按需增强）

## 部署检查清单

部署 bao 前请确认：

- [ ] API Key 安全存储（未写入代码）
- [ ] 配置文件权限设为 `0600`（`~/.bao/config.jsonc`）
- [ ] 所有渠道已配置 `allowFrom` 白名单
- [ ] 以非 root 用户运行
- [ ] 文件系统权限正确限制
- [ ] 依赖已更新至最新安全版本
- [ ] 日志已配置监控
- [ ] API 提供商已设置用量上限
- [ ] 生产环境启用 `restrictToWorkspace`
- [ ] 已审查自定义技能/工具的安全性

## 事件响应

如果怀疑发生安全事件：

1. **立即撤销** 泄露的 API Key
2. **检查日志** 排查未授权访问
3. **排查** 异常文件修改
4. **轮换** 所有凭证
5. **更新** 到最新版本
6. **上报** 给维护者

## 更新记录

**最后更新**：2026-03-01
