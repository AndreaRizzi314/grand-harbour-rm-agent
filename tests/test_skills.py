from __future__ import annotations

import re
from pathlib import Path

import frontmatter


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"


def skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def skill_posts():
    return [(path, frontmatter.load(path)) for path in skill_files()]


def test_pack_version_pin():
    challenge_skill = (SKILLS_DIR / "CHALLENGE_SKILL.md").read_text(encoding="utf-8")
    post = frontmatter.loads(challenge_skill)
    assert "otel-rm-v2" in post["description"]


def test_minimum_skill_count_and_frontmatter():
    posts = skill_posts()
    assert len(posts) >= 6
    for path, post in posts:
        assert post.get("name")
        assert post.get("description")
        assert post["name"] == path.parent.name


def test_judgment_skills_have_thresholds_and_actions():
    qualifying = 0
    for _path, post in skill_posts():
        body = post.content
        has_threshold = bool(re.search(r"(>=|<=|>|<)\s*\d+|\b\d+%", body))
        has_action = bool(
            re.search(
                r"\brecommend\b|\baction\b|\bshift\b|\bclose\b|\breview\b|\bprotect\b|\bhold\b",
                body,
                re.IGNORECASE,
            )
        )
        if has_threshold and has_action and len(body.split()) >= 80:
            qualifying += 1
    assert qualifying >= 3


def test_tool_routing_declared_without_raw_sql():
    tool_names = {
        "get_otb_summary",
        "get_segment_mix",
        "get_pickup_delta",
        "get_as_of_otb",
        "get_block_vs_transient_mix",
    }
    for _path, post in skill_posts():
        body = post.content + "\n" + post["description"]
        assert any(tool_name in body for tool_name in tool_names)
        assert "arbitrary sql" not in body.lower()
        assert "reservations_hackathon directly" not in body.lower()


def test_distinct_routing_and_topic_coverage():
    posts = skill_posts()
    names = [post["name"] for _path, post in posts]
    descriptions = [" ".join(post["description"].split()) for _path, post in posts]
    assert len(names) == len(set(names))
    assert len(descriptions) == len(set(descriptions))
    combined = "\n".join(post["description"] + "\n" + post.content for _path, post in posts)
    assert "get_pickup_delta" in combined
    assert "get_segment_mix" in combined or "get_block_vs_transient_mix" in combined
    assert "get_otb_summary" in combined


def test_adversarial_guardrail_exists():
    combined = "\n".join(post.content for _path, post in skill_posts()).lower()
    assert "stay rows are not reservations" in combined or "property_date" in combined or "provisional" in combined

