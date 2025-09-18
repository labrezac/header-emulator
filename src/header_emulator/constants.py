"""Static data derived from common browser fingerprints and ZenRows guidance."""

from __future__ import annotations

from collections.abc import Mapping

DESKTOP_ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
)
MOBILE_ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
)
API_ACCEPT_HEADER = "application/json, text/javascript, */*;q=0.01"

DEFAULT_ACCEPT_ENCODINGS = ["gzip", "deflate", "br"]

# Weighted Accept-Language headers inspired by ZenRows' header rotation article.
ACCEPT_LANGUAGE_WEIGHTS: Mapping[str, float] = {
    "en-US,en;q=0.9": 0.42,
    "en-GB,en;q=0.8": 0.12,
    "es-ES,es;q=0.9,en;q=0.6": 0.08,
    "fr-FR,fr;q=0.9,en;q=0.6": 0.07,
    "de-DE,de;q=0.9,en;q=0.6": 0.06,
    "it-IT,it;q=0.9,en;q=0.6": 0.05,
    "pt-BR,pt;q=0.9,en;q=0.6": 0.05,
    "ja-JP,ja;q=0.9,en;q=0.5": 0.04,
    "ko-KR,ko;q=0.9,en;q=0.5": 0.03,
    "ru-RU,ru;q=0.9,en;q=0.6": 0.03,
    "zh-CN,zh;q=0.9,en;q=0.6": 0.03,
    "ar-SA,ar;q=0.9,en;q=0.5": 0.02,
}

# Chrome and Firefox security headers that the ZenRows guide recommends preserving.
SEC_FETCH_HEADERS_DOCUMENT = {
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

SEC_FETCH_HEADERS_XHR = {
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# Representative referers to make navigation patterns more realistic.
COMMON_REFERERS = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://news.ycombinator.com/",
    "https://www.reddit.com/",
    "https://twitter.com/",
]

# Default header template IDs used across builders and tests.
DEFAULT_PROFILE_IDS = {
    "desktop_chrome": "desktop_chrome_112",
    "desktop_firefox": "desktop_firefox_116",
    "mobile_android": "mobile_chrome_android_110",
    "mobile_ios": "mobile_safari_ios_16",
}

# Sample Chrome UA brand strings adapted from modern desktop fingerprints.
SEC_CH_UA_BRANDS = {
    "desktop_chrome": '"Not.A/Brand";v="8", "Chromium";v="112", "Google Chrome";v="112"',
    "desktop_firefox": '"Not.A/Brand";v="99", "Mozilla";v="116"',
    "desktop_safari": '"Not.A/Brand";v="99", "Safari";v="16"',
    "mobile_android": '"Not.A/Brand";v="8", "Chromium";v="110", "Google Chrome";v="110"',
    "mobile_ios": '"Not.A/Brand";v="99", "AppleWebKit";v="605", "Mobile Safari";v="16"',
}


__all__ = [
    "ACCEPT_LANGUAGE_WEIGHTS",
    "API_ACCEPT_HEADER",
    "COMMON_REFERERS",
    "DEFAULT_ACCEPT_ENCODINGS",
    "DEFAULT_PROFILE_IDS",
    "DESKTOP_ACCEPT_HEADER",
    "MOBILE_ACCEPT_HEADER",
    "SEC_CH_UA_BRANDS",
    "SEC_FETCH_HEADERS_DOCUMENT",
    "SEC_FETCH_HEADERS_XHR",
]
