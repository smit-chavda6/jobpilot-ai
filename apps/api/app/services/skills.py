"""Skill ontology: canonical names, aliases and families (for 'adjacent' skill detection)."""

from __future__ import annotations

import re
from functools import lru_cache

# canonical -> (family, aliases)
ONTOLOGY: dict[str, tuple[str, list[str]]] = {
    "Python": ("language", ["python3", "py"]),
    "JavaScript": ("language", ["js", "ecmascript", "es6"]),
    "TypeScript": ("language", ["ts"]),
    "Java": ("language", []),
    "Go": ("language", ["golang"]),
    "Rust": ("language", []),
    "C++": ("language", ["cpp"]),
    "C#": ("language", ["csharp", "c sharp"]),
    "Kotlin": ("language", []),
    "Swift": ("language", []),
    "Ruby": ("language", []),
    "PHP": ("language", []),
    "Scala": ("language", []),
    "R": ("language", ["r language"]),
    "SQL": ("database", ["structured query language"]),
    "PostgreSQL": ("database", ["postgres", "psql"]),
    "MySQL": ("database", []),
    "MongoDB": ("database", ["mongo"]),
    "Redis": ("database", []),
    "Elasticsearch": ("database", ["elastic search", "opensearch"]),
    "Snowflake": ("data_platform", []),
    "BigQuery": ("data_platform", ["big query"]),
    "Spark": ("data_platform", ["apache spark", "pyspark"]),
    "Airflow": ("data_platform", ["apache airflow"]),
    "dbt": ("data_platform", []),
    "Kafka": ("data_platform", ["apache kafka"]),
    "Pandas": ("data_science", []),
    "NumPy": ("data_science", ["numpy"]),
    "scikit-learn": ("ml", ["sklearn", "scikit learn"]),
    "PyTorch": ("ml", ["torch"]),
    "TensorFlow": ("ml", ["tf", "keras"]),
    "XGBoost": ("ml", []),
    "Machine Learning": ("ml", ["ml"]),
    "Deep Learning": ("ml", ["dl"]),
    "NLP": ("ml", ["natural language processing"]),
    "Computer Vision": ("ml", ["cv", "opencv"]),
    "LLM": ("ml", ["llms", "large language models", "large language model"]),
    "RAG": ("ml", ["retrieval augmented generation", "retrieval-augmented generation"]),
    "Hugging Face": ("ml", ["huggingface", "transformers"]),
    "LangChain": ("ml", []),
    "MLOps": ("ml", ["ml ops"]),
    "Statistics": ("data_science", ["statistical analysis"]),
    "Data Analysis": ("data_science", ["data analytics"]),
    "Tableau": ("bi", []),
    "Power BI": ("bi", ["powerbi"]),
    "Excel": ("bi", ["ms excel", "microsoft excel"]),
    "React": ("frontend", ["react.js", "reactjs"]),
    "Vue": ("frontend", ["vue.js", "vuejs"]),
    "Angular": ("frontend", []),
    "Next.js": ("frontend", ["nextjs"]),
    "HTML": ("frontend", ["html5"]),
    "CSS": ("frontend", ["css3", "tailwind", "tailwindcss"]),
    "Node.js": ("backend", ["nodejs", "node.js"]),
    "FastAPI": ("backend", []),
    "Django": ("backend", []),
    "Flask": ("backend", []),
    "Spring": ("backend", ["spring boot", "springboot"]),
    "GraphQL": ("backend", []),
    "REST": ("backend", ["rest api", "restful", "rest apis"]),
    "Microservices": ("backend", ["microservice"]),
    "AWS": ("cloud", ["amazon web services"]),
    "GCP": ("cloud", ["google cloud", "google cloud platform"]),
    "Azure": ("cloud", ["microsoft azure"]),
    "Docker": ("devops", []),
    "Kubernetes": ("devops", ["k8s"]),
    "Terraform": ("devops", []),
    "CI/CD": ("devops", ["ci cd", "continuous integration", "github actions", "jenkins"]),
    "Linux": ("devops", ["unix"]),
    "Git": ("devops", ["github", "gitlab"]),
    "Agile": ("process", ["scrum", "kanban"]),
    "Figma": ("design", []),
    "Product Management": ("product", ["product manager"]),
    "Communication": ("soft", ["communication skills"]),
    "Leadership": ("soft", ["team leadership"]),
}

_EDU_LEVELS = {"none": 0, "high_school": 1, "associate": 2, "bachelor": 3, "master": 4, "phd": 5}


@lru_cache
def _alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for canonical, (_, aliases) in ONTOLOGY.items():
        idx[canonical.lower()] = canonical
        for a in aliases:
            idx[a.lower()] = canonical
    return idx


@lru_cache
def _scan_regex() -> re.Pattern[str]:
    # Longest terms first so "machine learning" wins over "ml"; very short ambiguous aliases
    # ("r", "go", "ts", "tf", "cv", "py", "dl", "ml") are only matched when written in upper/proper case
    # by `extract_skills` below.
    terms = sorted(_alias_index().keys(), key=len, reverse=True)
    safe = [re.escape(t) for t in terms if len(t) > 2 or t in {"c#", "go", "r", "js"}]
    return re.compile(r"(?<![\w+#.-])(" + "|".join(safe) + r")(?![\w+#&-])", re.IGNORECASE)


_SHORT_CASE_SENSITIVE = {"ML": "Machine Learning", "NLP": "NLP", "CV": "Computer Vision", "TS": "TypeScript"}
# Terms that are also common English words: only count them when written with this exact casing.
_EXACT_CASE = {"rest": "REST", "go": "Go", "r": "R", "swift": "Swift", "excel": "Excel", "spring": "Spring"}


def canonicalize(name: str) -> str | None:
    return _alias_index().get(name.strip().lower())


def normalize_skill(name: str) -> str:
    return canonicalize(name) or name.strip()


def family(skill: str) -> str | None:
    c = canonicalize(skill)
    return ONTOLOGY[c][0] if c else None


def extract_skills(text: str) -> list[str]:
    """Return canonical skills mentioned in `text`, in first-seen order."""
    found: dict[str, None] = {}
    for m in _scan_regex().finditer(text):
        term = m.group(1)
        exact = _EXACT_CASE.get(term.lower())
        if exact is not None and term != exact:
            continue
        c = canonicalize(term)
        if c:
            found.setdefault(c, None)
    for short, canonical in _SHORT_CASE_SENSITIVE.items():
        if re.search(rf"(?<![\w-]){short}(?![\w-])", text):
            found.setdefault(canonical, None)
    return list(found)


def education_rank(level: str | None) -> int | None:
    return _EDU_LEVELS.get(level) if level else None


def detect_education(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bph\.?d\b|doctorate", t):
        return "phd"
    end = r"(?=[\s,()/]|$)"
    if re.search(
        rf"\bmasters?\b|\bmaster's\b|\b(?:m\.\s?sc\.?|msc|m\.s\.|m\.\s?tech\.?|mtech|mba|m\.\s?eng\.?|meng){end}", t
    ):
        return "master"
    if re.search(
        rf"\bbachelors?\b|\bbachelor's\b|\bundergraduate degree|"
        rf"\b(?:b\.\s?sc\.?|bsc|b\.s\.|b\.\s?tech\.?|btech|b\.e\.|bca|b\.a\.){end}",
        t,
    ):
        return "bachelor"
    if re.search(r"\bassociate'?s? degree", t):
        return "associate"
    if re.search(r"high school|secondary school", t):
        return "high_school"
    return None
