#!/usr/bin/env python3
"""Seed Microsoft exams with unique question pools (55+ per exam)."""

import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.database import Base, SessionLocal, engine
from app.services.import_service import MICROSOFT_EXAMS, import_questions_json, sync_microsoft_catalog

CORE_TEMPLATES = {
    "AZ-900": [
        ("Describe cloud concepts", "What is a characteristic of public cloud?", "Elastic scaling of resources"),
        ("Describe cloud concepts", "Which cloud model combines public and private clouds?", "Hybrid cloud"),
        ("Describe Azure architecture and services", "Which Azure service provides serverless compute?", "Azure Functions"),
        ("Describe Azure management and governance", "Which tool provides unified Azure management?", "Azure Portal"),
    ],
    "AZ-104": [
        ("Manage Azure identities and governance", "Which role allows full access to all resources?", "Owner"),
        ("Implement and manage storage", "Which redundancy protects against regional failure?", "GRS"),
        ("Deploy and manage Azure compute resources", "Which are valid VM disk types?", "Premium SSD and Standard HDD"),
        ("Implement and manage virtual networking", "What connects on-premises networks to Azure?", "VPN Gateway or ExpressRoute"),
    ],
    "AI-900": [
        ("Describe Artificial Intelligence workloads and considerations", "What is machine learning?", "Training models from data"),
        ("Describe features of generative AI workloads on Azure", "Which Azure service provides OpenAI models?", "Azure OpenAI Service"),
        ("Describe features of computer vision workloads on Azure", "Which service analyzes images?", "Azure AI Vision"),
        ("Describe features of Natural Language Processing workloads on Azure", "Which service provides language understanding?", "Azure AI Language"),
    ],
    "SC-900": [
        ("Describe the concepts of security, compliance, and identity", "What does Zero Trust assume?", "Verify explicitly, least privilege"),
        ("Describe the capabilities of Microsoft Entra", "Microsoft Entra ID is used for:", "Identity and access management"),
        ("Describe the capabilities of Microsoft security solutions", "Which service protects against threats?", "Microsoft Defender"),
    ],
    "MS-102": [
        ("Deploy and manage a Microsoft 365 tenant", "Which portal manages M365 licenses?", "Microsoft 365 admin center"),
        ("Implement and manage identity and access", "Conditional Access evaluates:", "User risk and device compliance"),
        ("Manage security and threats", "Which portal reviews security posture?", "Microsoft Defender portal"),
    ],
}


def build_unique_pool(code: str, meta: dict, target: int = 65) -> list:
    sections = [s[0] for s in meta.get("sections", [("General", 100)])]
    core = CORE_TEMPLATES.get(code, [])
    questions = []

    for n in range(target):
        if n < len(core):
            section, prompt, answer = core[n]
            text = f"[{code}] {prompt}"
            correct = answer
        else:
            section = sections[n % len(sections)]
            text = (
                f"[{code}] Practice item {n + 1}: In the context of \"{section}\", "
                f"select the most accurate statement for scenario {n + 1}."
            )
            correct = f"Correct concept for {section} (item {n + 1})"

        qtype = "multiple" if n % 4 == 0 else "single"
        options = [
            {"label": "A", "text": correct, "is_correct": True},
            {"label": "B", "text": f"Distractor B for item {n + 1}", "is_correct": False},
            {"label": "C", "text": f"Distractor C for item {n + 1}", "is_correct": False},
            {"label": "D", "text": f"Distractor D for item {n + 1}", "is_correct": False},
        ]
        if qtype == "multiple":
            options[1]["is_correct"] = True
            options[1]["text"] = f"Secondary valid point for item {n + 1}"

        questions.append({
            "section": section,
            "question_type": qtype,
            "text": text,
            "explanation": f"Review Microsoft Learn skills outline for {code} — {section}.",
            "external_id": f"seed-{code}-uniq-{n + 1}",
            "options": options,
        })
    return questions


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        sync_microsoft_catalog(db)
        for meta in MICROSOFT_EXAMS:
            code = meta["code"]
            payload = build_unique_pool(code, meta, 65)
            import_questions_json(db, code, payload, source="seed")
            print(f"Seeded {len(payload)} unique questions for {code}")
        print("Database seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
