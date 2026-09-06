#!/usr/bin/env python3
"""
Single-run pipeline for GitHub Actions or Cloud Cron.
1. Launches headless browser
2. Expands DataTable and saves 'sih2026PS.html'
3. Runs 'parse_sih.py' to generate 'sih2026_data.json' and sync 'index.html' / 'dashboard.html'
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


async def run_scraper():
    print(f"[1/3] Navigating to {URL} with Playwright...")
    scraped_fresh_html = False
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            response = await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
            if not response or response.status != 200:
                print(f"[WARN] HTTP status {response.status if response else 'None'}; using last saved HTML snapshot if available.")
            else:
                await page.wait_for_timeout(3000)

                print("[2/3] Expanding DataTable to show all entries...")
                await page.evaluate("""() => {
                    if (window.jQuery && window.jQuery.fn.dataTable && window.jQuery('#dataTablePS').length) {
                        try {
                            window.jQuery('#dataTablePS').DataTable().page.len(-1).draw();
                        } catch (e) {
                            console.error('DataTable len error', e);
                        }
                    }
                }""")
                await page.wait_for_timeout(3000)

                html = await page.content()
                if html.strip():
                    OUTPUT_HTML.write_text(html, encoding="utf-8")
                    scraped_fresh_html = True
                    print(f"[OK] Saved HTML ({len(html):,} bytes) to {OUTPUT_HTML.resolve()}")
                else:
                    print("[WARN] Empty HTML received; using last saved HTML snapshot if available.")

        finally:
            await browser.close()

    if not OUTPUT_HTML.exists() or not OUTPUT_HTML.read_text(encoding="utf-8").strip():
        print("[ERROR] No usable HTML snapshot is available to parse.")
        return False

    if not scraped_fresh_html:
        print(f"[INFO] Continuing with cached HTML snapshot: {OUTPUT_HTML.resolve()}")

    print("[3/3] Parsing HTML into JSON and updating dashboards...")
    data = parse_html_to_json(html_path=OUTPUT_HTML)
    
    # Sync both dashboard.html and index.html if present
    update_dashboard_embedded_data(data, DASHBOARD_HTML)
    if INDEX_HTML.exists():
        update_dashboard_embedded_data(data, INDEX_HTML)
    
    print("[SUCCESS] Pipeline completed successfully!")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_scraper())
    sys.exit(0 if success else 1)
