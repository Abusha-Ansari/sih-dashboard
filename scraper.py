import asyncio
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from parse_sih import parse_html_to_json


URL = "https://sih.gov.in/sih2026PS"

# HTML file that will continuously be overwritten
OUTPUT_FILE = Path("sih2026PS.html")

# 10 minutes
INTERVAL_SECONDS = 10 * 60


async def download_page(page):
    """Download the SIH page with all problem statements and overwrite the local HTML file."""

    print(
        f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] "
        "Fetching SIH page..."
    )

    try:
        response = await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=120_000,
        )

        if response is None:
            print("[ERROR] No HTTP response received.")
            return False

        print(f"[INFO] HTTP status: {response.status}")
        print(f"[INFO] URL: {page.url}")

        if response.status != 200:
            print(
                f"[ERROR] Server returned HTTP {response.status}."
            )
            return False

        # Wait for DataTable to initialize
        await page.wait_for_timeout(3000)

        # Expand DataTable to display ALL problem statements (-1 length)
        await page.evaluate("""() => {
            if (window.jQuery && window.jQuery.fn.dataTable && window.jQuery('#dataTablePS').length) {
                try {
                    window.jQuery('#dataTablePS').DataTable().page.len(-1).draw();
                } catch (err) {
                    console.error('Failed to expand DataTable:', err);
                }
            }
        }""")

        # Wait for all rows to render into the DOM
        await page.wait_for_timeout(3000)

        # Get the rendered HTML containing all records
        html = await page.content()

        if not html.strip():
            print("[ERROR] Received empty HTML.")
            return False

        # Write to temporary file first for atomic replacement
        temp_file = OUTPUT_FILE.with_suffix(".tmp")
        temp_file.write_text(
            html,
            encoding="utf-8",
        )

        temp_file.replace(OUTPUT_FILE)

        print(
            f"[OK] Saved {len(html):,} characters to "
            f"{OUTPUT_FILE.resolve()}"
        )

        # Automatically parse and update JSON and Dashboard
        try:
            print("[INFO] Parsing HTML into JSON and syncing dashboard...")
            parse_html_to_json()
        except Exception as pe:
            print(f"[WARN] Error during auto-parsing: {pe}")

        return True

    except Exception as e:
        print(
            f"[ERROR] {type(e).__name__}: {e}"
        )
        return False


async def main():
    print("=" * 60)
    print("SIH 2026 HTML Downloader & Auto-Parser")
    print("=" * 60)

    print(f"URL: {URL}")
    print(f"Output: {OUTPUT_FILE.resolve()}")
    print("Interval: 10 minutes")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False
        )

        context = await browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={
                "width": 1366,
                "height": 768,
            },
        )

        page = await context.new_page()

        try:
            while True:
                success = await download_page(page)

                if success:
                    print(
                        "[INFO] Existing HTML file & JSON was "
                        "successfully updated."
                    )
                else:
                    print(
                        "[INFO] Keeping the previous HTML file."
                    )

                print(
                    "[INFO] Waiting 10 minutes "
                    "before the next check..."
                )

                await asyncio.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[INFO] Stopping scraper...")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())