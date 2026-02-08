[FIX] 2026-02-08 桌面侧边栏收起态对齐与宽度收敛（local）

## 当前进度

- 已完成：修复侧边栏收起态导航 icon 视觉偏移（歪斜）问题。
- 已完成：继续收窄收起态横向宽度，减少空白占比。
- 已完成：对本次侧边栏改动执行 code-simplifier 清理，保持行为不变。

## 改动记录（最近）

- `apps/desktop/src/components/layout/app-shell.tsx`：
  - 收起态侧边栏宽度保持为 `72`，并将收起态内外层 padding 统一为 `p-2`，避免内容区过窄导致视觉偏移。
  - 收起态头部保持单按钮居中布局，避免与品牌区混排造成横向重心偏移。
  - 收起态导航容器改为 `items-center`，导航项采用固定 `h-10 w-10`，保证每个 icon 共享统一视觉中心。
  - 基于 code-simplifier 对条件类名进行了等价提炼（`getSidebarPaddingClass/getHeaderLayoutClass/getNavLayoutClass/getNavItemLayoutClass`），减少重复分支。

## 未来发展（优先级）

1. 高：补充桌面端侧边栏收起/展开的视觉回归用例（确保 icon 居中与宽度不回退）。
2. 中：将侧边栏宽度与收起态尺寸提取为可配置 token，降低后续调整成本。
3. 中：评估按导航内容长度自适应展开宽度的上限策略，避免不同语言下文本截断波动。
