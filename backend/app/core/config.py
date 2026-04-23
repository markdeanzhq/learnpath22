from __future__ import annotations

import base64
import hashlib
import os
import socket
import sys
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Optional
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url

PYTHON_BASELINE = "3.12"
PROTOTYPE_SCOPE = "machine_learning_only"
DELIVERY_STAGE = "graduation_prototype"
RUNTIME_SETTINGS_SCOPE = "sqlite-persisted"
RUNTIME_SETTING_KEYS = (
    "llm_base_url",
    "llm_model",
    "llm_api_key",
    "search_api_key",
    "llm_explanation_polish",
)
SECRET_RUNTIME_SETTING_KEYS = frozenset({
    "llm_api_key",
    "search_api_key",
})
_RUNTIME_SECRET_PREFIX = "enc:v1:"
_RUNTIME_SECRET_KEY_BYTES = 32
_RUNTIME_SECRET_KEY_SALT = b"learnpath/runtime-secrets/v1"
_RUNTIME_SECRET_PBKDF2_ITERATIONS = 390000
_LOOPBACK_HOSTS = {"localhost"}
_METADATA_IPS = {
    ip_address("100.100.100.200"),
    ip_address("169.254.169.254"),
    ip_address("169.254.170.2"),
}

_TRUTHY_BOOL_STRINGS = frozenset({"true", "1", "yes", "on", "y", "t"})
_FALSY_BOOL_STRINGS = frozenset({"false", "0", "no", "off", "n", "f"})


def parse_runtime_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUTHY_BOOL_STRINGS:
            return True
        if normalized in _FALSY_BOOL_STRINGS:
            return False
    raise ValueError(f"无法解析运行时布尔值: {value!r}")


def serialize_runtime_bool(value: bool) -> str:
    return "true" if value else "false"


class Settings(BaseSettings):
    PROJECT_NAME: str = "LearnPath-KG"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    SQLITE_URL: str = "sqlite+aiosqlite:///./learnpath.db"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "learnpath"

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-3.5-turbo"
    SEARCH_API_KEY: str = ""
    RUNTIME_SECRETS_MASTER_KEY: str = ""

    LLM_EXPLANATION_POLISH: bool = False

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _is_loopback_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    if normalized in _LOOPBACK_HOSTS:
        return True

    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_runtime_llm_base_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError as exc:
        raise ValueError("llm_base_url 必须是有效的 URL") from exc

    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("llm_base_url 必须是有效的 http(s) URL")
    if parts.username or parts.password:
        raise ValueError("llm_base_url 不允许包含认证信息")
    if parts.scheme == "http" and not _is_loopback_hostname(parts.hostname):
        raise ValueError("llm_base_url 仅允许 loopback 地址使用 http")

    try:
        target_ip = ip_address(parts.hostname)
    except ValueError:
        lowered_host = parts.hostname.lower()
        if lowered_host.endswith(".local"):
            raise ValueError("llm_base_url 不允许指向本地域名")
        if lowered_host == "metadata.google.internal":
            raise ValueError("llm_base_url 不允许指向元数据地址")
        try:
            resolved_ips = {
                ip_address(addr_info[4][0])
                for addr_info in socket.getaddrinfo(parts.hostname, parts.port or None, proto=socket.IPPROTO_TCP)
            }
        except socket.gaierror:
            return value
        for resolved_ip in resolved_ips:
            if resolved_ip.is_loopback:
                continue
            if resolved_ip in _METADATA_IPS:
                raise ValueError("llm_base_url 不允许指向元数据地址")
            if (
                resolved_ip.is_private
                or resolved_ip.is_link_local
                or resolved_ip.is_multicast
                or resolved_ip.is_unspecified
                or resolved_ip.is_reserved
            ):
                raise ValueError("llm_base_url 不允许指向私有或非公网 IP")
        return value

    if target_ip.is_loopback:
        return value
    if target_ip in _METADATA_IPS:
        raise ValueError("llm_base_url 不允许指向元数据地址")
    if (
        target_ip.is_private
        or target_ip.is_link_local
        or target_ip.is_multicast
        or target_ip.is_unspecified
        or target_ip.is_reserved
    ):
        raise ValueError("llm_base_url 不允许指向私有或非公网 IP")
    return value


def _get_runtime_secret_master_key(settings: Settings) -> bytes:
    if settings.RUNTIME_SECRETS_MASTER_KEY:
        return settings.RUNTIME_SECRETS_MASTER_KEY.strip().encode("utf-8")

    key_path = _get_runtime_secret_key_path(settings)
    if key_path is None:
        return os.urandom(_RUNTIME_SECRET_KEY_BYTES)

    if key_path.exists():
        key = key_path.read_bytes()
        if not key:
            raise RuntimeError("运行时密钥主密钥无效，无法加载持久化配置")
        return key

    key = os.urandom(_RUNTIME_SECRET_KEY_BYTES)
    _write_runtime_secret_key_file(key_path, key)
    return key


def _get_runtime_secret_key_path(settings: Settings) -> Optional[Path]:
    try:
        database = make_url(settings.SQLITE_URL).database
    except Exception:
        return None

    if not database or database == ":memory:":
        return None

    database_path = Path(database).expanduser()
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    database_path = database_path.resolve()
    return database_path.with_name(f".{database_path.name}.runtime-secrets.key")


def _write_runtime_secret_key_file(key_path: Path, key: bytes) -> None:
    key_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = key_path.with_name(f"{key_path.name}.tmp")
    temp_path.write_bytes(key)
    os.replace(temp_path, key_path)
    if os.name != "nt":
        os.chmod(key_path, 0o600)


@lru_cache(maxsize=1)
def _get_runtime_secret_master_key_cached() -> bytes:
    return _get_runtime_secret_master_key(get_settings())


def _build_runtime_secret_key(master_key: bytes) -> bytes:
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        master_key,
        _RUNTIME_SECRET_KEY_SALT,
        _RUNTIME_SECRET_PBKDF2_ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived_key)


@lru_cache(maxsize=1)
def _get_runtime_secret_fernet() -> Fernet:
    return Fernet(_build_runtime_secret_key(_get_runtime_secret_master_key_cached()))


def encode_runtime_setting_value(setting_key: str, value: str) -> str:
    if setting_key not in SECRET_RUNTIME_SETTING_KEYS or not value:
        return value
    encrypted_value = _get_runtime_secret_fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{_RUNTIME_SECRET_PREFIX}{encrypted_value}"


def decode_runtime_setting_value(setting_key: str, value: str) -> tuple[str, bool]:
    if setting_key not in SECRET_RUNTIME_SETTING_KEYS or not value:
        return value, False
    if not value.startswith(_RUNTIME_SECRET_PREFIX):
        return value, True

    try:
        decrypted_value = _get_runtime_secret_fernet().decrypt(
            value.removeprefix(_RUNTIME_SECRET_PREFIX).encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError(f"运行时配置中的 {setting_key} 无法解密，请检查主密钥配置") from exc

    return decrypted_value, False


class RuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_base_url: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None
    llm_model: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None
    llm_api_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None
    search_api_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None
    llm_explanation_polish: Optional[bool] = None

    @field_validator("llm_base_url")
    @classmethod
    def validate_llm_base_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _validate_runtime_llm_base_url(value)


# Runtime overrides cached in-process and backed by SQLite.
_runtime_overrides: dict[str, str] = {}
_lock = Lock()


def _get_runtime_snapshot() -> tuple[Settings, dict[str, str]]:
    settings = get_settings()
    with _lock:
        return settings, _runtime_overrides.copy()


def get_llm_config() -> dict[str, str]:
    settings, runtime_overrides = _get_runtime_snapshot()
    return {
        "llm_base_url": runtime_overrides.get("llm_base_url", settings.LLM_BASE_URL),
        "llm_model": runtime_overrides.get("llm_model", settings.LLM_MODEL),
        "llm_api_key": runtime_overrides.get("llm_api_key", settings.LLM_API_KEY),
    }


def get_search_api_key() -> str:
    settings, runtime_overrides = _get_runtime_snapshot()
    return runtime_overrides.get("search_api_key", settings.SEARCH_API_KEY)


def get_llm_polish_enabled() -> bool:
    settings, runtime_overrides = _get_runtime_snapshot()
    override = runtime_overrides.get("llm_explanation_polish")
    if override is None:
        return settings.LLM_EXPLANATION_POLISH
    try:
        return parse_runtime_bool(override)
    except ValueError:
        return settings.LLM_EXPLANATION_POLISH


def get_environment_fingerprint() -> dict[str, Any]:
    settings, runtime_overrides = _get_runtime_snapshot()
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    llm_api_key = runtime_overrides.get("llm_api_key", settings.LLM_API_KEY)
    search_api_key = runtime_overrides.get("search_api_key", settings.SEARCH_API_KEY)

    return {
        "prototype_scope": PROTOTYPE_SCOPE,
        "delivery_stage": DELIVERY_STAGE,
        "python_baseline": PYTHON_BASELINE,
        "python_version": python_version,
        "runtime_settings_scope": RUNTIME_SETTINGS_SCOPE,
        "sqlite_backend": settings.SQLITE_URL.partition(":")[0],
        "neo4j_scheme": settings.NEO4J_URI.partition(":")[0],
        "llm_provider": "openai_compatible",
        "llm_api_key_set": bool(llm_api_key),
        "search_provider": "tavily",
        "search_api_key_set": bool(search_api_key),
    }


def replace_runtime_settings(overrides: dict[str, str]) -> None:
    sanitized_overrides: dict[str, str] = {}
    for key, value in overrides.items():
        if key not in RUNTIME_SETTING_KEYS:
            continue
        if key == "llm_base_url":
            try:
                value = _validate_runtime_llm_base_url(value)
            except ValueError:
                continue
        if key == "llm_explanation_polish":
            try:
                value = serialize_runtime_bool(parse_runtime_bool(value))
            except ValueError:
                continue
        sanitized_overrides[key] = value

    with _lock:
        _runtime_overrides.clear()
        _runtime_overrides.update(sanitized_overrides)
