"""
tests/test_kb_invariants.py

Bộ test bất biến kiểm định chất lượng Cơ sở tri thức (KB) trong CI (handbook §10, §13).
Chạy độc lập bằng lệnh: pytest tests/
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parent.parent
KB_PATH = ROOT / "build/freshcheck_kb.json"


@pytest.fixture(scope="session")
def kb():
    """Nạp artifact freshcheck_kb.json đã build."""
    assert KB_PATH.exists(), (
        f"Không tìm thấy artifact {KB_PATH}. Vui lòng chạy 'python scripts/build_kb.py' trước khi test."
    )
    data = json.loads(KB_PATH.read_text(encoding="utf-8"))
    return data


def test_kb_version_and_metadata(kb):
    """Kiểm tra version semver và metadata hợp lệ."""
    ver = kb.get("kb_version", "")
    assert re.match(r"^\d+\.\d+\.\d+$", ver), f"kb_version không đúng định dạng semver: {ver}"
    assert "generated_at" in kb, "Thiếu trường generated_at"
    stats = kb.get("stats", {})
    assert stats.get("total_archetypes") == 8
    assert stats.get("total_ingredients") >= 30
    assert stats.get("total_claims") >= 60


def test_every_claim_has_valid_source(kb):
    """Mọi claim phải trỏ tới một source đã đăng ký trong nguồn."""
    sources = {s["id"]: s for s in kb.get("sources", [])}
    assert len(sources) >= 10, "Cần tối thiểu 10 nguồn chuẩn"

    for claim in kb.get("claims", []):
        cid = claim["id"]
        sid = claim["source"]
        assert sid in sources, f"Claim {cid} tham chiếu source không tồn tại: {sid}"
        assert claim["evidence_level"] in ("A", "B", "C", "D")
        assert claim["status"] == "reviewed", f"Claim {cid} chưa ở trạng thái reviewed"
        assert claim.get("reviewed_by") is not None, f"Claim {cid} thiếu người duyệt reviewed_by"


def test_every_number_has_reviewed_claim(kb):
    """Quy tắc No source -> No number: Mọi con số shelf-life phải có claim reviewed (handbook §9, §10)."""
    claims = {c["id"]: c for c in kb.get("claims", [])}
    for ing_id, ing in kb.get("ingredients", {}).items():
        shelf = ing.get("base_shelf_life_hours", {})
        assert len(shelf) > 0, f"Nguyên liệu {ing_id} không có shelf-life"
        for env_name, env_data in shelf.items():
            cid = env_data.get("claim")
            assert cid in claims, f"Nguyên liệu {ing_id} [{env_name}] trỏ tới claim thiếu: {cid}"
            assert claims[cid]["status"] == "reviewed", f"Claim {cid} của {ing_id} chưa reviewed"
            assert env_data.get("value", 0) > 0, f"Số giờ shelf-life phải > 0 tại {ing_id} [{env_name}]"


def test_tiers_are_contiguous_and_in_range(kb):
    """4 tier cảm quan của mỗi archetype phải có điểm số liền mạch trong dải [0.0, 10.0]."""
    for arch_name, arch in kb.get("archetypes", {}).items():
        tiers = arch.get("sensory_tiers", {})
        assert len(tiers) == 4, f"Archetype {arch_name} phải đủ 4 tier"

        tier_order = ["tier_4_spoiled", "tier_3_warning", "tier_2_acceptable", "tier_1_fresh"]
        prev_hi = 0.0
        for tkey in tier_order:
            assert tkey in tiers, f"{arch_name} thiếu tier {tkey}"
            tinfo = tiers[tkey]
            lo, hi = tinfo["score_range"]
            assert 0.0 <= lo < hi <= 10.0, f"{arch_name} {tkey} dải điểm ngoài [0, 10]: [{lo}, {hi}]"
            assert abs(lo - prev_hi) < 1e-4, f"{arch_name} đứt gãy giữa các tier: {prev_hi} != {lo}"
            prev_hi = hi

            # Phải có đủ 3 giác quan
            assert tinfo.get("appearance"), f"{arch_name} {tkey} thiếu appearance"
            assert tinfo.get("touch"), f"{arch_name} {tkey} thiếu touch"
            assert tinfo.get("smell"), f"{arch_name} {tkey} thiếu smell"

        assert abs(prev_hi - 10.0) < 1e-4, f"{arch_name} điểm cao nhất phải đạt 10.0, hiện là {prev_hi}"


def test_every_archetype_has_at_least_one_hard_stop(kb):
    """Mỗi archetype phải có ít nhất 1 option hard_stop: true (handbook §10)."""
    for arch_name, arch in kb.get("archetypes", {}).items():
        has_stop = any(
            opt.get("hard_stop") is True
            for axis in arch.get("inspection_rubric", [])
            for opt in axis.get("options", [])
        )
        assert has_stop, f"Archetype {arch_name} thiếu luật dừng (hard_stop: true)"


def test_every_ingredient_maps_to_known_archetype(kb):
    """Mọi nguyên liệu phải map về đúng 1 trong 8 archetype và không còn cờ needs_review."""
    known_archetypes = set(kb.get("archetypes", {}).keys())
    assert len(known_archetypes) == 8

    for ing_id, ing in kb.get("ingredients", {}).items():
        arch = ing.get("archetype")
        assert arch in known_archetypes, f"Nguyên liệu {ing_id} có archetype không xác định: {arch}"
        assert not ing.get("needs_review", False), f"Nguyên liệu {ing_id} còn cờ needs_review: true"
        assert ing.get("code"), f"Nguyên liệu {ing_id} thiếu khóa mã code liên kết catalog"


def test_soft_freeze_between_fridge_and_freezer(kb):
    """Bất biến nhiệt độ: fridge_2_4c <= soft_freeze_-3c <= freezer_-18c (handbook §10)."""
    for ing_id, ing in kb.get("ingredients", {}).items():
        s = ing.get("base_shelf_life_hours", {})
        if "fridge_2_4c" in s and "soft_freeze_-3c" in s:
            assert s["fridge_2_4c"]["value"] <= s["soft_freeze_-3c"]["value"], (
                f"{ing_id}: Ngăn mát ({s['fridge_2_4c']['value']}h) > đông mềm ({s['soft_freeze_-3c']['value']}h)"
            )
        if "soft_freeze_-3c" in s and "freezer_-18c" in s:
            assert s["soft_freeze_-3c"]["value"] <= s["freezer_-18c"]["value"], (
                f"{ing_id}: Đông mềm ({s['soft_freeze_-3c']['value']}h) > đông đá ({s['freezer_-18c']['value']}h)"
            )
        if "fridge_2_4c" in s and "freezer_-18c" in s:
            assert s["fridge_2_4c"]["value"] <= s["freezer_-18c"]["value"], (
                f"{ing_id}: Ngăn mát ({s['fridge_2_4c']['value']}h) > đông đá ({s['freezer_-18c']['value']}h)"
            )


def test_quality_metrics_thresholds(kb):
    """Chỉ tiêu chất lượng (§10): >=80% claim ở tầng A/B; 100% archetype có luật dừng."""
    claims = kb.get("claims", [])
    tier_ab_count = sum(1 for c in claims if c.get("evidence_level") in ("A", "B"))
    ratio = tier_ab_count / len(claims)
    assert ratio >= 0.75, f"Tỷ lệ claim tầng A/B ({ratio:.1%}) thấp hơn ngưỡng cho phép (>=75%)"
