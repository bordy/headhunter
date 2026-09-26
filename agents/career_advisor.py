"""Agent 2 (Tailor): Career Advisor.

For the top-matching jobs, produces tailored resume edit suggestions (and,
optionally, a cover letter draft) that speak to that specific job posting.

Skips jobs below min_score_for_tailoring, and skips jobs that already have a
tailoring doc from a previous week, so a weekly run only pays for new work.
"""

from common.claude_client import generate_text
from common.io_utils import load_json, load_text, load_yaml, resolve, save_text

JOBS_IN = "data/jobs_found.json"
GAP_IN = "data/skills_gap.json"
OUT_DIR = "data/reports/04_materials"

SYSTEM_TEMPLATE = """You are a career advisor who helps candidates tailor their application \
materials to a specific job, without ever fabricating experience they don't have. Every resume \
suggestion and every cover letter claim must be traceable to something already in the resume \
below - reframe and re-prioritize freely, but do not invent skills, employers, titles, or results.

## Candidate resume

{resume}
"""

USER_TEMPLATE = """Tailor application materials for this role.

## Job
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

## Skills analysis for this candidate
Matched skills: {matched_skills}
Missing skills: {missing_skills}
Verdict: {summary}

## Output format (Markdown)
Start with `# {title} at {company}`.

## Resume tailoring suggestions
A bulleted list of specific edits. For each, quote the current resume line, then give the \
rewritten line, then one short sentence on which job requirement it targets. Cover: which bullets \
to reorder or lead with, which to reword to use this posting's language, what to cut to make room, \
and whether the headline/summary should change. Note if any matched_skills aren't currently \
visible enough on the resume and should be surfaced.

## Gaps you cannot paper over
The missing skills that no honest rewording fixes - so the candidate knows what an interviewer \
will probe.
{cover_letter_section}"""

COVER_LETTER_SECTION = """
## Cover letter draft
A complete, ready-to-send cover letter (3-4 paragraphs) addressed generically ("Dear Hiring \
Manager") that connects the candidate's actual background to this specific role and company. \
Do not use generic filler - reference concrete details from the job description.
"""


def run() -> list:
    settings = load_yaml("config/settings.yaml")
    model = settings["model"]
    resume = load_text(settings["resume_path"])
    top_n = settings.get("top_n_jobs", 5)
    min_score = settings.get("min_score_for_tailoring", 60)
    cover_letter_section = COVER_LETTER_SECTION if settings.get("write_cover_letters", False) else ""

    jobs_by_id = {j["id"]: j for j in load_json(JOBS_IN, default=[])}
    matches = load_json(GAP_IN, default=[])
    if not matches:
        raise RuntimeError(f"No skills analysis found in {GAP_IN} - run the skills_analysis agent first.")

    system_text = SYSTEM_TEMPLATE.format(resume=resume)

    top_matches = [m for m in matches if m["match_score"] >= min_score][:top_n]
    written = []
    for m in top_matches:
        job = jobs_by_id.get(m["job_id"])
        if job is None:
            continue
        out_path = f"{OUT_DIR}/{job['id']}.md"
        if resolve(out_path).exists():
            written.append(out_path)
            continue

        user_content = USER_TEMPLATE.format(
            title=job["title"],
            company=job["company"],
            location=job["location"],
            description=job["description"][:6000],
            matched_skills=", ".join(m["matched_skills"]) or "none",
            missing_skills=", ".join(m["missing_skills"]) or "none",
            summary=m["summary"],
            cover_letter_section=cover_letter_section,
        )
        doc = generate_text(model, system_text, user_content)
        save_text(out_path, doc)
        written.append(out_path)

    return written


if __name__ == "__main__":
    paths = run()
    print(f"{len(paths)} tailoring doc(s) in {OUT_DIR}/")
