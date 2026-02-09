[FIX] 2026-02-09 聊天头部清空 + 模型选择迁移到 Topbar（local）

## 当前进度

- 已完成：移除聊天右侧面板顶部整行（会话ID/模型选择/新建按钮）。
- 已完成：将模型选择器迁移到全局 Topbar（仅聊天页显示）。
- 已完成：将“新建对话”按钮迁移到左侧会话列表区域。
- 已完成：会话搜索与新建按钮合并为同一行，并缩短搜索输入宽度。
- 已完成：对本次聊天页/Topbar 改动执行 code-simplifier 等价清理（保持行为不变）。

## 改动记录（最近）

- `apps/desktop/src/pages/chat/layout.tsx`：
  - 删除聊天流上方整行头部，避免显示 `s-xxxx` 会话技术 ID。
  - 左侧会话列表顶部新增“新建对话”按钮入口。
  - 会话搜索框与“新建对话”按钮并排展示（同一行），搜索框最大宽度收敛为 `220px`。
  - 基于 code-simplifier 抽取消息前插辅助函数与发送禁用状态派生，减少重复分支。
- `apps/desktop/src/components/layout/topbar.tsx`：
  - 新增聊天页路由判断（`/`），仅在聊天页显示模型下拉选择器。
  - 复用 provider settings 链路，切换模型时同步写入 `provider.selectedProfileId/provider.active/provider.model/provider.baseUrl/provider.apiKey`。
  - 监听 `settings.update` 的 `provider.*` 变更并刷新下拉状态。
  - 基于 code-simplifier 抽取 provider 可选条件与模型切换回调，降低 JSX 内联复杂度。

## 未来发展（优先级）

1. 高：补充聊天页 Topbar 模型切换交互回归（切换后发送守卫与可发状态一致）。
2. 中：将 Topbar 模型选择提取为独立组件，减少布局组件职责。
3. 中：统一聊天页与设置页的 provider profile 读写复用，避免双处逻辑漂移。
