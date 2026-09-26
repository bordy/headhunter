"""Runs the job-search pipeline.

The weekly pipeline is four agents:
  Scout       search -> skills   find jobs on company career boards, score fit
  Tailor      materials          resume edits for the top matches
  Coach       coach              real resources for recurring skill gaps
  Consigliere review             cross-check everything, write the weekly brief

Usage:
    python orchestrator.py weekly      # the four agents above, in order
    python orchestrator.py all         # weekly + interview prep
    python orchestrator.py <stage>     # one stage: search, skills, materials, coach, review, interview
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from agents import career_advisor, coach, consigliere, interview_prep, job_search, skills_analysis

STAGES = {
    "search": job_search.run,
    "skills": skills_analysis.run,
    "materials": career_advisor.run,
    "coach": coach.run,
    "review": consigliere.run,
    "interview": interview_prep.run,
}
WEEKLY = ["search", "skills", "materials", "coach", "review"]
ALL = [*WEEKLY, "interview"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "stage",
        choices=[*STAGES, "weekly", "all"],
        help="Which stage to run, 'weekly' for the four-agent pipeline, or 'all' to add interview prep.",
    )
    args = parser.parse_args()

    stages = {"weekly": WEEKLY, "all": ALL}.get(args.stage, [args.stage])

    for stage in stages:
        print(f"\n=== Running: {stage} ===")
        try:
            STAGES[stage]()
        except Exception as exc:  # noqa: BLE001 - surface the failure and stop the pipeline
            print(f"Stage '{stage}' failed: {exc}", file=sys.stderr)
            sys.exit(1)

    print("\nDone. Start with data/reports/00_weekly_brief.md")


if __name__ == "__main__":
    main()
