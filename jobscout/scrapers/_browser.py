"""Shared Playwright helper for bot-protected portals (Indeed, Dice).

Lazy browser launch — first call opens chromium, subsequent calls reuse it.
Caller MUST call close() when done (handled by main.py's finally block).
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright, Browser, Playwright, BrowserContext


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BrowserSession:
    """One headless chromium per scraper instance. Reused across queries."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None

    def _ensure(self) -> BrowserContext:
        if self._ctx is not None:
            return self._ctx
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx = self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        self._ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return self._ctx

    def fetch(self, url: str, wait_for: str | None = None,
              timeout_ms: int = 30000) -> str:
        ctx = self._ensure()
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=timeout_ms)
                except Exception:
                    pass
            else:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return page.content()
        finally:
            page.close()

    def close(self):
        if self._ctx:
            self._ctx.close()
            self._ctx = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None
