"""Common data types used across the header emulator package."""

from __future__ import annotations

from enum import Enum
from ipaddress import IPv4Address, IPv6Address
from typing import Callable, Iterable, Mapping, MutableMapping, Optional, Protocol, Sequence

from pydantic import BaseModel, Field, field_validator

HeaderName = str
HeaderValue = str
HeaderTuple = tuple[HeaderName, HeaderValue]
HeaderMap = MutableMapping[HeaderName, HeaderValue]
FrozenHeaderMap = Mapping[HeaderName, HeaderValue]
CookiesMap = MutableMapping[str, str]


class RotationStrategy(str, Enum):
    """Supported header/proxy rotation strategies."""

    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    STICKY = "sticky"


class FailurePolicy(str, Enum):
    """How failing proxies or profiles are treated."""

    EVICT = "evict"
    COOLDOWN = "cooldown"
    RETAIN = "retain"


class ProxyScheme(str, Enum):
    """Proxy transport types."""

    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyAuth(BaseModel):
    """Authentication information for a proxy entry."""

    username: str
    password: str


class ProxyConfig(BaseModel):
    """Represents a single proxy endpoint in the rotation pool."""

    scheme: ProxyScheme = ProxyScheme.HTTP
    host: str
    port: int = Field(..., ge=1, le=65535)
    auth: Optional[ProxyAuth] = None
    region: Optional[str] = Field(
        default=None,
        description="Geographical region or ISO country code associated with the proxy.",
    )
    weight: float = Field(default=1.0, ge=0.0)
    tags: set[str] = Field(default_factory=set)
    last_checked: Optional[int] = Field(
        default=None,
        description="Unix timestamp of the last successful health check.",
    )

    @property
    def netloc(self) -> str:
        """Return host:port formatted pair."""

        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        """Return a ready-to-use proxy URL."""

        if self.auth:
            return f"{self.scheme.value}://{self.auth.username}:{self.auth.password}@{self.netloc}"
        return f"{self.scheme.value}://{self.netloc}"


class LocaleProfile(BaseModel):
    """Locale metadata used for Accept-Language and geo selection."""

    language: str = Field(..., description="BCP47 language tag, e.g. 'en-US'.")
    quality: float = Field(default=1.0, ge=0.0, le=1.0)
    country: Optional[str] = Field(default=None, description="ISO 3166-1 alpha-2 country code.")
    currency: Optional[str] = Field(default=None, description="Currency code for the locale.")
    timezone: Optional[str] = Field(default=None, description="IANA time zone identifier.")


class UserAgentMetadata(BaseModel):
    """Information extracted from a user-agent string."""

    family: str = Field(..., description="Browser or client family, e.g. 'Chrome'.")
    version: Optional[str] = Field(default=None, description="Browser major.minor version.")
    device: Optional[str] = Field(default=None, description="Device category, e.g. 'desktop'.")
    os: Optional[str] = Field(default=None, description="Operating system name/version.")
    mobile: bool = Field(default=False)
    touch: bool = Field(default=False)
    original: str = Field(..., description="The raw user-agent string.")


class HeaderProfile(BaseModel):
    """Aggregated view of headers, cookies, and supporting metadata."""

    id: str
    user_agent: UserAgentMetadata
    accept: str
    accept_language: str
    accept_encoding: str = "gzip, deflate, br"
    connection: str = Field(default="keep-alive")
    upgrade_insecure_requests: Optional[str] = Field(default="1")
    sec_ch_ua: Optional[str] = None
    sec_ch_ua_mobile: Optional[str] = None
    sec_ch_ua_platform: Optional[str] = None
    referer: Optional[str] = None
    sec_fetch_site: Optional[str] = None
    sec_fetch_mode: Optional[str] = None
    sec_fetch_dest: Optional[str] = None
    additional: dict[str, str] = Field(default_factory=dict)

    def headers(self) -> dict[str, str]:
        """Materialize the headers for this profile."""

        core = {
            "User-Agent": self.user_agent.original,
            "Accept": self.accept,
            "Accept-Language": self.accept_language,
            "Accept-Encoding": self.accept_encoding,
            "Connection": self.connection,
        }
        optional = {
            "Upgrade-Insecure-Requests": self.upgrade_insecure_requests,
            "Sec-CH-UA": self.sec_ch_ua,
            "Sec-CH-UA-Mobile": self.sec_ch_ua_mobile,
            "Sec-CH-UA-Platform": self.sec_ch_ua_platform,
            "Referer": self.referer,
            "Sec-Fetch-Site": self.sec_fetch_site,
            "Sec-Fetch-Mode": self.sec_fetch_mode,
            "Sec-Fetch-Dest": self.sec_fetch_dest,
        }
        enriched = {k: v for k, v in optional.items() if v is not None}
        enriched.update(self.additional)
        core.update(enriched)
        return core


class EmulatedRequest(BaseModel):
    """Represents an outgoing request with headers and optional proxy assignment."""

    headers: dict[str, str]
    cookies: dict[str, str] = Field(default_factory=dict)
    proxy: Optional[ProxyConfig] = None
    profile_id: Optional[str] = None
    retry_count: int = 0
    profile: Optional[HeaderProfile] = None


class HealthCheckResult(BaseModel):
    """Metadata captured during proxy/profile health checks."""

    ok: bool
    latency_ms: Optional[int] = None
    http_status: Optional[int] = None
    detail: Optional[str] = None


class HeaderMutator(Protocol):
    """Callable signature for header mutation hooks."""

    def __call__(
        self,
        headers: HeaderMap,
        cookies: CookiesMap,
        profile: HeaderProfile,
        context: Optional[dict[str, object]] = None,
    ) -> None:  # pragma: no cover - protocol definition
        ...


class ProxyValidator(Protocol):
    """Callable signature for external proxy validators."""

    def __call__(self, proxy: ProxyConfig) -> bool:  # pragma: no cover - protocol definition
        ...


class ProviderCallback(Protocol):
    """Signature for provider hooks that fetch external data (UAs, proxies, locales)."""

    def __call__(self) -> Iterable[Mapping[str, object]]:  # pragma: no cover - protocol definition
        ...


class AddressFamily(Enum):
    """Address family used when selecting proxies."""

    IPV4 = IPv4Address
    IPV6 = IPv6Address

    @property
    def label(self) -> str:
        return "ipv4" if self is AddressFamily.IPV4 else "ipv6"


class StickySessionKey(BaseModel):
    """Identifier used for mapping callers to persistent profiles/proxies."""

    client_id: str
    host: Optional[str] = None
    browser_family: Optional[str] = None

    @field_validator("client_id")
    @classmethod
    def _strip_client_id(cls, value: str) -> str:
        if not value:
            raise ValueError("client_id must be non-empty")
        return value.strip()


MutatorFactory = Callable[[dict[str, object]], HeaderMutator]
