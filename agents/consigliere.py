"""Agent 4 (Consigliere): Cross-check and weekly brief.

Reads everything the other agents produced this week and checks it against the
resume, the hard requirements, and each other:
  - Scout: are high scores justified? Did a job that fails a hard requirement slip through?
  - Tailor: does any suggested edit claim something the resume doesn't support?
  - Coach: do the recommended resources target the gaps in the jobs worth applying to?
  - Across agents: does the tailor paper over a gap the coach says is real, or vice versa?

Then writes the one document to read each week: data/reports/00_weekly_brief.md
(plus a dated copy in data/reports/archive/).
"""

from datetime import datetime

from common.claude_client import parse_structured
from common.io_utils import load_json, load_text, load_yaml, resolve, save_text
from common.models import ConsigliereReview

JOBS_IN = "data/jobs_found.json"
GAP_IN = "data/skills_gap.json"
TAILOR_DIR = "data/reports/04_materials"
COACH_IN = "data/reports/05_coach.md"
BRIEF_OUT = "data/reports/00_weekly_brief.md"
ARCHIVE_DIR = "data/reports/archive"

SYSTEM_TEMPLATE = """You are the candidate's consigliere: a skeptical, loyal chief of staff who \
reviews the work of three assistants before it reaches the candidate. Your job is to catch \
mistakes and contradictions, then tell the candidate plainly what to do this week.

The assistants:
- scout: found jobs and scored their fit against the resume and hard requirements
- tailor: suggested resume edits for the top jobs
- coach: recommended learning resources for recurring skill gaps

Check for, at minimum:
1. Fabrication (high severity): a tailor edit that claims a skill, tool, metric, title, or result \
not supported by the resume. Quote the offending line.
2. Hard-requirement misses (high): a job scored well or recommended despite failing a hard \
requirement (location/remote, salary, sponsorship, seniority, role type).
3. Scoring inconsistencies (medium): similar jobs scored very differently, or a score that \
contradicts its own summary.
4. Cross-agent contradictions (medium): the tailor rewording around a gap the coach says needs \
real learning, the coach recommending study for something the resume already shows, or coaching \
aimed at jobs you are telling the candidate to skip.
5. Coach quality (low-medium): resources without URLs, costs, or time estimates, or with obvious \
low leverage.

Only report real problems - an empty issues list is fine. For each, give a concrete fix.

apply_this_week: the jobs (by job_id) you would actually apply to this week, best first, max \
{max_apply}. Only jobs you are confident pass the hard requirements. It's fine to list fewer, or \
none.
skip: high-scoring jobs you are deliberately NOT recommending, and why.

brief: the Markdown weekly brief the candidate will read (no top-level heading - one is added). \
Lead with the bottom line in 2-3 sentences, then: what to apply to and in what order, which \
tailoring docs to trust (and which edits to ignore), the one or two coaching priorities worth \
time this week, and anything you'd change about the search itself (companies, keywords, \
requirements). Be direct and brief; the candidate will click through to the detailed reports.

## Candidate hard requirements
{requirements}

## Candidate resume
{resume}
"""


def _jobs_section(matches: list, jobs_by_id: dict, limit: int) -> str:
    blocks = []
    for m in matches[:limit]:
        job = jobs_by_id.get(m["job_id"], {})
        blocks.append(
            f"### job_id: {m['job_id']}{' (NEW this week)' if job.get('is_new') else ''}\n"
            f"{job.get('title', '?')} at {job.get('company', '?')} - {job.get('location', '?')}\n"
            f"Score: {m['match_score']}/100\n"
            f"Summary: {m['summary']}\n"
            f"Flags: {'; '.join(m['hard_requirement_flags']) or 'none'}\n"
            f"Missing: {', '.join(m['missing_skills']) or 'none'}\n"
            f"Posting excerpt:\n{job.get('description', '')[:2500]}\n"
        )
    return "\n".join(blocks)


def _tailor_section(matches: list) -> str:
    blocks = []
    for m in matches:
        path = resolve(f"{TAILOR_DIR}/{m['job_id']}.md")
        if path.exists():
            blocks.append(f"### Tailor doc for job_id: {m['job_id']}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(blocks) or "(no tailoring docs this week)"


def run() -> str:
    settings = load_yaml("config/settings.yaml")
    model = settings["model"]
    resume = load_text(settings["resume_path"])
    requirements = load_text("config/candidate_requirements.yaml")

    jobs_by_id = {j["id"]: j for j in load_json(JOBS_IN, default=[])}
    matches = load_json(GAP_IN, default=[])
    if not matches:
        raise RuntimeError(f"No skills analysis found in {GAP_IN} - run the skills_analysis agent first.")
    coach_report = load_text(COACH_IN) if resolve(COACH_IN).exists() else "(no coach report this week)"

    system_text = SYSTEM_TEMPLATE.format(
        requirements=requirements,
        resume=resume,
        max_apply=settings.get("max_apply_per_week", 5),
    )
    user_content = (
        "Review this week's work.\n\n"
        f"# Scout: top jobs by score\n{_jobs_section(matches, jobs_by_id, settings.get('consigliere_job_limit', 15))}\n\n"
        f"# Tailor output\n{_tailor_section(matches)}\n\n"
        f"# Coach output\n{coach_report}\n"
    )
    review = parse_structured(model, system_text, user_content, ConsigliereReview, max_tokens=32000, effort="high")

    brief = _render(review, jobs_by_id)
    save_text(BRIEF_OUT, brief)
    save_text(f"{ARCHIVE_DIR}/{datetime.now().strftime('%Y-%m-%d')}_brief.md", brief)
    return BRIEF_OUT


def _job_link(job_id: str, jobs_by_id: dict) -> str:
    job = jobs_by_id.get(job_id)
    if job is None:
        return f"`{job_id}` (unknown job)"
    return f"[{job['title']} at {job['company']}]({job['url']})"


def _render(review: ConsigliereReview, jobs_by_id: dict) -> str:
    lines = [f"# Weekly Job Search Brief - {datetime.now().strftime('%Y-%m-%d')}", "", review.brief, ""]

    lines.append("## Apply this week")
    if review.apply_this_week:
        for i, p in enumerate(review.apply_this_week, 1):
            tailor = resolve(f"{TAILOR_DIR}/{p.job_id}.md")
            tailor_link = f" - [tailoring notes](04_materials/{p.job_id}.md)" if tailor.exists() else ""
            lines.append(f"{i}. {_job_link(p.job_id, jobs_by_id)}{tailor_link}  \n   {p.why}")
    else:
        lines.append("_Nothing this week._")
    lines.append("")

    if review.skip:
        lines.append("## Deliberately skipped")
        for p in review.skip:
            lines.append(f"- {_job_link(p.job_id, jobs_by_id)} - {p.why}")
        lines.append("")

    lines.append("## Issues found in the agents' work")
    if review.issues:
        order = {"high": 0, "medium": 1, "low": 2}
        for issue in sorted(review.issues, key=lambda x: order.get(x.severity, 3)):
            where = f" ({_job_link(issue.job_id, jobs_by_id)})" if issue.job_id else ""
            lines.append(f"- **{issue.severity.upper()} / {issue.agent}**{where}: {issue.problem}  \n  _Fix:_ {issue.fix}")
    else:
        lines.append("_None - the other agents' output checked out._")
    lines.append("")

    lines.append("## Detailed reports")
    lines.append("- [All jobs found](01_job_search.md)")
    lines.append("- [Fit scores](02_skills_analysis.md)")
    lines.append("- [Coaching plan](05_coach.md)")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(f"Wrote {run()}")
