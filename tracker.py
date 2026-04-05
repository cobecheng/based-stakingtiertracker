import asyncio
import os
import logging
from datetime import datetime
from playwright.async_api import async_playwright
import httpx

# ── Config (edit these or use environment variables) ──────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "YOUR_CHAT_ID_HERE")
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "120"))   # 2 minutes
TARGET_URL         = "https://basedfoundation.com/genesis"
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

last_state: bool | None = None   # True = available, False = full/greyed


async def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    if resp.status_code != 200:
        log.error("Telegram error: %s", resp.text)
    else:
        log.info("Telegram message sent.")


async def check_stake_availability(page) -> bool:
    """
    Returns True if the Based Tier staking input is ENABLED (available).
    Strategy:
      1. Navigate to the Stake tab.
      2. Find the middle staking card (Based tier).
      3. Check whether its amount input is disabled.
    Adjust selectors below if the page structure differs.
    """
    await page.goto(TARGET_URL, wait_until="networkidle", timeout=60_000)

    # Click the "Stake" tab if the page has tabs
    try:
        stake_tab = page.get_by_role("tab", name="Stake")
        if await stake_tab.count():
            await stake_tab.click()
            await page.wait_for_timeout(2000)
    except Exception:
        pass  # Already on the right view, or no tab present

    # ── Selector strategy ────────────────────────────────────────────────────
    # We look for an input inside a card/section that contains the text
    # "Based" (the middle tier).  This covers most React/Vue staking UIs.
    # If you inspect the page and see a more specific class, add it below.
    #
    # Priority 1 – input inside a container mentioning "Based"
    based_input = page.locator(
        ":is(div, section, article):has-text('Based') input[type='number'], "
        ":is(div, section, article):has-text('Based') input[placeholder]"
    ).first

    count = await based_input.count()
    if count == 0:
        log.warning("Could not find the Based tier input — page structure may have changed.")
        return False  # Treat as unavailable so we don't spam

    is_disabled = await based_input.is_disabled()
    log.info("Based tier input disabled=%s", is_disabled)
    return not is_disabled   # available = NOT disabled


async def monitor() -> None:
    global last_state
    log.info("Starting Based Foundation Genesis tracker…")
    log.info("Target: %s | Interval: %ss", TARGET_URL, CHECK_INTERVAL_SEC)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        while True:
            try:
                available = await check_stake_availability(page)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if available and last_state is not True:
                    msg = (
                        "🟢 <b>Based Tier Staking — OPEN!</b>\n"
                        f"Allocation is now available.\n"
                        f"👉 <a href='{TARGET_URL}'>{TARGET_URL}</a>\n"
                        f"🕐 {ts}"
                    )
                    await send_telegram(msg)
                    log.info("STATE CHANGE → AVAILABLE")

                elif not available and last_state is True:
                    msg = (
                        "🔴 <b>Based Tier Staking — FULL</b>\n"
                        "The allocation input is greyed out again.\n"
                        f"🕐 {ts}"
                    )
                    await send_telegram(msg)
                    log.info("STATE CHANGE → FULL / GREYED OUT")

                else:
                    log.info("No state change (available=%s)", available)

                last_state = available

            except Exception as exc:
                log.error("Check failed: %s", exc)

            await asyncio.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(monitor())
