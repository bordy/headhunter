from typing import List, Optional
from pydantic import BaseModel


class JobPosting(BaseModel):
    id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    department: Optional[str] = None


class JobMatch(BaseModel):
    job_id: str
    match_score: int  # 0-100
    matched_skills: List[str]
    missing_skills: List[str]
    hard_requirement_flags: List[str]  # e.g. "on-site Bengaluru, no remote", "salary range tops out at $120k"
    summary: str


class SkillsAnalysisBatch(BaseModel):
    matches: List[JobMatch]


class ReviewIssue(BaseModel):
    severity: str  # "high" | "medium" | "low"
    agent: str  # which agent's output the issue is in: scout, tailor, coach
    job_id: Optional[str] = None
    problem: str
    fix: str


class ReviewPriority(BaseModel):
    job_id: str
    why: str


class ConsigliereReview(BaseModel):
    issues: List[ReviewIssue]
    apply_this_week: List[ReviewPriority]
    skip: List[ReviewPriority]
    brief: str  # Markdown weekly brief for the candidate
