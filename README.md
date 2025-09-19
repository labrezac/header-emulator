# header-emulator
HTML scraping header emulator with proxy rotation.

## Quick Start

1. Create a profile file (e.g., `data/profiles.json`) with user-agent fingerprints.
2. Instantiate the emulator and make requests:

```python
from header_emulator import HeaderEmulator

emulator = HeaderEmulator.from_profile_file("data/profiles.json")

with emulator.session() as session:
    response = session.request("GET", "https://example.com", with_proxy=True)
    print(response.status_code)
```

## Dynamic Sources

```python
from header_emulator import (
    HeaderEmulator,
    proxies_from_proxyscrape,
    user_agents_from_intoli,
)
from header_emulator.providers.locales import LocaleProvider
from header_emulator.types import LocaleProfile

ua_provider, locale = user_agents_from_intoli(limit=50)
proxy_provider = proxies_from_proxyscrape()

emulator = HeaderEmulator(
    user_agents=ua_provider,
    locales=LocaleProvider([locale]),
    proxies=proxy_provider,
)

headers, proxy = emulator.next_headers(with_proxy=True)
```

## Proxy Utilities

- `ProxyProvider.from_env()` / `.from_file()` / `.from_csv()` load proxies from different sources.
- `load_proxies_from_lines()`, `deduplicate_proxies()`, and `shuffled_proxies()` help clean and randomize a proxy pool.
- `healthcheck_proxies()` runs quick checks before scraping.

## Notes

- `data/profiles.json` is ignored by git so you can store private fingerprints locally.
- Install optional dependencies (`requests`, `PyYAML`) if you use dynamic feeds or YAML profiles.
- Use the proxy tools to load/clean/check your proxy list before scraping.
