"""Seed Alex's resume into resume_profiles + resume_sections with embeddings.

Idempotent: if Alex's user + v1 profile already exist, this clears the old
sections and re-inserts (so re-running picks up text edits).

Run from backend/:  venv/bin/python -m scripts.seed_resume
"""
import asyncio
from typing import Any

from sqlalchemy import delete, select

from db import SessionLocal
from models import ResumeProfile, ResumeSection, User
from services.embedding import embed_text

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
ALEX_NAME = "Xuanye Zeng"
PROFILE_LABEL = "Master Resume"
PROFILE_VERSION = 1


SECTIONS: list[dict[str, Any]] = [
    # --- projects ---
    {
        "section_type": "project",
        "content_json": {
            "title": "End-to-End ML Feature Pipeline & Training System",
            "dates": "Feb 2026 - Apr 2026",
            "identity": "ML Pipeline",
            "bullets": [
                "Transformed raw datasets into training-ready features at scale by designing a distributed ML pipeline using Python and Ray.",
                "Selected optimal model architecture from 3 candidates (logistic regression, random forest, MLP) via 60 Ray Tune trials, achieving F1 of 0.63 and ROC AUC of 0.84.",
                "Improved recall on skewed churn labels by building a PyTorch training path with balanced class weighting, benchmarked against sklearn baselines.",
                "Ensured reproducible model selection across experiments by implementing config-driven training with threshold analysis and per-run artifact tracking.",
                "Caught 2 schema inconsistencies before training by implementing data quality validation and drift monitoring; containerized with Docker and automated via GitHub Actions CI/CD.",
            ],
        },
    },
    {
        "section_type": "project",
        "content_json": {
            "title": "CloudScale Inventory Management System",
            "dates": "Oct 2025 - Dec 2025",
            "identity": "CloudScale",
            "bullets": [
                "Architected a fault-tolerant microservices system in Go with separate API, worker, and data layers, enabling independent scaling and isolated failure handling per service.",
                "Reduced read latency by 30% by implementing asynchronous order event processing using SQS and caching with ElastiCache Redis.",
                "Isolated performance bottlenecks across 3 microservices with API gateway, rate limiting, and distributed tracing for end-to-end observability.",
                "Deployed containerized services to Amazon ECS and EKS with Auto Scaling and automated CI/CD via GitHub Actions.",
            ],
        },
    },
    {
        "section_type": "project",
        "content_json": {
            "title": "Full-Stack Food Ordering App",
            "dates": "Jun 2025 - Aug 2025",
            "identity": "Food Ordering",
            "bullets": [
                "Ensured thread-safe stock deductions using Redis transactions and distributed locks, achieving zero overselling under simulated concurrent load of 500+ requests per second.",
                "Integrated Elasticsearch for search and implemented an event-driven pipeline using RabbitMQ, decoupling order creation from downstream processing to handle traffic spikes.",
                "Built a full-stack ordering platform using Spring Boot and React, featuring secure JWT authentication and role-based access control.",
                "Deployed containerized services on AWS with Docker and automated CI/CD workflows using GitHub Actions.",
            ],
        },
    },
    # --- internship experience ---
    {
        "section_type": "experience",
        "content_json": {
            "company": "Beijing Jingdiao Group",
            "role": "Software & Automation Engineer Intern",
            "location": "Beijing, China",
            "dates": "Jul 2024 - Aug 2024",
            "bullets": [
                "Cut equipment downtime by 33% with a C-based sensor fault detection workflow that identified failure patterns from diagnostic logs and automated recovery.",
                "Reduced unplanned stops by 15% by developing a pre-run safety validation script that verified sensor calibration and machine state before job execution.",
                "Improved manufacturing precision by 30% through G-code control algorithm optimization for automated equipment.",
                "Optimized equipment motion paths using Python data analysis, improving production efficiency by 10%.",
            ],
        },
    },
    {
        "section_type": "experience",
        "content_json": {
            "company": "Engineering Center, University of Science and Technology Beijing",
            "role": "Software & Hardware Engineer Intern",
            "location": "Beijing, China",
            "dates": "Mar 2023 - Jul 2023",
            "bullets": [
                "Reduced cycle time by 12% through performance profiling of CNC control algorithms for complex mechanical structures.",
                "Accelerated parametric testing across 30+ design configurations by engineering a modular SolidWorks and MATLAB simulation system for mechanical automation.",
                "Cut setup time by 20% by developing G-code programs that optimized precision milling and prototyping workflows.",
            ],
        },
    },
    # --- education ---
    {
        "section_type": "education",
        "content_json": {
            "school": "Northeastern University - Seattle",
            "degree": "Master of Science, Computer Science",
            "location": "Seattle, WA",
            "dates": "Sep 2025 - Present",
            "details": ["GPA: 4.0/4.0"],
        },
    },
    {
        "section_type": "education",
        "content_json": {
            "school": "University of Science and Technology Beijing",
            "degree": "Bachelor of Engineering, Mechanical Engineering",
            "location": "Beijing, China",
            "dates": "Sep 2021 - Jul 2025",
            "details": [
                "People's Scholarship (Nov. 2023)",
                "Second Prize in the Student Research Training Program",
            ],
        },
    },
    # --- skills ---
    {
        "section_type": "skill",
        "content_json": {
            "category": "Programming Languages",
            "items": ["Python", "Java", "Go", "C/C++", "SQL", "JavaScript", "TypeScript", "HTML/CSS"],
        },
    },
    {
        "section_type": "skill",
        "content_json": {
            "category": "Cloud & Infrastructure",
            "items": ["AWS (ECS, EKS, SQS, RDS, S3)", "Docker", "Kubernetes", "CI/CD (GitHub Actions)"],
        },
    },
    {
        "section_type": "skill",
        "content_json": {
            "category": "Backend & Data",
            "items": ["REST API design", "FastAPI", "Spring Boot", "PostgreSQL", "Redis", "NoSQL", "RabbitMQ", "Elasticsearch"],
        },
    },
    {
        "section_type": "skill",
        "content_json": {
            "category": "ML & AI",
            "items": ["PyTorch", "Ray", "LangChain", "pandas", "NumPy"],
        },
    },
    {
        "section_type": "skill",
        "content_json": {
            "category": "Core",
            "items": ["Data Structures & Algorithms", "Object-Oriented Design", "Distributed Systems", "Microservice Architecture"],
        },
    },
]


def section_to_text(section_type: str, content: dict[str, Any]) -> str:
    """Flatten a section into a single string for embedding."""
    if section_type == "project":
        return f"{content['title']}. " + " ".join(content["bullets"])
    if section_type == "experience":
        return (
            f"{content['role']} at {content['company']}. "
            + " ".join(content["bullets"])
        )
    if section_type == "education":
        details = " ".join(content.get("details", []))
        return f"{content['degree']} at {content['school']}. {details}"
    if section_type == "skill":
        return f"{content['category']}: {', '.join(content['items'])}"
    raise ValueError(f"unknown section_type: {section_type}")


async def seed() -> None:
    async with SessionLocal() as s:
        # 1. Upsert user
        existing_user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one_or_none()
        if existing_user is None:
            user = User(email=ALEX_EMAIL, name=ALEX_NAME)
            s.add(user)
            await s.flush()
            print(f"INSERT user {ALEX_EMAIL}")
        else:
            user = existing_user
            print(f"reuse user {ALEX_EMAIL} (id={user.id})")

        # 2. Upsert profile (per user + version)
        existing_profile = (
            await s.execute(
                select(ResumeProfile).where(
                    ResumeProfile.user_id == user.id,
                    ResumeProfile.version == PROFILE_VERSION,
                )
            )
        ).scalar_one_or_none()
        if existing_profile is None:
            profile = ResumeProfile(
                user_id=user.id, version=PROFILE_VERSION, label=PROFILE_LABEL
            )
            s.add(profile)
            await s.flush()
            print(f"INSERT profile v{PROFILE_VERSION} '{PROFILE_LABEL}'")
        else:
            profile = existing_profile
            # Clear existing sections to re-seed cleanly
            await s.execute(
                delete(ResumeSection).where(ResumeSection.profile_id == profile.id)
            )
            print(f"reuse profile v{PROFILE_VERSION}; cleared existing sections")

        # 3. Insert sections with embeddings
        for i, section in enumerate(SECTIONS, 1):
            text = section_to_text(section["section_type"], section["content_json"])
            print(f"  [{i:2d}/{len(SECTIONS)}] embed {section['section_type']:11s} | {text[:80]}...")
            vec = embed_text(text)
            s.add(
                ResumeSection(
                    profile_id=profile.id,
                    section_type=section["section_type"],
                    content_json=section["content_json"],
                    embedding=vec,
                )
            )

        await s.commit()
        print(f"done: {len(SECTIONS)} sections inserted for {ALEX_EMAIL} / profile v{PROFILE_VERSION}")


if __name__ == "__main__":
    asyncio.run(seed())
