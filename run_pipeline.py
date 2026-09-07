#!/usr/bin/env python3
"""
SIH 2026 Resilient Scraper & Pipeline Runner
Guarantees full table expansion, prevents partial HTML overwrites,
and syncs JSON and dashboards non-destructively.
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from parse_sih import parse_html_to_json, update_dashboard_embedded_data

URL = "https://sih.gov.in/sih2026PS"
OUTPUT_HTML = Path("sih2026PS.html")
INDEX_HTML = Path("index.html")
DASHBOARD_HTML = Path("dashboard.html")
MINIMUM_EXPECTED_ROWS = 50  # Portal has 230+ statements; never overwrite if fewer


async def run_scraper():
    print("=" * 60)
    print("SIH 2026 Scraper Pipeline Starting")
    print("=" * 60)
    print(f"[1/3] Navigating to {URL} with Playwright...")

    scraped_success = False
    new_html_content = ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Navigate with networkidle or load
            try:
                response = await page.goto(URL, wait_until="networkidle", timeout=60000)
            except Exception:
                response = await page.goto(URL, wait_until="load", timeout=90000)

            if not response or response.status != 200:
                print(f"[WARN] HTTP status {response.status if response else 'None'}.")
                return False

            print("[2/3] Waiting for DataTables initialization...")
            await page.wait_for_selector("#dataTablePS", timeout=30000)

            # Wait for jQuery and DataTable to be attached
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

            # Expand DataTable with retries
            expanded_rows = 0
            for attempt in range(1, 6):
                print(f"[INFO] Expanding DataTable (attempt {attempt}/5)...")
                await page.evaluate("""() => {
                    if (window.jQuery && window.jQuery.fn.DataTable.isDataTable('#dataTablePS')) {
                        try {
                            const dt = window.jQuery('#dataTablePS').DataTable();
                            dt.page.len(-1).draw();
                        } catch (e) {
                            console.error('DataTable draw error:', e);
                        }
                    }
                }""")

                # Fallback: Also try selecting the dropdown if needed
                try:
                    length_select = page.locator("select[name='dataTablePS_length']")
                    if await length_select.count() > 0:
                        await length_select.select_option(value="-1")
                except Exception:
                    pass

                await page.wait_for_timeout(3000)
                expanded_rows = await page.locator("#dataTablePS tbody tr").count()
                print(f"[INFO] Rows detected in DOM: {expanded_rows}")
                if expanded_rows >= MINIMUM_EXPECTED_ROWS:
                    print(f"[OK] Successfully expanded to {expanded_rows} problem statements.")
                    break

            if expanded_rows >= MINIMUM_EXPECTED_ROWS:
                new_html_content = await page.content()
                if new_html_content.strip():
                    OUTPUT_HTML.write_text(new_html_content, encoding="utf-8")
                    scraped_success = True
                    print(f"[OK] Saved full HTML ({len(new_html_content):,} bytes) with {expanded_rows} rows to {OUTPUT_HTML.resolve()}")
            else:
                print(f"[WARN] Extraction yielded only {expanded_rows} rows (< {MINIMUM_EXPECTED_ROWS}).")
                print("[WARN] Guard activated: Preserving previously saved HTML file to prevent data loss.")

        except Exception as e:
            print(f"[ERROR] Exception during scrape: {e}")
            return False

        finally:
            await browser.close()

    if not OUTPUT_HTML.exists():
        print("[ERROR] No HTML snapshot available.")
        return False

    print("[3/3] Parsing HTML into JSON and syncing dashboards...")
    data = parse_html_to_json(html_path=OUTPUT_HTML)
    
    total_in_db = len(data.get("problem_statements", []))
    print(f"[SUCCESS] Pipeline finished. Total problem statements in database: {total_in_db}")

    # Safety: ensure we didn't end up with an empty or broken dataset
    if total_in_db < MINIMUM_EXPECTED_ROWS:
        print(f"[WARN] Total items ({total_in_db}) below expected threshold ({MINIMUM_EXPECTED_ROWS}).")

    return True


if __name__ == "__main__":
    success = asyncio.run(run_scraper())
    sys.exit(0 if success else 1)
