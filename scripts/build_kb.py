"""
scripts/build_kb.py

Gộp toàn bộ các file YAML thành artifact duy nhất build/freshcheck_kb.json (handbook §3, §6, §10, §11).
Định dạng JSON phẳng cho runtime engine và sync PostgreSQL, gắn version semver kb_version: "0.3.0".
Tự kiểm định toàn bộ các bất biến (invariants) trước khi xuất file.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
ARCHETYPES_DIR = REPO_ROOT / "archetypes"
INGREDIENTS_DIR = REPO_ROOT / "ingredients"
CLAIMS_DIR = REPO_ROOT / "claims"

KB_VERSION = "0.3.0"


def load_yaml(file_path: Path):
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")
    return yaml.safe_load(file_path.read_text("utf-8"))


def validate_kb(
    sources: list[dict],
    claims: list[dict],
    archetypes: dict[str, dict],
    ingredients: dict[str, dict],
):
    """Kiểm định toàn bộ bất biến kỹ thuật theo handbook §10 và checklist §13."""
    print("-> Bắt đầu kiểm định bất biến KB...")

    # 1. Kiểm tra nguồn (Sources)
    assert len(sources) > 0, "Danh sách sources rỗng"
    source_ids = {s["id"]: s for s in sources}

    # 2. Kiểm tra bằng chứng (Claims)
    assert len(claims) > 0, "Danh sách claims rỗng"
    claim_ids = {c["id"]: c for c in claims}

    for cid, c in claim_ids.items():
        assert c["source"] in source_ids, f"Claim {cid} tham chiếu source không tồn tại: {c['source']}"
        assert c.get("status") == "reviewed", f"Claim {cid} chưa có status: reviewed"

    # 3. Kiểm tra Archetypes
    assert len(archetypes) == 8, f"Yêu cầu đủ 8 archetypes, hiện có {len(archetypes)}"
    for arch_name, arch in archetypes.items():
        tiers = arch.get("sensory_tiers", {})
        assert len(tiers) == 4, f"{arch_name} thiếu tier (yêu cầu 4 tier)"

        # Tiers liền mạch trong [0.0, 10.0]
        ranges = []
        for tname, tinfo in tiers.items():
            lo, hi = tinfo["score_range"]
            assert 0.0 <= lo < hi <= 10.0, f"Dải điểm không hợp lệ {arch_name} {tname}: {tinfo['score_range']}"
            ranges.append((lo, hi))

        # Mỗi archetype phải có ít nhất 1 option hard_stop: true
        has_hard_stop = False
        rubric = arch.get("inspection_rubric", [])
        assert len(rubric) > 0, f"{arch_name} thiếu inspection_rubric"
        for axis in rubric:
            for opt in axis.get("options", []):
                if opt.get("hard_stop"):
                    has_hard_stop = True
                cid = opt.get("claim")
                if cid:
                    assert cid in claim_ids, f"Option {opt.get('value')} trong {arch_name} thiếu claim: {cid}"
        assert has_hard_stop, f"{arch_name} thiếu luật dừng (hard_stop: true)"

    # 4. Kiểm tra Ingredients
    assert len(ingredients) >= 30, f"Yêu cầu tối thiểu 30-35 nguyên liệu P0, hiện có {len(ingredients)}"
    for ing_id, ing in ingredients.items():
        arch = ing.get("archetype")
        assert arch in archetypes, f"Nguyên liệu {ing_id} trỏ tới archetype không rõ: {arch}"
        assert not ing.get("needs_review", False), f"Nguyên liệu {ing_id} còn mang cờ needs_review"

        shelf = ing.get("base_shelf_life_hours", {})
        assert len(shelf) > 0, f"Nguyên liệu {ing_id} thiếu base_shelf_life_hours"

        for env_name, env_data in shelf.items():
            cid = env_data.get("claim")
            assert cid in claim_ids, f"Nguyên liệu {ing_id} [{env_name}] trỏ tới claim thiếu: {cid}"
            assert claim_ids[cid]["status"] == "reviewed", f"Claim {cid} chưa được reviewed"
            assert env_data.get("value", 0) > 0, f"Giá trị giờ phải dương: {ing_id} [{env_name}]"

        # Bất biến nhiệt độ: fridge <= soft_freeze <= freezer
        if "fridge_2_4c" in shelf and "soft_freeze_-3c" in shelf:
            assert shelf["fridge_2_4c"]["value"] <= shelf["soft_freeze_-3c"]["value"], (
                f"Lỗi logic nhiệt độ ({ing_id}): fridge > soft_freeze"
            )
        if "soft_freeze_-3c" in shelf and "freezer_-18c" in shelf:
            assert shelf["soft_freeze_-3c"]["value"] <= shelf["freezer_-18c"]["value"], (
                f"Lỗi logic nhiệt độ ({ing_id}): soft_freeze > freezer"
            )
        if "fridge_2_4c" in shelf and "freezer_-18c" in shelf:
            assert shelf["fridge_2_4c"]["value"] <= shelf["freezer_-18c"]["value"], (
                f"Lỗi logic nhiệt độ ({ing_id}): fridge > freezer"
            )

    print("-> Xác thực toàn bộ bất biến KB: ĐẠT 100% (Green).")


def build_kb() -> Path:
    print(f"=== Bắt đầu build FreshCheck KB (v{KB_VERSION}) ===")

    # 1. Đọc sources & claims
    sources = load_yaml(CLAIMS_DIR / "sources.yaml")
    claims = load_yaml(CLAIMS_DIR / "claims.yaml")
    print(f"Loaded {len(sources)} sources, {len(claims)} claims.")

    # 2. Đọc archetypes
    archetypes = {}
    for arch_file in sorted(ARCHETYPES_DIR.glob("*.yaml")):
        data = load_yaml(arch_file)
        arch_id = data["archetype"]
        archetypes[arch_id] = data
    print(f"Loaded {len(archetypes)} archetypes: {list(archetypes.keys())}")

    # 3. Đọc ingredients
    ingredients = {}
    for ing_file in sorted(INGREDIENTS_DIR.glob("*.yaml")):
        items = load_yaml(ing_file)
        for item in items:
            ingredients[item["id"]] = item
    print(f"Loaded {len(ingredients)} ingredients.")

    # 4. Kiểm định bất biến
    validate_kb(sources, claims, archetypes, ingredients)

    # 5. Đóng gói payload JSON
    payload = {
        "kb_version": KB_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_archetypes": len(archetypes),
            "total_ingredients": len(ingredients),
            "total_claims": len(claims),
            "total_sources": len(sources),
        },
        "sources": sources,
        "claims": claims,
        "archetypes": archetypes,
        "ingredients": ingredients,
    }

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    out_file = BUILD_DIR / "freshcheck_kb.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    size_kb = out_file.stat().st_size / 1024
    print(f"\n=> Xuất thành công artifact: {out_file} ({size_kb:.1f} KB)")
    print(f"   kb_version: {KB_VERSION}")
    print(f"   Archetypes : {len(archetypes)}")
    print(f"   Ingredients: {len(ingredients)}")
    print(f"   Claims     : {len(claims)}")
    print(f"   Sources    : {len(sources)}")
    return out_file


if __name__ == "__main__":
    build_kb()
