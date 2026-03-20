"""Provider, tool, and UI configuration models."""

from pydantic import Field, SecretStr, model_validator

from ._schema_base import (
    Base,
    ExecSandboxModeLiteral,
    PolicyWarningSpec,
    ProviderTypeLiteral,
    ToolExposureModeLiteral,
    get_args,
    warn_unknown_policy,
)


class ProviderConfig(Base):
    type: str = "openai"
    api_key: SecretStr = SecretStr("")
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None

    @model_validator(mode="after")
    def _warn_policies(self) -> "ProviderConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="ProviderConfig",
                field_name="type",
                value=self.type,
                allowed_values=get_args(ProviderTypeLiteral),
            )
        )
        return self


class HeartbeatConfig(Base):
    enabled: bool = True
    interval_s: int = 30 * 60


class HubConfig(Base):
    host: str = "0.0.0.0"
    port: int = 18790
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class EmbeddingConfig(Base):
    model: str = ""
    api_key: SecretStr = SecretStr("")
    base_url: str = ""
    dim: int = 0
    timeout_seconds: int = 15
    retry_attempts: int = 2
    retry_backoff_ms: int = 200

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.api_key.get_secret_value())


class WebSearchConfig(Base):
    provider: str = ""
    brave_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")
    exa_api_key: SecretStr = SecretStr("")
    max_results: int = 5


class WebBrowserConfig(Base):
    enabled: bool = True


class WebToolsConfig(Base):
    proxy: str | None = None
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    browser: WebBrowserConfig = Field(default_factory=WebBrowserConfig)


class ExecToolConfig(Base):
    timeout: int = 60
    path_append: str = ""
    sandbox_mode: str = "semi-auto"

    @model_validator(mode="after")
    def _warn_sandbox_mode(self) -> "ExecToolConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="ExecToolConfig",
                field_name="sandbox_mode",
                value=self.sandbox_mode,
                allowed_values=get_args(ExecSandboxModeLiteral),
            )
        )
        return self


class MCPServerConfig(Base):
    type: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    tool_timeout_seconds: int = 30
    slim_schema: bool | None = None
    max_tools: int | None = None


class ImageGenerationConfig(Base):
    api_key: SecretStr = SecretStr("")
    model: str = ""
    base_url: str = ""


class DesktopConfig(Base):
    enabled: bool = True


class ToolExposureConfig(Base):
    mode: str = "off"
    domains: list[str] = Field(
        default_factory=lambda: [
            "core",
            "messaging",
            "handoff",
            "web_research",
            "desktop_automation",
            "coding_backend",
        ]
    )

    @model_validator(mode="after")
    def _warn_mode(self) -> "ToolExposureConfig":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="ToolExposureConfig",
                field_name="mode",
                value=self.mode,
                allowed_values=get_args(ToolExposureModeLiteral),
            )
        )
        return self


class ToolsConfig(Base):
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    restrict_to_workspace: bool = False
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    mcp_max_tools: int = 50
    mcp_slim_schema: bool = True
    image_generation: ImageGenerationConfig = Field(default_factory=ImageGenerationConfig)
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    tool_exposure: ToolExposureConfig = Field(default_factory=ToolExposureConfig)


class UIConfig(Base):
    class UpdateConfig(Base):
        enabled: bool = True
        auto_check: bool = True
        channel: str = "stable"
        feed_url: str = "https://suge8.github.io/Bao/desktop-update.json"

    update: UpdateConfig = Field(default_factory=UpdateConfig)
