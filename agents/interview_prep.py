"""Agent 3: Interview Prep.

For the top-matching jobs (by skills-analysis match_score), generates a
tailored interview prep document: likely questions, resume-grounded talking
points, topics to brush up on, and questions to ask the interviewer.
"""

from common.claude_client import generate_text
from common.io_utils import load_json, load_text, load_yaml, save_text

JOBS_IN = "data/jobs_found.json"
GAP_IN = "data/skills_gap.json"
OUT_DIR = "data/reports/03_interview_prep"

SYSTEM_TEMPLATE = """You are an experienced interview coach. You write specific, actionable \
interview prep documents grounded in the candidate's real resume and the actual job posting - \
never generic advice.

## Candidate resume

{resume}
"""

USER_TEMPLATE = """Write an interview prep document in Markdown for this role.

## Job
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

## Skills analysis for this candidate
Match score: {match_score}/100
Matched skills: {matched_skills}
Missing skills: {missing_skills}
Verdict: {summary}

## Required sections (use these as Markdown ## headings)
1. Likely interview questions - a mix of technical and behavioral questions specific to this \
role's actual requirements, not generic ones
2. Talking points from the resume - for each of the candidate's most relevant experiences, a \
STAR-format (Situation/Task/Action/Result) note they could give as an answer
3. Topics to brush up on - tied directly to the missing_skills above, with what to review
4. Smart questions to ask the interviewer - specific to this company/role, not boilerplate

Output only the Markdown document, starting with a level-1 heading with the job title and company.
"""


def run() -> list:
    settings = load_yaml("config/settings.yaml")
    model = settings["model"]
    resume = load_text(settings["resume_path"])
    top_n = settings.get("top_n_jobs", 5)

    jobs_by_id = {j["id"]: j for j in load_json(JOBS_IN, default=[])}
    matches = load_json(GAP_IN, default=[])
    if not matches:
        raise RuntimeError(f"No skills analysis found in {GAP_IN} - run the skills_analysis agent first.")

    system_text = SYSTEM_TEMPLATE.format(resume=resume)

    top_matches = matches[:top_n]
    written = []
    for m in top_matches:
        job = jobs_by_id.get(m["job_id"])
        if job is None:
            continue

        user_content = USER_TEMPLATE.format(
            title=job["title"],
            company=job["company"],
            location=job["location"],
            description=job["description"][:6000],
            match_score=m["match_score"],
            matched_skills=", ".join(m["matched_skills"]) or "none",
            missing_skills=", ".join(m["missing_skills"]) or "none",
            summary=m["summary"],
        )
        doc = generate_text(model, system_text, user_content, max_tokens=4096)
        out_path = f"{OUT_DIR}/{job['id']}.md"
        save_text(out_path, doc)
        written.append(out_path)

    return written


if __name__ == "__main__":
    paths = run()
    print(f"Wrote {len(paths)} interview prep docs to {OUT_DIR}/")
