# Workflow: Scrape Job Listings to Excel

## Objective
Scrape remote job listings from DailyRemote (or any paginated DailyRemote URL) and export all results to a local Excel file with 12 columns, including company name.

---

## Prerequisites
- `FIRECRAWL_API_KEY` must be set in `.env`
- Dependencies installed: `pip install -r requirements.txt`

---

## Inputs
| Input | Default | Description |
|-------|---------|-------------|
| `BASE_URL` | `https://dailyremote.com/remote-support-jobs` | The job category URL |
| `PARAMS` | `employmentType=full-time&benefits=maternity` | Filter parameters (no `page=`) |

To change the target URL or filters, edit the `BASE_URL` and `PARAMS` constants at the top of `tools/scrape_job_listings.py`.

---

## How to Run

Python is installed at `C:\Users\wjcho\AppData\Local\Programs\Python\Python312\`. Use the full path (Python is not yet in shell PATH):

```bash
# From the project root (Z:\Orbiters\ORBITERS CLAUDE\WJ Test1):
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools\scrape_job_listings.py
```

The `-X utf8` flag is required on Korean Windows (cp949 encoding) to prevent UnicodeEncodeError.

---

## What It Does

### Step 1 — Scrape listing pages
- Calls the Firecrawl API to scrape each paginated listing page
- Extracts: Job Title, URL, Employment Type, Posted, Location, Salary, Experience, Category, Description, Tags
- Stops when a page returns 0 job listings

### Step 2 — Fetch company names (parallel)
- For each job found, scrapes its individual detail page
- Runs up to 10 requests in parallel using `ThreadPoolExecutor`
- Extracts company name from the detail page

### Step 3 — Write Excel
- Saves all jobs to `.tmp/job_listings_YYYY-MM-DD_HHMMSS.xlsx`
- 12 columns with bold headers and auto-width

---

## Expected Output
`.tmp/job_listings_YYYY-MM-DD_HHMMSS.xlsx` with columns:
1. Job Title
2. Company
3. Job URL
4. Employment Type
5. Posted
6. Location
7. Salary Range
8. Experience Level
9. Category
10. Description
11. Skills / Tags
12. Apply URL

---

## Edge Cases & Notes
- **No salary**: Many listings don't include salary. The Salary Range cell will be blank — this is expected.
- **No company profile**: Some jobs don't have a DailyRemote company page. The Company cell will be blank.
- **Pagination**: The tool auto-detects the last page by checking for 0 results. No manual page count needed.
- **Rate limits**: Firecrawl has a concurrency limit (check with `firecrawl --status`). If you hit limits, reduce `MAX_WORKERS` in the script.
- **Filters**: The `benefits=maternity` filter is applied server-side — all returned jobs include maternity benefits.

---

## Lessons Learned
- DailyRemote listing pages contain heavy navigation content (country dropdowns, benefits checkboxes) before the job blocks. Job blocks start after the applied filter summary line.
- Company names only appear on individual job detail pages, not listing pages.
- The Firecrawl markdown output uses `## [Title](URL)` as reliable job block delimiters.
- DailyRemote has infinite pagination — the site returns the same jobs for any `?page=N` beyond the last real page. The tool detects this by tracking seen job URLs and stopping when a full page is all duplicates.
- Run Python with `-X utf8` flag to avoid `UnicodeEncodeError` on Korean Windows (cp949 encoding).
