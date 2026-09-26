"""Agent 3 (Coach): Skill-gap resources.

Looks across the scored jobs for the gaps that keep coming up in roles the
candidate actually wants, then uses web search to point to real, current
resources (courses, certifications, projects) to close them. Gaps are weighted
by match score, so a gap in a 80/100 job counts more than one in a 25/100 job.
"""

from collections import defaultdict

from common.claude_client import generate_text
from common.io_utils import load_json, load_text, load_yaml, save_text

JOBS_IN = "data/jobs_found.json"
GAP_IN = "data/skills_gap.json"
REPORT_OUT = "data/reports/05_coach.md"

SYSTEM_TEMPLATE = """You are a pragmatic career coach for a job seeker. You recommend the \
smallest set of learning investments that will most improve their odds on the jobs they are \
actually targeting - not a generic curriculum.

Rules:
- Use web search to confirm every resource you recommend exists and is current. Give its real \
URL, cost (or "free"), and a realistic time commitment. Never recommend a resource you have not \
verified in this session.
- Prefer resources a hiring manager would recognize (official certifications, well-known \
courses, vendor training) and, where a gap is better closed by showing than by studying, a \
concrete portfolio project instead.
- Separate real gaps from presentation gaps: if the resume already implies the skill and the \
problem is that it isn't stated, say "resume wording, not learning" and move on - that is the \
resume tailor's job, not yours.
- Rank by leverage: how many target jobs it unlocks, weighted by how good those jobs are, \
divided by the time it takes. Be willing to say a gap is not worth closing.

## Candidate hard requirements
{requirements}

## Candidate resume
{resume}
"""

USER_TEMPLATE = """Here are the skill gaps from this week's scored jobs, weighted by match score \
(only jobs scoring {min_score}+ are counted). Each gap lists the jobs it appeared in.

{gaps_block}

Write a Markdown report, starting with `# Weekly Coaching Plan`, with these sections:

## Top priorities (max {max_priorities})
For each: the gap, why it matters (which jobs), the recommended resource(s) with URL, cost, and \
time, and what "done" looks like (e.g. certificate earned, project on GitHub, a line you can add \
to the resume).

## Presentation gaps (no learning needed)
Gaps the resume already supports but doesn't state.

## Not worth it right now
Gaps you'd skip, and why.
"""


def _gaps_block(matches: list, jobs_by_id: dict, min_score: int) -> str:
    weight = defaultdict(int)
    where = defaultdict(list)
    for m in matches:
        if m["match_score"] < min_score:
            continue
        job = jobs_by_id.get(m["job_id"], {})
        for gap in m["missing_skills"]:
            weight[gap] += m["match_score"]
            where[gap].append(f"{job.get('title', '?')} at {job.get('company', '?')} ({m['match_score']})")

    lines = []
    for gap in sorted(weight, key=weight.get, reverse=True)[:30]:
        lines.append(f"- **{gap}** (weight {weight[gap]}): {'; '.join(where[gap])}")
    return "\n".join(lines)


def run() -> str:
    settings = load_yaml("config/settings.yaml")
    model = settings["model"]
    resume = load_text(settings["resume_path"])
    requirements = load_text("config/candidate_requirements.yaml")
    min_score = settings.get("min_score_for_coaching", 40)

    jobs_by_id = {j["id"]: j for j in load_json(JOBS_IN, default=[])}
    matches = load_json(GAP_IN, default=[])
    if not matches:
        raise RuntimeError(f"No skills analysis found in {GAP_IN} - run the skills_analysis agent first.")

    gaps_block = _gaps_block(matches, jobs_by_id, min_score)
    if not gaps_block:
        report = f"# Weekly Coaching Plan\n\nNo jobs scored {min_score}+ this week, so there are no gaps to coach on.\n"
        save_text(REPORT_OUT, report)
        return REPORT_OUT

    system_text = SYSTEM_TEMPLATE.format(requirements=requirements, resume=resume)
    user_content = USER_TEMPLATE.format(
        gaps_block=gaps_block,
        min_score=min_score,
        max_priorities=settings.get("coach_max_priorities", 4),
    )
    report = generate_text(
        model,
        system_text,
        user_content,
        effort="high",
        web_search_max_uses=settings.get("coach_web_search_max_uses", 10),
    )
    save_text(REPORT_OUT, report)
    return REPORT_OUT


if __name__ == "__main__":
    print(f"Wrote {run()}")
