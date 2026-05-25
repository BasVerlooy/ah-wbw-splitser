import asyncio
import logging
from typing import Optional

logger = logging.getLogger("backend.ah_auth")
from urllib.parse import parse_qs, urlparse

import httpx

CLIENT_ID = "appie-ios"
_API_BASE = "https://api.ah.nl"
_LOGIN_URL = (
    f"https://login.ah.nl/login?client_id={CLIENT_ID}"
    f"&response_type=code&redirect_uri=appie://login-exit"
)
_HEADERS = {
    "User-Agent": "Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)",
    "x-client-name": "appie-ios",
    "x-client-version": "9.28",
}

# Module-level session state (single-user app)
_state: dict = {}


async def start_login(email: str, password: str) -> dict:
    """Start the OAuth login flow. Returns {"status": "mfa_required"} or {"status": "success", ...}."""
    from playwright.async_api import async_playwright

    await _cleanup()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()

    loop = asyncio.get_running_loop()
    code_future: asyncio.Future[str] = loop.create_future()

    def _extract_appie_code(url: str) -> str:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("code", [""])[0]

    async def on_response(response):
        location = response.headers.get("location", "")
        if location.startswith("appie://"):
            code = _extract_appie_code(location)
            if code and not code_future.done():
                logger.info("Got appie:// code from response Location header")
                code_future.set_result(code)
        # Also check JSON response bodies for the auth code
        if "appie" in response.url and not code_future.done():
            try:
                body = await response.json()
                if isinstance(body, dict):
                    code = body.get("code") or body.get("authorization_code") or ""
                    if code:
                        logger.info("Got code from JSON response body")
                        code_future.set_result(code)
            except Exception:
                pass

    def on_request(request):
        url = request.url
        if url.startswith("appie://"):
            code = _extract_appie_code(url)
            if code and not code_future.done():
                logger.info("Got appie:// code from request URL")
                code_future.set_result(code)

    def on_request_failed(request):
        url = request.url
        if url.startswith("appie://"):
            code = _extract_appie_code(url)
            if code and not code_future.done():
                logger.info("Got appie:// code from failed request")
                code_future.set_result(code)

    page.on("response", on_response)
    page.on("request", on_request)
    page.on("requestfailed", on_request_failed)

    _state["pw"] = pw
    _state["browser"] = browser
    _state["page"] = page
    _state["code_future"] = code_future

    await page.goto(_LOGIN_URL, wait_until="domcontentloaded")

    # Dismiss cookie consent banner if present
    try:
        consent = page.locator("button:has-text('Accepteren'), button:has-text('Accept'), #onetrust-accept-btn-handler")
        await consent.first.click(timeout=3000)
        await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    # Submit email
    email_input = page.locator("input[type=email], input[name=email], input[name=username], input[id*=email]").first
    await email_input.wait_for(timeout=15000)
    await email_input.fill(email)
    await page.locator("button[type=submit]").first.click()
    await page.wait_for_load_state("domcontentloaded")

    # Submit password
    pw_input = page.locator("input[type=password]").first
    await pw_input.wait_for(timeout=10000)
    await pw_input.fill(password)
    await page.locator("button[type=submit]").first.click()
    await page.wait_for_load_state("domcontentloaded")

    # Check if we already got the code (no MFA)
    try:
        auth_code = await asyncio.wait_for(asyncio.shield(code_future), timeout=2.0)
        tokens = await _exchange_code(auth_code)
        await _cleanup()
        return {"status": "success", "tokens": tokens}
    except asyncio.TimeoutError:
        pass

    return {"status": "mfa_required"}


async def submit_mfa(code: str) -> dict:
    """Submit the SMS MFA code and complete the login flow."""
    page = _state.get("page")
    code_future: Optional[asyncio.Future] = _state.get("code_future")

    if not page or not code_future:
        raise ValueError("No active login session. Call start_login first.")

    # pincode-1 accepts the full 6-digit code; JS distributes it across boxes
    first_input = page.locator("#pincode-1, input[data-testid='mfa-form-code']").first
    await first_input.click()
    await first_input.press_sequentially(code, delay=80)

    # Wait for submit button to become enabled then click
    submit = page.locator("#mfa-send, button[type=submit]").first
    await submit.wait_for(state="visible", timeout=5000)
    try:
        await page.wait_for_function("el => !el.disabled", arg=await submit.element_handle(), timeout=5000)
    except Exception:
        logger.warning("Submit button still disabled — attempting force click")
    await submit.click(force=True)

    try:
        auth_code = await asyncio.wait_for(asyncio.shield(code_future), timeout=30.0)
    except asyncio.TimeoutError:
        await _cleanup()
        raise ValueError("Timed out waiting for auth code after MFA submission.")

    tokens = await _exchange_code(auth_code)
    await _cleanup()
    return {"status": "success", "tokens": tokens}


async def _exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_API_BASE}/mobile-auth/v1/auth/token",
            json={"clientId": CLIENT_ID, "code": code},
            headers={"Content-Type": "application/json", **_HEADERS},
        )
        resp.raise_for_status()
        return resp.json()


async def _cleanup():
    browser = _state.pop("browser", None)
    pw = _state.pop("pw", None)
    _state.pop("page", None)
    _state.pop("code_future", None)
    if browser:
        try:
            await browser.close()
        except Exception:
            pass
    if pw:
        try:
            await pw.stop()
        except Exception:
            pass
