# Bundled Dimsums

本目录包含 **随安装包分发、不可卸载** 的内置点心（Bundled Dimsums）。

阶段0/1 仅提供目录契约与 manifest stubs，用于并行开发隔离：

- 每个点心在独立子目录内自包含（manifest + 资源）。
- Core 以 `schemas/dimsum_manifest_v1.schema.json` 校验 manifest。
- Router/Memory/Corrector/Provider 均以点心形式存在（不可把策略写进 core）。
