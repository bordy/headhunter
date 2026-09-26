"""Fetchers for public company career-page job board APIs.

These are the public, unauthenticated JSON APIs that Greenhouse, Lever, and
Ashby expose for embedding job listings on a company's careers page - not
scrapes of LinkedIn/Indeed, and not subject to their ToS restrictions.
"""

import html
import re
from typing import List

import requests

from common.io_utils import job_id

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"</(p|li|h[1-6]|div|ul|ol)>|<br\s*/?>", re.IGNORECASE)
_WS_RE = re.compile(r"\n{3,}")
TIMEOUT = 15


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    # Greenhouse returns entity-escaped HTML ("&lt;p&gt;"), so unescape before stripping tags.
    text = html.unescape(raw)
    text = _BLOCK_END_RE.sub("\n", text)
    text = html.unescape(_TAG_RE.sub("", text))
    text = _WS_RE.sub("\n\n", text)
    return text.strip()


def fetch_greenhouse(company: str, board_token: str) -> List[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    resp = requests.get(url, params={"content": "true"}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        title = j.get("title", "")
        location = (j.get("location") or {}).get("name", "")
        departments = j.get("departments") or []
        jobs.append({
            "id": job_id(company, title, location),
            "company": company,
            "title": title,
            "location": location,
            "url": j.get("absolute_url", ""),
            "description": strip_html(j.get("content", "")),
            "department": departments[0]["name"] if departments else None,
        })
    return jobs


def fetch_lever(company: str, board_token: str) -> List[dict]:
    url = f"https://api.lever.co/v0/postings/{board_token}"
    resp = requests.get(url, params={"mode": "json"}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        title = j.get("text", "")
        categories = j.get("categories") or {}
        location = categories.get("location", "")
        description_parts = [j.get("descriptionPlain") or strip_html(j.get("description", ""))]
        for section in j.get("lists") or []:
            description_parts.append(section.get("text", ""))
            description_parts.append(strip_html(section.get("content", "")))
        jobs.append({
            "id": job_id(company, title, location),
            "company": company,
            "title": title,
            "location": location,
            "url": j.get("hostedUrl", ""),
            "description": "\n\n".join(p for p in description_parts if p),
            "department": categories.get("team"),
        })
    return jobs


def fetch_ashby(company: str, board_token: str) -> List[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        title = j.get("title", "")
        location = j.get("location", "")
        description = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", ""))
        jobs.append({
            "id": job_id(company, title, location),
            "company": company,
            "title": title,
            "location": location,
            "url": j.get("jobUrl", ""),
            "description": description,
            "department": j.get("department"),
        })
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_company_jobs(company: str, board_type: str, board_token: str) -> List[dict]:
    fetcher = FETCHERS.get(board_type)
    if fetcher is None:
        raise ValueError(f"Unknown board_type '{board_type}' for company '{company}'")
    return fetcher(company, board_token)
