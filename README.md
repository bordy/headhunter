# Job Search Agents

Four agents, run weekly, that turn a list of target companies into one brief
telling you what to apply to, how to tailor your resume, and what to learn.

| Agent | Stages | What it does |
|---|---|---|
| **Scout** | `search`, `skills` | Pulls open roles straight from each company's Greenhouse/Lever/Ashby career board, keyword-filters them, then scores fit against your resume and hard requirements. Flags jobs that are new since last week. |
| **Tailor** | `materials` | For the top matches, suggests specific resume edits (current line -> rewritten line -> which requirement it targets), and names the gaps no rewording can fix. |
| **Coach** | `coach` | Finds the skill gaps that recur across jobs worth having, and uses web search to point to real, current resources with URL, cost, and time. |
| **Consigliere** | `review` | Cross-checks the other three: fabricated resume claims, jobs that fail a hard requirement, inconsistent scores, tailor/coach contradictions. Writes the weekly brief. |

There's also an optional `interview` stage (interview prep docs for the top matches).

## Setup

```
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
```

- `config/settings.yaml` - model, resume path, thresholds for each agent
- `config/companies.yaml` - companies to search (board token comes from the careers page URL)
- `config/search_criteria.yaml` - blunt title keyword filter; keep it broad, the Scout's scoring does the real judgment
- `config/candidate_requirements.yaml` - hard requirements (salary floor, remote, relocation/sponsorship)
- `config/applications.yaml` - paste job_ids you've applied to or passed on; they drop out of future runs

## Run

```
python orchestrator.py weekly
```

Then read `data/reports/00_weekly_brief.md`. It links to everything else.

Run one stage at a time with `python orchestrator.py <stage>` (search, skills,
materials, coach, review, interview). Each reads the previous stage's output.

### What's cached week to week

- `data/seen_jobs.json` - every job ever seen, so the reports can mark `NEW`
- `data/skills_cache.json` - fit scores; only new jobs are scored each week.
  Editing your resume, requirements, or model rescores everything.
- `data/reports/04_materials/` - tailoring docs aren't regenerated for jobs that already have one.
  Delete a doc to force a fresh one (e.g. after updating your resume).
- `data/reports/archive/` - a dated copy of every weekly brief

## Schedule it weekly (Windows Task Scheduler)

`run_weekly.ps1` runs the weekly pipeline and logs to `logs\<date>.log`. To run it
every Monday at 7am:

```
schtasks /Create /TN "JobSearchAgents" /SC WEEKLY /D MON /ST 07:00 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\chris\Python\job_search_agents\run_weekly.ps1"
```

The PC has to be on (and you logged in) at that time; if it's often off, open
Task Scheduler, edit the task, and tick "Run task as soon as possible after a
scheduled start is missed".
