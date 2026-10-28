"""Interview prep (spec §13): question bank by type, STAR scaffolds built only from verified facts,
mock-interview sessions with rubric feedback (relevance, structure, specificity, clarity)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, UnprocessableError
from app.models import Job, MockInterviewSession, ProfileFact
from app.repositories import Repo
from app.services import profile_service
from app.services.skills import extract_skills, family

BEHAVIORAL = [
    "Tell me about a time you had to learn a new technology quickly.",
    "Describe a situation where you disagreed with a teammate. How did you resolve it?",
    "Tell me about a project that did not go as planned. What did you do?",
    "Give an example of a time you improved a process or system.",
    "Describe a time you had to deliver under a tight deadline.",
    "Tell me about feedback you received and how you acted on it.",
]
GENERIC_TECHNICAL = [
    "How do you approach debugging a problem you have never seen before?",
    "How do you decide when code is ready to ship?",
    "Explain a technical concept from your work to a non-technical audience.",
]
CODING = {
    "language": "Write a function in {skill} that returns the k most frequent elements of a list. Discuss complexity.",
    "database": "Write a {skill} query that returns each customer's most recent order. How would you index it?",
    "ml": "How would you evaluate a {skill} model whose classes are heavily imbalanced?",
    "frontend": "Build a debounced search input in {skill}. How do you avoid stale responses?",
    "backend": "Design an idempotent 'create payment' endpoint in {skill}. What can go wrong?",
}
FILLERS = re.compile(r"\b(um+|uh+|like|basically|you know|kind of|sort of|actually)\b", re.I)
STAR_CUES = {
    "situation": re.compile(r"\b(when|while|at (my|the)|during|in my (role|job|internship))\b", re.I),
    "task": re.compile(r"\b(goal|task|needed to|responsible for|challenge|objective|had to)\b", re.I),
    "action": re.compile(
        r"\b(i (built|implemented|designed|wrote|created|analy[sz]ed|led|developed|set up|added|fixed|"
        r"proposed|automated|migrated|tested))\b",
        re.I,
    ),
    "result": re.compile(
        r"\b(result|resulted|outcome|so that|which (led|reduced|improved|increased)|reduced|"
        r"improved|increased|saved|as a result)\b",
        re.I,
    ),
}


def question_bank(job: Job | None, facts: list[ProfileFact]) -> dict[str, list[dict[str, Any]]]:
    skills = list(dict.fromkeys((job.required_skills or []) + (job.preferred_skills or []))) if job else []
    technical = [
        {
            "type": "technical",
            "question": f"How have you used {s} in a real project, and what trade-offs did " f"you make?",
            "skills": [s],
        }
        for s in skills[:5]
    ]
    technical += [{"type": "technical", "question": q, "skills": []} for q in GENERIC_TECHNICAL]
    coding: list[dict[str, Any]] = []
    for s in skills:
        fam = family(s)
        if fam in CODING and len(coding) < 4:
            coding.append({"type": "coding", "question": CODING[fam].format(skill=s), "skills": [s]})
    if not coding:
        coding.append(
            {
                "type": "coding",
                "question": "Implement an LRU cache and explain the data structures you chose.",
                "skills": [],
            }
        )
    projects = [f for f in facts if f.category in ("project", "experience")][:4]
    project_q = [
        {
            "type": "project",
            "question": f'Walk me through this: "{f.text[:160]}". What was hard about it?',
            "skills": profile_service.fact_skills(f),
            "fact_id": str(f.id),
        }
        for f in projects
    ]
    return {
        "technical": technical,
        "coding": coding,
        "project": project_q,
        "behavioral": [{"type": "behavioral", "question": q, "skills": []} for q in BEHAVIORAL],
    }


def star_scaffold(question: str, facts: list[ProfileFact], job_skills: list[str]) -> dict[str, Any]:
    q_skills = {s.lower() for s in extract_skills(question)} | {s.lower() for s in job_skills}
    q_words = set(re.findall(r"[a-z]{5,}", question.lower()))
    scored = []
    for f in facts:
        if f.category not in ("experience", "project", "achievement"):
            continue
        fs = {s.lower() for s in profile_service.fact_skills(f)}
        score = 2 * len(fs & q_skills) + len(q_words & set(re.findall(r"[a-z]{5,}", f.text.lower())))
        scored.append((score, f))
    scored.sort(key=lambda x: -x[0])
    picks = [f for s, f in scored[:2] if s > 0] or [f for _, f in scored[:1]]
    if not picks:
        return {
            "question": question,
            "supporting_fact_ids": [],
            "situation": None,
            "task": None,
            "action": None,
            "result": None,
            "note": "No confirmed experience or project facts yet - add some in your profile.",
        }
    f = picks[0]
    a = f.attributes or {}
    where = " at ".join(p for p in (a.get("title"), a.get("employer") or a.get("project")) if p)
    when = "–".join(p for p in (a.get("start"), a.get("end")) if p)
    numbers = re.findall(r"\d+(?:\.\d+)?\s*%?", f.text)
    return {
        "question": question,
        "supporting_fact_ids": [str(p.id) for p in picks],
        "situation": f"{where} ({when})" if where and when else where or "[Add where/when this happened]",
        "task": "[Describe the goal or problem - your facts do not state it]",
        "action": f.text,
        "result": f"Stated in your fact: {', '.join(numbers)}"
        if numbers
        else "[Add the measurable outcome if you have one - do not invent numbers]",
        "additional_evidence": [p.text for p in picks[1:]],
    }


def _score(value: float) -> int:
    return max(1, min(5, round(value)))


def rubric(question: dict[str, Any], answer: str, job_skills: list[str]) -> dict[str, Any]:
    words = re.findall(r"[A-Za-z0-9+#']+", answer)
    n = len(words)
    sentences = [s for s in re.split(r"[.!?]+", answer) if s.strip()]
    q_terms = set(re.findall(r"[a-z]{5,}", question["question"].lower())) | {
        s.lower() for s in question.get("skills", [])
    }
    a_terms = {w.lower() for w in words}
    overlap = len(q_terms & a_terms) / max(1, len(q_terms))
    skill_hits = len({s.lower() for s in extract_skills(answer)} & ({s.lower() for s in job_skills} | q_terms))
    relevance = _score(1 + 3 * min(1.0, overlap * 1.5) + min(1, skill_hits))
    star_hits = {k: bool(p.search(answer)) for k, p in STAR_CUES.items()}
    structure = _score(1 + sum(star_hits.values()) + (0 if question["type"] == "coding" else 0))
    numbers = len(re.findall(r"\d", answer))
    tools = len(extract_skills(answer))
    specificity = _score(1 + min(2, numbers) + min(2, tools))
    avg_len = n / max(1, len(sentences))
    fillers = len(FILLERS.findall(answer))
    clarity = 5.0
    if n < 40:
        clarity -= 2
    elif n > 350:
        clarity -= 1
    if avg_len > 30:
        clarity -= 1
    clarity -= min(2, fillers / 3)
    scores = {"relevance": relevance, "structure": structure, "specificity": specificity, "clarity": _score(clarity)}
    tips = []
    if relevance <= 3:
        tips.append("Address the question directly and mention the skills it asks about.")
    missing = [k for k, v in star_hits.items() if not v]
    if missing and question["type"] in ("behavioral", "project", "technical"):
        tips.append(f"Strengthen STAR structure - missing: {', '.join(missing)}.")
    if specificity <= 2:
        tips.append(
            "Add specifics from your verified experience: tools used, scale, "
            "or a measurable outcome you can stand behind."
        )
    if n < 40:
        tips.append("Expand your answer - aim for 90-200 words.")
    if fillers:
        tips.append("Reduce filler words.")
    return {
        "scores": scores,
        "overall": round(sum(scores.values()) / 4, 2),
        "tips": tips,
        "word_count": n,
        "star_elements": star_hits,
    }


async def create_session(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID | None, n: int = 5
) -> MockInterviewSession:
    job = await Repo(session, Job, user_id).get(job_id) if job_id else None
    facts = await profile_service.confirmed_facts(session, user_id)
    bank = question_bank(job, facts)
    order = ["behavioral", "technical", "project", "coding", "behavioral", "technical"]
    picks: list[dict[str, Any]] = []
    used: set[str] = set()
    idx = {k: 0 for k in bank}
    for t in order:
        pool = bank.get(t, [])
        while idx[t] < len(pool) and pool[idx[t]]["question"] in used:
            idx[t] += 1
        if idx[t] < len(pool):
            q = dict(pool[idx[t]])
            q["id"] = f"q{len(picks) + 1}"
            picks.append(q)
            used.add(q["question"])
            idx[t] += 1
        if len(picks) >= n:
            break
    row = Repo(session, MockInterviewSession, user_id).add(
        job_id=job.id if job else None, questions=picks, answers={}, feedback={}
    )
    await session.flush()
    return row


async def submit_answer(
    session: AsyncSession, user_id: uuid.UUID, s: MockInterviewSession, question_id: str, answer: str
) -> dict[str, Any]:
    if s.completed:
        raise Conflict("Session already completed", code="session_completed")
    q = next((q for q in s.questions if q["id"] == question_id), None)
    if q is None:
        raise UnprocessableError("Unknown question")
    job = await Repo(session, Job, user_id).get(s.job_id) if s.job_id else None
    job_skills = (job.required_skills or []) + (job.preferred_skills or []) if job else []
    fb = rubric(q, answer, job_skills)
    s.answers = {**s.answers, question_id: answer[:6000]}
    s.feedback = {**s.feedback, question_id: fb}
    if all(q["id"] in s.answers for q in s.questions):
        s.completed = True
        s.overall_score = round(sum(f["overall"] for f in s.feedback.values()) / len(s.feedback), 2)
    return fb


def session_dict(s: MockInterviewSession) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "job_id": str(s.job_id) if s.job_id else None,
        "questions": s.questions,
        "answers": s.answers,
        "feedback": s.feedback,
        "overall_score": s.overall_score,
        "completed": s.completed,
        "created_at": s.created_at.isoformat(),
    }
