from __future__ import annotations

from typing import Annotated

import getpass
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    # ---------- Postgres ----------
    pg_host: str = Field(default="127.0.0.1")
    pg_port: int = Field(default=5432)
    pg_user: str = Field(default_factory=getpass.getuser)
    pg_password: str = Field(default="")
    pg_db: str = Field(default="horace_quant")
    pg_ssl: str = Field(default="", description="例如 require；空字符串表示不启用")
    pg_pool_min: int = Field(default=1)
    pg_pool_max: int = Field(default=10)
    pg_command_timeout: float = Field(default=30.0)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, v):
        """
        允许使用两种方式配置：
        - HQ_ALLOWED_HOSTS='["example.com","api.example.com"]'  (JSON)
        - HQ_ALLOWED_HOSTS='example.com,api.example.com'        (逗号分隔)
        - HQ_ALLOWED_HOSTS='*'                                  (允许任意 Host，不建议线上使用)
        """
        if v is None:
            return v
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return []
            if s == "*":
                return ["*"]
            # JSON 形式交给 pydantic 自己 decode 也可，但这里做兼容
            if s.startswith("["):
                return v
            return [x.strip() for x in s.split(",") if x.strip()]
        return v


settings = Settings()

