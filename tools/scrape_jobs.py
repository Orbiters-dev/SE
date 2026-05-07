"""
WAT Tool: Scrape remote support jobs from DailyRemote via Firecrawl markdown + regex parser.
Approach: scrape each page as markdown (fast, no LLM), parse with regex.
Output: .tmp/jobs_raw.json

Usage:
    python tools/scrape_jobs.py
    python tools/scrape_jobs.py --pages 2        # test with first 2 pages
    python tools/scrape_jobs.py --start-page 10  # resume from page 10
"""

import os
import re
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from firecrawl import FirecrawlApp  # v2 API - markdown only (fast, no LLM)

BASE_URL = "https://dailyremote.com/remote-support-jobs"
QUERY_PARAMS = "employmentType=full-time&benefits=maternity"
TOTAL_PAGES = 21
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "jobs_raw.json"
RATE_LIMIT_DELAY = 2  # seconds between page requests

# Multi-filter combos — each exposes a different slice of the job pool
MULTI_FILTER_COMBOS = [
    "employmentType=full-time&benefits=maternity",
    "employmentType=full-time",
    "employmentType=full-time&experience=0-2",
    "employmentType=full-time&experience=2-5",
    "employmentType=full-time&experience=5-10",
    "employmentType=full-time&location=united-states",
    "employmentType=full-time&location=worldwide",
    "employmentType=full-time&location=philippines",
    "employmentType=full-time&benefits=health-insurance",
    "employmentType=full-time&benefits=paid-time-off",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Markdown parsing ──────────────────────────────────────────────────────────

def parse_jobs_from_markdown(markdown: str) -> list[dict]:
    """
    Parse job listings from a DailyRemote page rendered as markdown.

    Each job block pattern:
        ## [Job Title](https://dailyremote.com/remote-job/slug)

        Full Time
        ·X hours/days ago

        🌎

        Location[💵 $salary][⭐ X-Y yrs exp][💼 Category](URL)

        Description paragraph

        [skill](URL) [skill](URL) ...

        [APPLY](URL)
    """
    jobs = []

    # Split on job header (## [...]) capturing title and URL
    job_pattern = re.compile(
        r'##\s+\[(.+?)\]\((https://dailyremote\.com/remote-job/[^\)]+)\)',
        re.MULTILINE
    )

    matches = list(job_pattern.finditer(markdown))
    if not matches:
        return []

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        job_url = match.group(2).strip()

        # Text block for this job
        block_start = match.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        block = markdown[block_start:block_end]

        job = {
            "job_title":           title,
            "company":             _extract_company(title),
            "location":            "",
            "salary":              "",
            "experience_level":    "",
            "employment_type":     "Full Time",
            "date_posted":         "",
            "description_snippet": "",
            "skills":              [],
            "category":            "Support",
            "job_url":             job_url,
        }

        lines = [l.strip() for l in block.split('\n')]

        # Date posted: line starting with ·
        date_match = re.search(r'[·•]\s*(.+?(?:ago|today|yesterday))', block, re.IGNORECASE)
        if date_match:
            job["date_posted"] = date_match.group(1).strip()

        # Info line: after globe emoji, find location/salary/experience/category
        info_line = _find_info_line(lines)
        if info_line:
            job["location"]         = _extract_location(info_line)
            job["salary"]           = _extract_salary(info_line)
            job["experience_level"] = _extract_experience(info_line)
            job["category"]         = _extract_category(info_line)

        # Description: substantial text paragraph
        job["description_snippet"] = _extract_description(lines)

        # Skills: [skill-name](dailyremote.com/remote-X-jobs) pattern
        job["skills"] = _extract_skills(block)

        if title and job_url:
            jobs.append(job)

    return jobs


def _extract_company(title: str) -> str:
    """Try to extract company from title like 'Job Title, CompanyName'."""
    sep_match = re.search(r',\s+([A-Z][^,]+)$', title)
    if sep_match:
        company = sep_match.group(1).strip()
        if len(company.split()) <= 4 and len(company) <= 40:
            return company
    return ""


def _find_info_line(lines: list[str]) -> str:
    """Find the info line (location/salary/experience) after the globe emoji."""
    globe_emojis = {'🌎', '\U0001f30e', '\U0001f30d', '\U0001f30f', '\U0001f310'}
    globe_found = False
    for line in lines:
        if any(g in line for g in globe_emojis):
            globe_found = True
            continue
        if globe_found:
            if not line:
                continue
            # The info line has experience or category markers
            has_exp = any(x in line for x in ['yrs', '⭐', '\u2b50'])
            has_cat = any(x in line for x in ['💼', '\U0001f4bc'])
            has_salary = any(x in line for x in ['💵', '\U0001f4b5', '$'])
            if has_exp or has_cat or has_salary:
                return line
            # Or just a plain location text (non-link, non-empty)
            if len(line) > 2 and not line.startswith('[') and not line.startswith('#'):
                return line
    return ""


def _extract_location(info_line: str) -> str:
    """Extract location (text before first emoji indicator)."""
    # Remove markdown links
    cleaned = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', info_line)
    # Split on money/star/briefcase emoji and take first part
    split_chars = r'[💵💰⭐💼\U0001f4b5\U0001f4b0\u2b50\U0001f4bc]'
    parts = re.split(split_chars, cleaned)
    location = parts[0].strip() if parts else ""
    # Clean up any stray $ at start
    location = re.sub(r'^\$[\d,\.]+.*', '', location).strip()
    return location


def _extract_salary(info_line: str) -> str:
    """Extract salary range."""
    patterns = [
        r'\$[\d,]+(?:\.\d+)?\s*[-\u2013]\s*\$[\d,]+(?:\.\d+)?\s*per\s+(?:hour|year|month)',
        r'\$[\d,]+(?:\.\d+)?\s*[-\u2013]\s*\$[\d,]+(?:\.\d+)?',
        r'[\d,]+(?:\.\d+)?\s*[-\u2013]\s*[\d,]+(?:\.\d+)?\s*per\s+(?:hour|year|month)',
        r'\$[\d,]+(?:\.\d+)?\s*per\s+(?:hour|year|month)',
    ]
    for pattern in patterns:
        m = re.search(pattern, info_line, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return ""


def _extract_experience(info_line: str) -> str:
    """Extract experience level."""
    m = re.search(r'(\d+[-\u2013]\d+)\s*yrs?', info_line, re.IGNORECASE)
    if m:
        return m.group(1) + " yrs"
    m2 = re.search(r'(\d+\+)\s*yrs?', info_line, re.IGNORECASE)
    if m2:
        return m2.group(1) + " yrs"
    return ""


def _extract_category(info_line: str) -> str:
    """Extract job category from 💼 label."""
    m = re.search(r'💼\s*([A-Za-z][^\[\]\(\)\n]+?)(?:\]|\()', info_line)
    if m:
        return m.group(1).strip()
    m2 = re.search(r'\[💼\s*([^\]]+)\]', info_line)
    if m2:
        return m2.group(1).strip()
    return "Support"


def _extract_description(lines: list[str]) -> str:
    """Extract description paragraph (plain prose, not info/skill/control lines)."""
    # Emojis that indicate info lines (location/salary/experience/category)
    info_emojis = {'⭐', '💵', '💼', '🌎', '\u2b50', '\U0001f4b5', '\U0001f4bc',
                   '\U0001f30e', '\U0001f30d', '\U0001f30f'}
    for line in lines:
        if not line or len(line) < 60:
            continue
        # Skip lines with info-line emojis
        if any(e in line for e in info_emojis):
            continue
        # Skip link-heavy lines (skill lists)
        link_count = len(re.findall(r'\[.+?\]\(.+?\)', line))
        if link_count > 2:
            continue
        # Skip control/navigation lines
        if line.startswith(('#', '[APPLY]', 'Full Time', 'Part Time', 'Contract')):
            continue
        if re.match(r'[·•]', line):
            continue
        # Skip lines that look like the experience/category info line
        if re.search(r'yrs?\s*exp', line, re.IGNORECASE):
            continue
        # This is likely a genuine description paragraph
        return line.strip()
    return ""


def _extract_skills(block: str) -> list[str]:
    """Extract skill tags."""
    skill_pattern = re.compile(
        r'\[([a-z0-9][a-z0-9\-]+)\]\(https://dailyremote\.com/remote-[a-z\-]+-jobs\)'
    )
    skills = skill_pattern.findall(block)
    seen = set()
    unique = []
    for s in skills:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_page_markdown(app: FirecrawlApp, url: str, retries: int = 3) -> str:
    """Scrape a page and return its markdown content."""
    for attempt in range(retries):
        try:
            result = app.scrape(
                url,
                formats=['markdown'],
                wait_for=3000,
                only_main_content=False,
                timeout=60000,
            )
            md = ""
            if hasattr(result, 'markdown'):
                md = result.markdown or ""
            elif isinstance(result, dict):
                md = result.get('markdown', '')
            logger.info(f"  -> {len(md)} chars from {url}")
            return md
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(RATE_LIMIT_DELAY * (attempt + 1))

    logger.error(f"All retries failed for {url}")
    return ""


def build_page_urls(start_page: int = 1, end_page: int = TOTAL_PAGES) -> list[str]:
    return [
        f"{BASE_URL}?{QUERY_PARAMS}&page={n}"
        for n in range(start_page, end_page + 1)
    ]


def deduplicate(jobs: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for job in jobs:
        key = job.get("job_url") or job.get("job_title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def save_output(jobs: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scraped_at": datetime.now().isoformat(),
        "total_jobs": len(jobs),
        "jobs": jobs,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(jobs)} jobs -> {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape_multi_filter(app: FirecrawlApp, pages_per_combo: int = 2) -> list[dict]:
    """Scrape multiple filter combos to maximize unique job coverage."""
    all_jobs = []
    seen_urls: set[str] = set()
    total_requests = 0

    for combo_i, combo in enumerate(MULTI_FILTER_COMBOS):
        combo_new = 0
        logger.info(f"Filter combo {combo_i + 1}/{len(MULTI_FILTER_COMBOS)}: {combo[:60]}")
        for page in range(1, pages_per_combo + 1):
            url = f"{BASE_URL}?{combo}&page={page}"
            md = scrape_page_markdown(app, url)
            total_requests += 1
            if md:
                page_jobs = parse_jobs_from_markdown(md)
                for job in page_jobs:
                    key = job.get("job_url") or job.get("job_title", "")
                    if key and key not in seen_urls:
                        seen_urls.add(key)
                        all_jobs.append(job)
                        combo_new += 1
            if page < pages_per_combo:
                time.sleep(RATE_LIMIT_DELAY)
        logger.info(f"  +{combo_new} new unique jobs (running total: {len(all_jobs)})")
        if combo_i < len(MULTI_FILTER_COMBOS) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    logger.info(f"Multi-filter complete: {total_requests} requests -> {len(all_jobs)} unique jobs")
    return all_jobs


def main():
    parser = argparse.ArgumentParser(description="Scrape remote support jobs via Firecrawl markdown")
    parser.add_argument("--pages", type=int, default=TOTAL_PAGES)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH))
    parser.add_argument("--multi-filter", action="store_true",
                        help="Use all filter combos to maximize unique job count")
    parser.add_argument("--pages-per-combo", type=int, default=2,
                        help="Pages to scrape per filter combo (default 2)")
    args = parser.parse_args()

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise EnvironmentError("FIRECRAWL_API_KEY not found. Check .env file.")

    app = FirecrawlApp(api_key=api_key)

    if args.multi_filter:
        logger.info(f"Multi-filter mode: {len(MULTI_FILTER_COMBOS)} combos x {args.pages_per_combo} pages each")
        unique_jobs = scrape_multi_filter(app, pages_per_combo=args.pages_per_combo)
    else:
        end_page = args.start_page + args.pages - 1
        urls = build_page_urls(start_page=args.start_page, end_page=end_page)
        logger.info(f"Scraping {len(urls)} pages (page {args.start_page} to {end_page})")

        all_jobs = []
        for i, url in enumerate(urls):
            logger.info(f"Page {i + 1}/{len(urls)}: {url}")
            md = scrape_page_markdown(app, url)
            if md:
                page_jobs = parse_jobs_from_markdown(md)
                logger.info(f"  Parsed: {len(page_jobs)} jobs")
                all_jobs.extend(page_jobs)
            if i < len(urls) - 1:
                time.sleep(RATE_LIMIT_DELAY)

        unique_jobs = deduplicate(all_jobs)
        logger.info(f"Total: {len(all_jobs)} | Unique: {len(unique_jobs)}")

    save_output(unique_jobs, Path(args.output))
    print(f"\nDone. {len(unique_jobs)} jobs -> {args.output}")


if __name__ == "__main__":
    main()
