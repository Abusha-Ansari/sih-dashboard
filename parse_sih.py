#!/usr/bin/env python3
"""
SIH 2026 HTML Data Parser & Analytics Generator

1. Reads 'sih2026PS.html'
2. Extracts problem statements, modal contents, and top summary statistics
3. Computes statistical distributions (by Category, Theme, Organization, Submissions)
4. Saves data to 'sih2026_data.json'
5. Updates/syncs embedded dataset in 'dashboard.html'
"""

import re
import json
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup


HTML_FILE = Path("sih2026PS.html")
OUTPUT_JSON_FILE = Path("sih2026_data.json")
DASHBOARD_HTML_FILE = Path("dashboard.html")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_portal_overview(soup: BeautifulSoup) -> dict:
    """Extract portal headline figures (Total statements, Hardware/Software counts, Themes)."""
    overview = {
        "portal_hardware_count": None,
        "portal_software_count": None,
        "portal_total_count": None,
        "portal_hardware_themes": None,
        "portal_software_themes": None
    }

    stat_boxes = soup.find_all("div", class_="statement-box")
    for box in stat_boxes:
        for hard in box.find_all("div", class_="hard"):
            h3 = hard.find("h3")
            p = hard.find("p")
            if h3 and p:
                val = int(re.sub(r"\D", "", h3.get_text())) if re.search(r"\d+", h3.get_text()) else None
                label = p.get_text().lower()
                if "hardware" in label and "theme" not in label:
                    overview["portal_hardware_count"] = val
                elif "theme" in label:
                    overview["portal_hardware_themes"] = val

        for soft in box.find_all("div", class_="soft"):
            h3 = soft.find("h3")
            p = soft.find("p")
            if h3 and p:
                val = int(re.sub(r"\D", "", h3.get_text())) if re.search(r"\d+", h3.get_text()) else None
                label = p.get_text().lower()
                if "software" in label and "theme" not in label:
                    overview["portal_software_count"] = val
                elif "theme" in label:
                    overview["portal_software_themes"] = val

    if overview["portal_hardware_count"] is not None and overview["portal_software_count"] is not None:
        overview["portal_total_count"] = overview["portal_hardware_count"] + overview["portal_software_count"]

    return overview


def parse_submissions(sub_str: str) -> dict:
    """Parse '1/500' format into current, maximum and capacity percentage."""
    sub_str = clean_text(sub_str)
    match = re.search(r"(\d+)\s*/\s*(\d+)", sub_str)
    if match:
        current = int(match.group(1))
        maximum = int(match.group(2))
        percentage = round((current / maximum * 100), 2) if maximum > 0 else 0
        return {
            "raw": sub_str,
            "current": current,
            "max": maximum,
            "percentage": percentage
        }
    return {
        "raw": sub_str,
        "current": 0,
        "max": 500,
        "percentage": 0.0
    }


def update_dashboard_embedded_data(json_payload: dict, dashboard_path: Path = DASHBOARD_HTML_FILE):
    """Sync json data directly into dashboard.html so it can be opened via double-click / file:// protocol without CORS restrictions."""
    if not dashboard_path.exists():
        return

    html_content = dashboard_path.read_text(encoding="utf-8")
    json_str = json.dumps(json_payload, ensure_ascii=False)
    
    # Check if placeholder script exists
    pattern = r'(<script id="sihDataPayload" type="application/json">)(.*?)(</script>)'
    if re.search(pattern, html_content, flags=re.DOTALL):
        updated_html = re.sub(pattern, rf'\g<1>{json_str}\g<3>', html_content, flags=re.DOTALL)
        dashboard_path.write_text(updated_html, encoding="utf-8")
        print(f"[OK] Synced embedded data to '{dashboard_path.resolve()}'.")


def parse_html_to_json(html_path: Path = HTML_FILE, json_path: Path = OUTPUT_JSON_FILE) -> dict:
    if not html_path.exists():
        raise FileNotFoundError(f"HTML source file '{html_path}' does not exist.")

    print(f"Reading '{html_path}'...")
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    portal_overview = extract_portal_overview(soup)

    table = soup.find("table", {"id": "dataTablePS"})
    if not table:
        table = soup.find("table")

    problem_statements = []

    if table:
        tbody = table.find("tbody")
        rows = tbody.find_all("tr", recursive=False) if tbody else table.find_all("tr")[1:]

        for row in rows:
            cols = row.find_all("td", recursive=False)
            if not cols or len(cols) < 5:
                continue

            s_no = clean_text(cols[0].get_text())
            organization = clean_text(cols[1].get_text())

            # Title column & Modal content
            title_td = cols[2]
            title_a = title_td.find("a")
            title = clean_text(title_a.get_text() if title_a else title_td.get_text())

            # Modal table fields
            modal_data = {}
            modal_table = title_td.find("table", {"id": "settings"})
            if not modal_table:
                modal_table = title_td.find("table")

            if modal_table:
                for m_row in modal_table.find_all("tr"):
                    th = m_row.find("th")
                    td = m_row.find("td")
                    if th and td:
                        key = clean_text(th.get_text())
                        a_tag = td.find("a")
                        href = a_tag["href"].strip() if a_tag and a_tag.has_attr("href") else ""
                        val = clean_text(td.get_text())
                        if href and href not in ["#", "", " "]:
                            modal_data[key] = {"text": val, "link": href}
                        else:
                            modal_data[key] = val

            category = clean_text(cols[3].get_text()) if len(cols) > 3 else modal_data.get("Category", "")
            ps_number = clean_text(cols[4].get_text()) if len(cols) > 4 else ""
            submission_raw = clean_text(cols[5].get_text()) if len(cols) > 5 else "0/500"
            theme = clean_text(cols[6].get_text()) if len(cols) > 6 else modal_data.get("Theme", "")
            deadline = clean_text(cols[7].get_text()) if len(cols) > 7 else ""

            ps_id = modal_data.get("Problem Statement ID", "")
            if not ps_id and ps_number:
                ps_id = re.sub(r"\D", "", ps_number)

            description = modal_data.get("Description", "")
            department = modal_data.get("Department", "")
            if not department:
                department = organization

            youtube_data = modal_data.get("Youtube Link", "")
            youtube_link = youtube_data.get("link", "") if isinstance(youtube_data, dict) else (youtube_data if youtube_data.startswith("http") else "")

            dataset_data = modal_data.get("Dataset Link", "")
            dataset_link = dataset_data.get("link", "") if isinstance(dataset_data, dict) else (dataset_data if dataset_data.startswith("http") else "")

            contact_info = modal_data.get("Contact info", "")
            if isinstance(contact_info, dict):
                contact_info = contact_info.get("text", "")

            item = {
                "s_no": int(s_no) if s_no.isdigit() else s_no,
                "ps_id": ps_id,
                "ps_number": ps_number,
                "title": title,
                "organization": organization,
                "department": department,
                "category": category,
                "theme": theme,
                "submission_stats": parse_submissions(submission_raw),
                "deadline": deadline,
                "description": description,
                "links": {
                    "youtube": youtube_link,
                    "dataset": dataset_link
                },
                "contact_info": contact_info,
                "all_modal_fields": modal_data
            }
            problem_statements.append(item)

    # Compute Statistics
    category_counts = {}
    theme_counts = {}
    org_counts = {}
    dept_counts = {}
    total_submitted_ideas = 0

    for ps in problem_statements:
        cat = ps["category"] or "Uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1

        th = ps["theme"] or "Other"
        theme_counts[th] = theme_counts.get(th, 0) + 1

        org = ps["organization"] or "Other"
        org_counts[org] = org_counts.get(org, 0) + 1

        dept = ps["department"] or "Other"
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

        total_submitted_ideas += ps["submission_stats"]["current"]

    theme_distribution = [{"name": k, "count": v} for k, v in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)]
    org_distribution = [{"name": k, "count": v} for k, v in sorted(org_counts.items(), key=lambda x: x[1], reverse=True)]
    dept_distribution = [{"name": k, "count": v} for k, v in sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)]

    data_payload = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "source_file": str(html_path),
            "total_extracted": len(problem_statements)
        },
        "portal_overview": portal_overview,
        "statistics": {
            "total_extracted": len(problem_statements),
            "total_submitted_ideas": total_submitted_ideas,
            "categories": category_counts,
            "themes": theme_distribution,
            "organizations": org_distribution,
            "departments": dept_distribution
        },
        "problem_statements": problem_statements
    }

    # Save to JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_payload, f, indent=2, ensure_ascii=False)

    print(f"[OK] Successfully extracted {len(problem_statements)} problem statements.")
    print(f"[OK] Saved structured data to '{json_path.resolve()}'.")

    # Sync embedded JSON into dashboard.html
    update_dashboard_embedded_data(data_payload)

    return data_payload


if __name__ == "__main__":
    parse_html_to_json()
