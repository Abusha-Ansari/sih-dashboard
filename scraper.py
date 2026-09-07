import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from parse_sih import parse_html_to_json, update_dashboard_embedded_data


URL = "https://sih.gov.in/sih2026PS"
OUTPUT_FILE = Path("sih2026PS.html")
INDEX_HTML = Path("index.html")
DASHBOARD_HTML = Path("dashboard.html")
INTERVAL_SECONDS = 10 * 60
MINIMUM_EXPECTED_ROWS = 50


def auto_git_push():
    """Automatically commits and pushes new changes to GitHub/Vercel if running locally."""
    try:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            print("[GIT] Changes detected. Committing and pushing to GitHub...")
            subprocess.run(["git", "add", "sih2026_data.json", "sih2026PS.html", "dashboard.html", "index.html"], check=True)
            subprocess.run(["git", "commit", "-m", "chore(auto-update): sync SIH 2026 dataset [local sync]"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("[GIT] Successfully pushed updates to GitHub & Vercel!")
        else:
            print("[GIT] No dataset changes to commit.")
    except Exception as e:
        print(f"[GIT-NOTE] Auto-push skipped: {e}")


async def download_page(page):
    """Download the SIH page with all problem statements and overwrite the local HTML file safely."""

    print(
        f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] "
        "Fetching SIH page..."
    )

    try:
        try:
            response = await page.goto(URL, wait_until="networkidle", timeout=60000)
        except Exception:
            response = await page.goto(URL, wait_until="load", timeout=90000)

        if response is None:
            print("[ERROR] No HTTP response received.")
            return False

        print(f"[INFO] HTTP status: {response.status}")
        print(f"[INFO] URL: {page.url}")

        if response.status != 200:
            print(f"[ERROR] Server returned HTTP {response.status}.")
            return False

        await page.wait_for_selector("#dataTablePS", timeout=30000)

        for _ in range(15):
            is_dt = await page.evaluate("""() => {
                return Boolean(window.jQuery && 
                               window.jQuery.fn && 
                               window.jQuery.fn.dataTable && 
                               window.jQuery.fn.DataTable.isDataTable('#dataTablePS'));
            }""")
            if is_dt:
                break
            await page.wait_for_timeout(1000)

        expanded_rows = 0
        for attempt in range(1, 6):
            print(f"[INFO] Expanding DataTable (attempt {attempt}/5)...")
            await page.evaluate("""() => {
                if (window.jQuery && window.jQuery.fn.DataTable.isDataTable('#dataTablePS')) {
                    try {
                        window.jQuery('#dataTablePS').DataTable().page.len(-1).draw();
                    } catch (e) {
                        console.error('DataTable draw error:', e);
                    }
                }
            }""")

            try:
                length_select = page.locator("select[name='dataTablePS_length']")
                if await length_select.count() > 0:
                    await length_select.select_option(value="-1")
            except Exception:
                pass

            await page.wait_for_timeout(3000)
            expanded_rows = await page.locator("#dataTablePS tbody tr").count()
            if expanded_rows >= MINIMUM_EXPECTED_ROWS:
                print(f"[OK] Successfully expanded to {expanded_rows} problem statements.")
                break

        if expanded_rows < MINIMUM_EXPECTED_ROWS:
            print(f"[WARN] Only {expanded_rows} rows found (< {MINIMUM_EXPECTED_ROWS}). Preserving existing HTML.")
            parse_html_to_json()
            return True

        html = await page.content()
        if not html.strip():
            print("[ERROR] Received empty HTML.")
            return False

        temp_file = OUTPUT_FILE.with_suffix(".tmp")
        temp_file.write_text(html, encoding="utf-8")
        temp_file.replace(OUTPUT_FILE)

        print(f"[OK] Saved {len(html):,} characters with {expanded_rows} rows to {OUTPUT_FILE.resolve()}")

        try:
            print("[INFO] Parsing HTML into JSON and syncing dashboards...")
            data = parse_html_to_json()
            update_dashboard_embedded_data(data, DASHBOARD_HTML)
            update_dashboard_embedded_data(data, INDEX_HTML)
            # Auto-sync to GitHub/Vercel
            auto_git_push()
        except Exception as pe:
            print(f"[WARN] Error during auto-parsing: {pe}")

        return True

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return False


async def main():
    print("=" * 60)
    print("SIH 2026 Resilient HTML Downloader & Auto-Parser")
    print("=" * 60)

    print(f"URL: {URL}")
    print(f"Output: {OUTPUT_FILE.resolve()}")
    print("Interval: 10 minutes")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = await browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            while True:
                success = await download_page(page)
                if success:
                    print("[INFO] Synchronization cycle completed.")
                else:
                    print("[INFO] Preserving existing database.")

                print("[INFO] Waiting 10 minutes before next check...")
                await asyncio.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[INFO] Stopping scraper...")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())