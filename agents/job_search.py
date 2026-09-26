"""Agent 1 (Scout), part 1: Job Search.

Fetches current openings from each company's public Greenhouse/Lever/Ashby
job board API, filters them against config/search_criteria.yaml, and writes
the results to data/jobs_found.json plus a readable Markdown report.

Remembers every job it has seen in data/seen_jobs.json, so each weekly run
can flag which postings are new since last time.
"""

from datetime import datetime, timezone

from common.io_utils import load_json, load_yaml, save_json, save_text
from common.job_boards import fetch_company_jobs

JOBS_OUT = "data/jobs_found.json"
SEEN_PATH = "data/seen_jobs.json"
REPORT_OUT = "data/reports/01_job_search.md"


def _matches(job: dict, criteria: dict) -> bool:
    title = job["title"].lower()
    location = (job.get("location") or "").lower()

    titles = [t.lower() for t in criteria.get("titles") or []]
    if titles and not any(t in title for t in titles):
        return False

    excludes = [e.lower() for e in criteria.get("exclude_keywords") or []]
    if any(e in title for e in excludes):
        return False

    locations = [l.lower() for l in criteria.get("locations") or []]
    if locations and not any(l in location for l in locations):
        return False

    return True


def run() -> list:
    companies_cfg = load_yaml("config/companies.yaml")
    criteria = load_yaml("config/search_criteria.yaml")

    all_jobs = []
    per_company_counts = {}
    errors = []

    for company in companies_cfg.get("companies", []):
        name = company["name"]
        try:
            fetched = fetch_company_jobs(name, company["board_type"], company["board_token"])
        except Exception as exc:  # noqa: BLE001 - one bad board shouldn't stop the run
            errors.append(f"{name}: {exc}")
            continue

        matched = [j for j in fetched if _matches(j, criteria)]
        per_company_counts[name] = (len(fetched), len(matched))
        all_jobs.extend(matched)

    seen = load_json(SEEN_PATH, default={})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for job in all_jobs:
        job["is_new"] = job["id"] not in seen
        job["first_seen"] = seen.setdefault(job["id"], today)
    save_json(SEEN_PATH, seen)

    save_json(JOBS_OUT, all_jobs)
    _write_report(all_jobs, per_company_counts, errors)
    return all_jobs


def _write_report(jobs: list, per_company_counts: dict, errors: list) -> None:
    lines = [
        "# Job Search Report",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        f"**{len(jobs)} matching jobs** found across {len(per_company_counts)} companies "
        f"({sum(j['is_new'] for j in jobs)} new since the last run).",
        "",
    ]

    if errors:
        lines.append("## Errors")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("## By company")
    for name, (total, matched) in per_company_counts.items():
        lines.append(f"- **{name}**: {matched} matched / {total} total open roles")
    lines.append("")

    lines.append("## Matching jobs")
    by_company = {}
    for job in jobs:
        by_company.setdefault(job["company"], []).append(job)

    for company, company_jobs in by_company.items():
        lines.append(f"### {company}")
        for job in company_jobs:
            new_tag = " `NEW`" if job["is_new"] else ""
            lines.append(f"- **{job['title']}** ({job['location']}){new_tag} - [{job['id']}]({job['url']})")
        lines.append("")

    save_text(REPORT_OUT, "\n".join(lines))


if __name__ == "__main__":
    jobs = run()
    print(f"Found {len(jobs)} matching jobs. See {REPORT_OUT}")
