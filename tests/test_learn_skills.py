import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.services.learn_skills_service import normalize_skill_weights, parse_skills_from_html


def test_parse_sc200_skills():
    html = """
    Skills at a glance
    Manage a security operations environment (40–45%)
    Respond to security incidents (35–40%)
    Perform threat hunting (20–25%)
    """
    skills = parse_skills_from_html(html)
    assert len(skills) == 3
    outline = normalize_skill_weights(skills)
    assert abs(sum(s["weight_percent"] for s in outline) - 100) < 0.2
    names = [s["name"] for s in outline]
    assert "Manage a security operations environment" in names


def test_normalize_single_percent():
    outline = normalize_skill_weights([("Topic A", 25, 25), ("Topic B", 75, 75)])
    assert outline[0]["weight_percent"] == 25.0
    assert outline[1]["weight_percent"] == 75.0
