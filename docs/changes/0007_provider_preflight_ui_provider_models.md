[FIX] 2026-02-09 提供方连通性检测与设置页模型配置体验收敛（local）

## 当前进度

- 已完成：连通性检测改为“拉取 provider 模型列表并校验已选 model id”，不再发送最小推理请求。
- 已完成：前端连通性错误提示改为用户可读分类（API Key/模型 ID/权限/限流/超时/服务不可用）。
- 已完成：设置页支持“一个提供方配置多个模型 ID”，并将模型 ID 列表移动到底部编辑。
- 已完成：设置页移除大写 `PLACEHOLDER` 文案，改为背景格式提示区；新增/删除操作改为 icon 按钮。
- 已完成：前端可见文案移除“网关/Gateway”字样，统一为服务/运行状态语义。
- 已完成：按反馈修正为“输入框内普通 placeholder”，移除输入框下方示例提示块。
- 已完成：对话输入在连通性检测中改为非阻塞；检测超时缩短为 2.5s，避免长时间卡在检查态。
- 已完成：使用 code-simplifier 对 provider/chat/settings 相关变更做行为等价简化，收敛重复分支与重复判断。

## 改动记录（最近）

- `apps/desktop/src-tauri/src/provider.rs`：
  - `providerPreflight` 改为通过各 provider 的模型列表接口进行校验（OpenAI/xAI `/models`、Anthropic `/v1/models`、Gemini `/v1beta/models`）。
  - 新增模型列表解析与 model id 匹配逻辑，确保“已选模型在返回列表中”。
  - 保留 `format_preflight_error`，将底层错误标准化为前端友好类别。
- `apps/desktop/src/pages/chat/layout.tsx`：
  - 预检失败原因改为分类映射文案，避免直接暴露底层错误串。
  - provider 选项改为从“提供方 + 模型 ID 列表”展开生成可选模型。
  - 对话 guard 调整为“检测中不阻塞输入”，仅在检测完成且失败时阻塞并提示。
  - 通过 code-simplifier 抽出重复消息插入/错误关键词匹配辅助函数，保持分支优先级不变。
- `apps/desktop/src/lib/provider-profiles.ts`：
  - `ProviderProfile` 从单一 `model` 升级为 `modelIds: string[]`，并保留旧 `provider.model` 的兼容读取。
  - 新增 `expandProfilesToModelProfiles`，用于聊天页按模型粒度选择。
- `apps/desktop/src/pages/settings.tsx`：
  - 模型输入改为“模型 ID 列表（多行）”，放在配置区底部。
  - 新增/删除按钮改为 icon-only；移除输入 placeholder，改为背景提示卡。
  - 保存校验调整为 `provider + modelIds + baseUrl` 必填，并持久化首个模型到 `provider.model` 兼容字段。
  - 按反馈恢复为输入框内 placeholder（含 API Key 与模型 ID 列表），删除下方提示卡。
  - 通过 code-simplifier 合并语言切换重复 JSX 与列表处理辅助函数，保持 UI 行为不变。
- `apps/desktop/src/i18n/desktop-locales.ts`：
  - 新增模型连通性错误分类文案与设置页格式提示文案。
  - 替换前端可见“网关/Gateway”文本为“服务/运行状态”语义。

## 未来发展（优先级）

1. 高：补充设置页 e2e（多模型 ID 增删改存）与预检错误映射回归用例。
2. 中：将 provider 预检超时和重试参数可配置化（按提供方维度）。
3. 中：在聊天页模型下拉增加“提供方 / 模型 ID”分组展示，降低多模型场景识别成本。
