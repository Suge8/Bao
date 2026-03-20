"""Root configuration model."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._schema_agents import AgentsConfig
from ._schema_channels import ChannelsConfig
from ._schema_tools import HubConfig, ProviderConfig, ToolsConfig, UIConfig


class Config(BaseSettings):
    """Root configuration for Bao."""

    config_version: int = Field(default=6, alias="config_version")
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    hub: HubConfig = Field(default_factory=HubConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @property
    def workspace_path(self) -> Path:
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple[ProviderConfig | None, str | None]:
        model_str = model or self.agents.defaults.model
        if not model_str:
            return None, None
        model_prefix = model_str.split("/", 1)[0] if "/" in model_str else ""
        normalized_prefix = model_prefix.lower().replace("-", "_")
        if normalized_prefix:
            return self._match_named_provider(normalized_prefix)
        return self._first_usable_provider()

    def _match_named_provider(
        self, normalized_prefix: str
    ) -> tuple[ProviderConfig | None, str | None]:
        for provider_name, provider in self.providers.items():
            if provider_name.lower().replace("-", "_") == normalized_prefix:
                matched = provider if self._has_usable_key(provider) else None
                return matched, provider_name
        return None, None

    def _first_usable_provider(self) -> tuple[ProviderConfig | None, str | None]:
        for provider_name, provider in self.providers.items():
            if self._has_usable_key(provider):
                return provider, provider_name
        return None, None

    @staticmethod
    def _has_usable_key(provider: ProviderConfig) -> bool:
        return provider.type == "openai_codex" or bool(provider.api_key.get_secret_value())

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        provider, _ = self._match_provider(model)
        return provider

    def get_provider_name(self, model: str | None = None) -> str | None:
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        provider = self.get_provider(model)
        return provider.api_key.get_secret_value() if provider else None

    def get_api_base(self, model: str | None = None) -> str | None:
        provider = self.get_provider(model)
        if provider and provider.api_base:
            return provider.api_base
        return self._default_api_base(provider)

    @staticmethod
    def _default_api_base(provider: ProviderConfig | None) -> str | None:
        if provider is None:
            return None
        if provider.type == "openai":
            return "https://api.openai.com/v1"
        if provider.type == "anthropic":
            return "https://api.anthropic.com"
        if provider.type == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/models"
        return None

    model_config = SettingsConfigDict(env_prefix="bao_", env_nested_delimiter="__")
