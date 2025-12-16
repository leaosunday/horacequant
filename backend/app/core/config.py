from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    线上风格配置：全部来自环境变量，默认值尽量安全。
    """

    model_config = SettingsConfigDict(env_prefix="HQ_", case_sensitive=False)

    app_name: str = "horacequant-backend"
    env: str = Field(default="prod", description="运行环境标识：prod/staging/dev")

    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8000, description="服务监听端口")

    log_level: str = Field(default="INFO", description="日志级别：DEBUG/INFO/WARNING/ERROR")

    # 安全：默认只允许本机/容器健康检查；线上请显式配置域名或网关
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])


settings = Settings()

