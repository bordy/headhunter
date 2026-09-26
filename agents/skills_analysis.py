"""Agent 1 (Scout), part 2: Fit scoring.

Scores every job found by the job-search step against the resume and the
candidate's hard requirements. Writes data/skills_gap.json (sorted best-first)
plus a Markdown report.

Scores are cached in data/skills_cache.json, so a weekly run only pays to score
jobs it hasn't seen before. Changing the resume, the requirements, or the
prompt below invalidates the cache and rescores everything.
"""

import hashlib
from collections import Counter

import yaml

from common.claude_client import parse_structured
from common.io_utils import load_json, load_text, load_yaml, save_json, save_text
from common.models import SkillsAnalysisBatch

JOBS_IN = "data/jobs_found.json"
GAP_OUT = "data/skills_gap.json"
CACHE_PATH = "data/skills_cache.json"
REPORT_OUT = "data/reports/02_skills_analysis.md"

SYSTEM_TEMPLATE = """You are a career-focused skills analyst. You compare a candidate's resume \
against job postings and produce an honest, specific fit assessment.

For each job, return:
- match_score: 0-100, how well the resume matches the job's actual requirements, AND how well the \
job fits the candidate's hard requirements below. A job that fits the skills but fails a hard \
requirement (wrong role type, no remote/relocation path, salary clearly below floor, clearly the \
wrong seniority such as an internship) should score low (20 or under) even with strong skill \
overlap - a great skills match in the wrong job is not a good match.
- matched_skills: skills/experience from the resume that satisfy the job's requirements
- missing_skills: specific skills/qualifications the job requires that the resume does not show. \
Use short, reusable names (e.g. "Snowflake", "SaaS revenue modeling", "CPA") so the same gap is \
named the same way across jobs.
- hard_requirement_flags: each hard requirement the posting fails or leaves unclear, as a short \
phrase quoting the posting where possible. Empty list if it clearly passes all of them.
- summary: 2-3 sentences covering (a) overall fit verdict, (b) role-type fit (does this match the \
candidate's primary or secondary focus, or neither), and (c) what the posting text says - or doesn't \
say - about remote work, salary, and visa sponsorship, since those aren't negotiable for this search

Be specific and critical - do not inflate match scores to be encouraging. If the posting doesn't \
mention salary or sponsorship, say so plainly rather than guessing.

## Candidate hard requirements

{requirements}

## Candidate resume

{resume}
"""

USER_TEMPLATE = """Analyze these {count} job postings against the resume in your system prompt. \
Return one JobMatch per job, using the exact job_id given for each.

{jobs_block}
"""


def _job_block(job: dict) -> str:
    return (
        f"### job_id: {job['id']}\n"
        f"Title: {job['title']}\n"
        f"Company: {job['company']}\n"
        f"Location: {job['location']}\n"
        f"Description:\n{job['description'][:6000]}\n"
    )


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _requirements_block(req: dict) -> str:
    lines = [
        f"- Primary focus: {req.get('primary_focus', '').strip()}",
        f"- Secondary/fallback focus: {req.get('secondary_focus', '').strip()}",
        f"- Minimum salary: ${req.get('salary_floor_usd', 0):,} USD (or equivalent)",
        f"- Remote required: {req.get('remote_required', False)}",
    ]
    if req.get("relocation_ok"):
        regions = ", ".join(req.get("relocation_regions", [])) or "anywhere"
        lines.append(f"- Open to relocating to: {regions} (only if the employer can sponsor a visa)")
        lines.append(f"- Sponsorship required if relocating: {req.get('sponsorship_required_if_relocating', True)}")
    else:
        lines.append("- Not open to relocation")
    return "\n".join(lines)


def run() -> list:
    settings = load_yaml("config/settings.yaml")
    model = settings["model"]
    resume = load_text(settings["resume_path"])
    batch_size = settings.get("skills_analysis_batch_size", 8)
    requirements = load_yaml("config/candidate_requirements.yaml")

    jobs = load_json(JOBS_IN, default=[])
    if not jobs:
        raise RuntimeError(f"No jobs found in {JOBS_IN} - run the job_search agent first.")

    system_text = SYSTEM_TEMPLATE.format(requirements=_requirements_block(requirements), resume=resume)
    fingerprint = hashlib.sha1(
        (system_text + model + yaml.safe_dump(requirements, sort_keys=True)).encode("utf-8")
    ).hexdigest()

    cache = load_json(CACHE_PATH, default={})
    cached = cache.get("matches", {}) if cache.get("fingerprint") == fingerprint else {}

    to_score = [j for j in jobs if j["id"] not in cached]
    print(f"Scoring {len(to_score)} job(s); reusing {len(jobs) - len(to_score)} cached score(s).")
    for batch in _chunk(to_score, batch_size):
        jobs_block = "\n".join(_job_block(j) for j in batch)
        user_content = USER_TEMPLATE.format(count=len(batch), jobs_block=jobs_block)
        result = parse_structured(model, system_text, user_content, SkillsAnalysisBatch)
        for m in result.matches:
            cached[m.job_id] = m.model_dump()
        # Save after each batch so a crash mid-run doesn't lose paid-for work.
        save_json(CACHE_PATH, {"fingerprint": fingerprint, "matches": cached})

    # Only report on jobs that are still open this week and not already handled.
    handled = load_yaml("config/applications.yaml") or {}
    skip_ids = set(handled.get("applied") or []) | set(handled.get("not_interested") or [])
    open_ids = {j["id"] for j in jobs} - skip_ids
    all_matches = [m for job_id, m in cached.items() if job_id in open_ids]
    all_matches.sort(key=lambda m: m["match_score"], reverse=True)
    save_json(GAP_OUT, all_matches)

    jobs_by_id = {j["id"]: j for j in jobs}
    _write_report(all_matches, jobs_by_id)
    return all_matches


def _write_report(matches: list, jobs_by_id: dict) -> None:
    lines = ["# Skills Analysis Report", ""]

    missing_counter = Counter()
    for m in matches:
        missing_counter.update(m["missing_skills"])

    if missing_counter:
        lines.append("## Most common skill gaps across all jobs")
        for skill, count in missing_counter.most_common(10):
            lines.append(f"- **{skill}** - missing from {count} job(s)")
        lines.append("")

    lines.append("## Jobs ranked by match")
    for m in matches:
        job = jobs_by_id.get(m["job_id"], {})
        new_tag = " `NEW`" if job.get("is_new") else ""
        lines.append(f"### {job.get('title', '?')} at {job.get('company', '?')} - {m['match_score']}/100{new_tag}")
        lines.append(f"_{m['summary']}_")
        lines.append("")
        lines.append(f"- Link: {job.get('url', '?')}")
        lines.append(f"- Matched: {', '.join(m['matched_skills']) or 'none'}")
        lines.append(f"- Missing: {', '.join(m['missing_skills']) or 'none'}")
        if m["hard_requirement_flags"]:
            lines.append(f"- Flags: {'; '.join(m['hard_requirement_flags'])}")
        lines.append("")

    save_text(REPORT_OUT, "\n".join(lines))


if __name__ == "__main__":
    matches = run()
    print(f"Analyzed {len(matches)} jobs. See {REPORT_OUT}")
