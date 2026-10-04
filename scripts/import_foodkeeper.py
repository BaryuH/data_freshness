"""
scripts/import_foodkeeper.py

Bơm shelf-life từ USDA FoodKeeper và quy tắc bản địa vào tầng Ingredient (handbook §5.2, §7, §8).
Tự động map danh mục ~35 nguyên liệu ưu tiên (P0) vào 8 Archetype của FreshCheck.
Chạy tách bạch, idempotent, tự kiểm định bất biến.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import yaml

# Khám phá đường dẫn thư mục gốc repo
REPO_ROOT = Path(__file__).resolve().parent.parent


def find_foodkeeper_json() -> Path:
    candidates = [
        REPO_ROOT / "sources/raw/foodkeeper.json",
        REPO_ROOT / "foodkeeper.json",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 1000:
            return p
    raise FileNotFoundError(
        f"Không tìm thấy file foodkeeper.json hợp lệ tại {candidates}"
    )


def find_master_ingredients_csv() -> Path | None:
    candidates = [
        REPO_ROOT / "data/processed/viendinhduong/master_ingredients_nutrition.csv",
        REPO_ROOT.parent / "sweep-food-AI/data/processed/viendinhduong/master_ingredients_nutrition.csv",
        Path("G:/github/sweep-food-AI/data/processed/viendinhduong/master_ingredients_nutrition.csv"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def normalize_row(row: list[dict] | dict) -> dict:
    if isinstance(row, list):
        res = {}
        for d in row:
            if isinstance(d, dict):
                res.update(d)
        return res
    return row


def to_hours(val: float | int | None, metric: str | None) -> float | None:
    if val is None or metric is None:
        return None
    val = float(val)
    m = str(metric).lower()
    if "hour" in m:
        return round(val, 1)
    if "day" in m:
        return round(val * 24.0, 1)
    if "week" in m:
        return round(val * 7 * 24.0, 1)
    if "month" in m:
        return round(val * 30 * 24.0, 1)
    if "year" in m:
        return round(val * 365 * 24.0, 1)
    return None


def get_fk_shelf_life(prod: dict, env_type: str) -> float | None:
    if env_type == "pantry":
        min_v = prod.get("DOP_Pantry_Min") or prod.get("Pantry_Min")
        metric = prod.get("DOP_Pantry_Metric") or prod.get("Pantry_Metric")
        return to_hours(min_v, metric)
    if env_type == "refrigerate":
        min_v = prod.get("DOP_Refrigerate_Min") or prod.get("Refrigerate_Min")
        metric = prod.get("DOP_Refrigerate_Metric") or prod.get("Refrigerate_Metric")
        return to_hours(min_v, metric)
    if env_type == "freeze":
        min_v = prod.get("DOP_Freeze_Min") or prod.get("Freeze_Min")
        metric = prod.get("DOP_Freeze_Metric") or prod.get("Freeze_Metric")
        return to_hours(min_v, metric)
    return None


# Danh mục ~35 nguyên liệu ưu tiên P0 phủ kín 8 Archetype
P0_SPECS = [
    # 1. FRESH_MEAT (5 món)
    {
        "id": "thit_ba_chi_heo",
        "code": "7018",
        "names_vi": ["thịt ba chỉ heo", "ba rọi", "ba chỉ heo", "thịt ba chỉ"],
        "archetype": "FRESH_MEAT",
        "fk_id": 60,
        "envs": {
            "room_temp_25_30c": {"value": 4.0, "claim": "C-LOCAL-HOTMEAT"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-PORK-CHOPS"},
            "soft_freeze_-3c": {"value": 168.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-PORK-FREEZE"},
        },
    },
    {
        "id": "thit_nac_heo",
        "code": "7085",
        "names_vi": ["thịt nạc heo", "nạc thăn heo", "thịt lợn nạc"],
        "archetype": "FRESH_MEAT",
        "fk_id": 61,
        "envs": {
            "room_temp_25_30c": {"value": 4.0, "claim": "C-LOCAL-HOTMEAT"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-PORK-CHOPS"},
            "soft_freeze_-3c": {"value": 168.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-PORK-FREEZE"},
        },
    },
    {
        "id": "suon_heo",
        "code": "7053",
        "names_vi": ["sườn heo", "sườn lợn", "sườn non"],
        "archetype": "FRESH_MEAT",
        "fk_id": 60,
        "envs": {
            "room_temp_25_30c": {"value": 4.0, "claim": "C-LOCAL-HOTMEAT"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-PORK-CHOPS"},
            "soft_freeze_-3c": {"value": 168.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-PORK-FREEZE"},
        },
    },
    {
        "id": "thit_bo_than",
        "code": "7005",
        "names_vi": ["thịt thăn bò", "thịt bò", "bắp bò", "thịt bò tươi"],
        "archetype": "FRESH_MEAT",
        "fk_id": 34,
        "envs": {
            "room_temp_25_30c": {"value": 4.0, "claim": "C-LOCAL-HOTMEAT"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-BEEF-STEAK"},
            "soft_freeze_-3c": {"value": 168.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-BEEF-FREEZE"},
        },
    },
    {
        "id": "thit_ga_ta",
        "code": "7013",
        "names_vi": ["thịt gà ta", "gà làm sẵn", "thịt gà", "ức gà"],
        "archetype": "FRESH_MEAT",
        "fk_id": 113,
        "envs": {
            "room_temp_25_30c": {"value": 4.0, "claim": "C-LOCAL-HOTMEAT"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-POULTRY-PARTS"},
            "soft_freeze_-3c": {"value": 120.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-POULTRY-FREEZE"},
        },
    },
    # 2. FISH_SEAFOOD (5 món)
    {
        "id": "ca_loc",
        "code": "8022",
        "names_vi": ["cá lóc", "cá quả", "cá chuối"],
        "archetype": "FISH_SEAFOOD",
        "fk_id": 144,
        "envs": {
            "room_temp_25_30c": {"value": 3.0, "claim": "C-LOCAL-FISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-FISH-LEAN"},
            "soft_freeze_-3c": {"value": 120.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-FISH-FREEZE"},
        },
    },
    {
        "id": "ca_dieu_hong",
        "code": "8024",
        "names_vi": ["cá điêu hồng", "cá rô phi", "rô phi đỏ"],
        "archetype": "FISH_SEAFOOD",
        "fk_id": 144,
        "envs": {
            "room_temp_25_30c": {"value": 3.0, "claim": "C-LOCAL-FISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-FISH-LEAN"},
            "soft_freeze_-3c": {"value": 120.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-FISH-FREEZE"},
        },
    },
    {
        "id": "tom_bien",
        "code": "8051",
        "names_vi": ["tôm biển", "tôm thẻ", "tôm sú", "tôm tươi"],
        "archetype": "FISH_SEAFOOD",
        "fk_id": 151,
        "envs": {
            "room_temp_25_30c": {"value": 2.0, "claim": "C-LOCAL-FISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SHRIMP-FRESH"},
            "soft_freeze_-3c": {"value": 120.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-SHRIMP-FREEZE"},
        },
    },
    {
        "id": "muc_tuoi",
        "code": "8040",
        "names_vi": ["mực tươi", "mực ống", "mực lá"],
        "archetype": "FISH_SEAFOOD",
        "fk_id": 152,
        "envs": {
            "room_temp_25_30c": {"value": 2.0, "claim": "C-LOCAL-FISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SQUID-FRESH"},
            "soft_freeze_-3c": {"value": 120.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-SQUID-FREEZE"},
        },
    },
    {
        "id": "bach_tuoc_tuoi",
        "code": "20053",
        "names_vi": ["bạch tuộc tươi", "bạch tuộc"],
        "archetype": "FISH_SEAFOOD",
        "fk_id": 152,
        "envs": {
            "room_temp_25_30c": {"value": 2.0, "claim": "C-LOCAL-FISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SQUID-FRESH"},
            "soft_freeze_-3c": {"value": 120.0, "claim": "C-LOCAL-SOFTFREEZE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-SQUID-FREEZE"},
        },
    },
    # 3. LIVE_SHELLFISH (4 món)
    {
        "id": "ngheu_song",
        "code": "8066",
        "names_vi": ["ngao sống", "nghêu sống", "nghêu", "ngao"],
        "archetype": "LIVE_SHELLFISH",
        "fk_id": 150,
        "envs": {
            "room_temp_25_30c": {"value": 6.0, "claim": "C-LOCAL-SHELLFISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SHELLFISH-LIVE"},
            "freezer_-18c": {"value": 1440.0, "claim": "C-FK-SHELLFISH-FREEZE"},
        },
    },
    {
        "id": "so_huyet",
        "code": "8048",
        "names_vi": ["sò huyết", "sò", "sò lông"],
        "archetype": "LIVE_SHELLFISH",
        "fk_id": 150,
        "envs": {
            "room_temp_25_30c": {"value": 6.0, "claim": "C-LOCAL-SHELLFISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SHELLFISH-LIVE"},
            "freezer_-18c": {"value": 1440.0, "claim": "C-FK-SHELLFISH-FREEZE"},
        },
    },
    {
        "id": "oc_buou",
        "code": "8041",
        "names_vi": ["ốc bươu", "ốc nhồi", "ốc hương sống"],
        "archetype": "LIVE_SHELLFISH",
        "fk_id": 150,
        "envs": {
            "room_temp_25_30c": {"value": 6.0, "claim": "C-LOCAL-SHELLFISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SHELLFISH-LIVE"},
            "freezer_-18c": {"value": 1440.0, "claim": "C-FK-SHELLFISH-FREEZE"},
        },
    },
    {
        "id": "cua_dong",
        "code": "8034",
        "names_vi": ["cua đồng", "cua biển", "ghẹ sống"],
        "archetype": "LIVE_SHELLFISH",
        "fk_id": 150,
        "envs": {
            "room_temp_25_30c": {"value": 4.0, "claim": "C-LOCAL-SHELLFISH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-SHELLFISH-LIVE"},
            "freezer_-18c": {"value": 1440.0, "claim": "C-FK-SHELLFISH-FREEZE"},
        },
    },
    # 4. EGG (3 món)
    {
        "id": "trung_ga",
        "code": "9001",
        "names_vi": ["trứng gà", "trứng gà ta", "trứng gà công nghiệp"],
        "archetype": "EGG",
        "fk_id": 21,
        "envs": {
            "room_temp_25_30c": {"value": 240.0, "claim": "C-LOCAL-EGG-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-EGG-STORAGE"},
        },
    },
    {
        "id": "trung_vit",
        "code": "9004",
        "names_vi": ["trứng vịt"],
        "archetype": "EGG",
        "fk_id": 21,
        "envs": {
            "room_temp_25_30c": {"value": 240.0, "claim": "C-LOCAL-EGG-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-EGG-STORAGE"},
        },
    },
    {
        "id": "trung_cut",
        "code": "9007",
        "names_vi": ["trứng cút", "trứng chim cút"],
        "archetype": "EGG",
        "fk_id": 21,
        "envs": {
            "room_temp_25_30c": {"value": 168.0, "claim": "C-LOCAL-EGG-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-EGG-STORAGE"},
        },
    },
    # 5. TUBER_ROOT (5 món)
    {
        "id": "khoai_tay",
        "code": "2014",
        "names_vi": ["khoai tây"],
        "archetype": "TUBER_ROOT",
        "fk_id": 297,
        "envs": {
            "room_temp_25_30c": {"fk_key": "pantry", "claim": "C-FK-POTATO-PANTRY"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-POTATO-FRIDGE"},
        },
    },
    {
        "id": "khoai_lang",
        "code": "2008",
        "names_vi": ["khoai lang", "khoai lang mật"],
        "archetype": "TUBER_ROOT",
        "fk_id": 422,
        "envs": {
            "room_temp_25_30c": {"fk_key": "pantry", "claim": "C-FK-SWEETPOTATO-PANTRY"},
        },
    },
    {
        "id": "ca_rot",
        "code": "4007",
        "names_vi": ["cà rốt"],
        "archetype": "TUBER_ROOT",
        "fk_id": 279,
        "envs": {
            "room_temp_25_30c": {"value": 72.0, "claim": "C-TCVN10738-SENSORY"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-CARROT-FRIDGE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-TCVN10738-SENSORY"},
        },
    },
    {
        "id": "cu_cai_trang",
        "code": "4021",
        "names_vi": ["củ cải trắng", "củ cải"],
        "archetype": "TUBER_ROOT",
        "fk_id": 299,
        "envs": {
            "room_temp_25_30c": {"value": 72.0, "claim": "C-TCVN10738-SENSORY"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-RADISH-FRIDGE"},
        },
    },
    {
        "id": "hanh_tay",
        "code": "4039",
        "names_vi": ["hành tây"],
        "archetype": "TUBER_ROOT",
        "fk_id": 294,
        "envs": {
            "room_temp_25_30c": {"fk_key": "pantry", "claim": "C-FK-ONION-PANTRY"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-ONION-PANTRY"},
        },
    },
    # 6. LEAFY_VEG (5 món)
    {
        "id": "rau_muong",
        "code": "4083",
        "names_vi": ["rau muống"],
        "archetype": "LEAFY_VEG",
        "fk_id": 415,
        "envs": {
            "room_temp_25_30c": {"value": 36.0, "claim": "C-LOCAL-LEAFY-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEAFY-FRIDGE"},
        },
    },
    {
        "id": "cai_ngot",
        "code": "4108",
        "names_vi": ["cải ngọt", "rau cải ngọt"],
        "archetype": "LEAFY_VEG",
        "fk_id": 415,
        "envs": {
            "room_temp_25_30c": {"value": 36.0, "claim": "C-LOCAL-LEAFY-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEAFY-FRIDGE"},
        },
    },
    {
        "id": "cai_thia",
        "code": "4015",
        "names_vi": ["cải thìa", "cải bẹ trắng", "cải chíp"],
        "archetype": "LEAFY_VEG",
        "fk_id": 415,
        "envs": {
            "room_temp_25_30c": {"value": 36.0, "claim": "C-LOCAL-LEAFY-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEAFY-FRIDGE"},
        },
    },
    {
        "id": "xa_lach",
        "code": "4090",
        "names_vi": ["xà lách", "rau xà lách"],
        "archetype": "LEAFY_VEG",
        "fk_id": 290,
        "envs": {
            "room_temp_25_30c": {"value": 24.0, "claim": "C-LOCAL-LEAFY-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEAFY-FRIDGE"},
        },
    },
    {
        "id": "hanh_la",
        "code": "4038",
        "names_vi": ["hành lá", "hành hoa", "ngò rí"],
        "archetype": "LEAFY_VEG",
        "fk_id": 415,
        "envs": {
            "room_temp_25_30c": {"value": 24.0, "claim": "C-LOCAL-LEAFY-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEAFY-FRIDGE"},
        },
    },
    # 7. FRESH_STARCH_SOY (4 món)
    {
        "id": "bun_tuoi",
        "code": "1020",
        "names_vi": ["bún tươi"],
        "archetype": "FRESH_STARCH_SOY",
        "fk_id": 332,
        "envs": {
            "room_temp_25_30c": {"value": 12.0, "claim": "C-LOCAL-STARCH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-NOODLE-FRESH"},
        },
    },
    {
        "id": "banh_pho_tuoi",
        "code": "1013",
        "names_vi": ["bánh phở tươi", "bánh phở"],
        "archetype": "FRESH_STARCH_SOY",
        "fk_id": 332,
        "envs": {
            "room_temp_25_30c": {"value": 12.0, "claim": "C-LOCAL-STARCH-ROOM"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-NOODLE-FRESH"},
        },
    },
    {
        "id": "dau_hu_trang",
        "code": "3025",
        "names_vi": ["đậu hũ trắng", "đậu phụ trắng", "đậu hũ tươi"],
        "archetype": "FRESH_STARCH_SOY",
        "fk_id": 168,
        "envs": {
            "room_temp_25_30c": {"value": 6.0, "claim": "C-LOCAL-STARCH-ROOM"},
            "fridge_2_4c": {"value": 72.0, "claim": "C-FK-TOFU-STORAGE"},
        },
    },
    {
        "id": "dau_hu_chien",
        "code": "3026",
        "names_vi": ["đậu hũ chiên", "đậu phụ rán"],
        "archetype": "FRESH_STARCH_SOY",
        "fk_id": 168,
        "envs": {
            "room_temp_25_30c": {"value": 12.0, "claim": "C-LOCAL-STARCH-ROOM"},
            "fridge_2_4c": {"value": 96.0, "claim": "C-FK-TOFU-STORAGE"},
        },
    },
    # 8. COOKED_LEFTOVERS (3 món)
    {
        "id": "com_nguoi",
        "code": "1004",
        "names_vi": ["cơm nguội", "cơm trắng đã nấu"],
        "archetype": "COOKED_LEFTOVERS",
        "fk_id": 178,
        "envs": {
            "room_temp_25_30c": {"value": 2.0, "claim": "C-USDA-LEFTOVERS-2HR"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-RICE-FRIDGE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-LEFTOVERS-FREEZE"},
        },
    },
    {
        "id": "canh_de_lai",
        "code": "4084",
        "names_vi": ["canh để lại", "canh rau thịt", "nước dùng để lại"],
        "archetype": "COOKED_LEFTOVERS",
        "fk_id": 193,
        "envs": {
            "room_temp_25_30c": {"value": 2.0, "claim": "C-USDA-LEFTOVERS-2HR"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEFTOVERS-FRIDGE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-LEFTOVERS-FREEZE"},
        },
    },
    {
        "id": "thit_ca_kho_de_lai",
        "code": "7003",
        "names_vi": ["thịt kho để lại", "cá kho để lại", "món mặn để lại"],
        "archetype": "COOKED_LEFTOVERS",
        "fk_id": 174,
        "envs": {
            "room_temp_25_30c": {"value": 2.0, "claim": "C-USDA-LEFTOVERS-2HR"},
            "fridge_2_4c": {"fk_key": "refrigerate", "claim": "C-FK-LEFTOVERS-FRIDGE"},
            "freezer_-18c": {"fk_key": "freeze", "claim": "C-FK-LEFTOVERS-FREEZE"},
        },
    },
]


def validate_kb_invariants(records: list[dict]):
    """Kiểm tra bất biến dữ liệu KB trước khi ghi file (handbook §10, §13)."""
    archetypes_dir = REPO_ROOT / "archetypes"
    known_archetypes = {f.stem.upper(): f for f in archetypes_dir.glob("*.yaml")}

    claims_file = REPO_ROOT / "claims/claims.yaml"
    claims_list = yaml.safe_load(claims_file.read_text("utf-8"))
    claims_map = {c["id"]: c for c in claims_list}

    for ing in records:
        arch = ing["archetype"]
        assert arch in known_archetypes, (
            f"Nguyên liệu {ing['id']} trỏ tới archetype không tồn tại: {arch}"
        )

        s = ing["base_shelf_life_hours"]
        assert len(s) > 0, f"Nguyên liệu {ing['id']} không có giá trị shelf-life nào"

        for env_name, env_data in s.items():
            cid = env_data["claim"]
            assert cid in claims_map, (
                f"Nguyên liệu {ing['id']} [{env_name}] trỏ tới claim thiếu: {cid}"
            )
            assert claims_map[cid]["status"] == "reviewed", (
                f"Claim {cid} chưa được reviewed"
            )
            assert env_data["value"] > 0, (
                f"Shelf-life phải dương: {ing['id']} [{env_name}]"
            )

        # Invariant thứ tự nhiệt độ: fridge <= soft_freeze <= freezer
        if "fridge_2_4c" in s and "soft_freeze_-3c" in s:
            assert s["fridge_2_4c"]["value"] <= s["soft_freeze_-3c"]["value"], (
                f"Lỗi logic nhiệt độ ({ing['id']}): fridge > soft_freeze"
            )
        if "soft_freeze_-3c" in s and "freezer_-18c" in s:
            assert s["soft_freeze_-3c"]["value"] <= s["freezer_-18c"]["value"], (
                f"Lỗi logic nhiệt độ ({ing['id']}): soft_freeze > freezer"
            )
        if "fridge_2_4c" in s and "freezer_-18c" in s:
            assert s["fridge_2_4c"]["value"] <= s["freezer_-18c"]["value"], (
                f"Lỗi logic nhiệt độ ({ing['id']}): fridge > freezer"
            )


def main():
    fk_path = find_foodkeeper_json()
    print(f"Đọc dữ liệu FoodKeeper: {fk_path}")
    raw_fk = json.loads(fk_path.read_text("utf-8"))

    product_sheet = next(s for s in raw_fk["sheets"] if s.get("name") == "Product")
    products_by_id = {}
    for p in product_sheet["data"]:
        norm = normalize_row(p)
        pid = norm.get("ID")
        if pid is not None:
            products_by_id[int(float(pid))] = norm

    master_csv = find_master_ingredients_csv()
    if master_csv:
        print(f"Đã liên kết catalog Viện Dinh Dưỡng: {master_csv}")
    else:
        print("Cảnh báo: Không tìm thấy master_ingredients_nutrition.csv, sử dụng code tĩnh.")

    records = []
    for spec in P0_SPECS:
        fk_prod = products_by_id.get(spec.get("fk_id"))
        envs_out = {}
        for env_name, env_spec in spec["envs"].items():
            claim_id = env_spec["claim"]
            if "value" in env_spec:
                val = float(env_spec["value"])
            elif "fk_key" in env_spec and fk_prod:
                val = get_fk_shelf_life(fk_prod, env_spec["fk_key"])
                if val is None:
                    raise ValueError(
                        f"Không trích xuất được {env_spec['fk_key']} từ FoodKeeper ID {spec['fk_id']} cho {spec['id']}"
                    )
            else:
                raise ValueError(f"Cấu hình env không hợp lệ: {spec['id']} {env_name}")

            envs_out[env_name] = {"value": val, "claim": claim_id}

        records.append({
            "id": spec["id"],
            "code": spec["code"],
            "names_vi": spec["names_vi"],
            "archetype": spec["archetype"],
            "base_shelf_life_hours": envs_out,
        })

    # Kiểm định bất biến
    validate_kb_invariants(records)
    print("Xác thực toàn bộ bất biến KB (Invariants): ĐẠT 100%.")

    # Xuất ra file p0_ingredients.yaml
    out_file = REPO_ROOT / "ingredients/p0_ingredients.yaml"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_content = yaml.safe_dump(records, allow_unicode=True, sort_keys=False)
    out_file.write_text(out_content, encoding="utf-8")

    print(f"\nĐã xuất thành công {len(records)} nguyên liệu P0 -> {out_file}")

    # Thống kê phân bổ theo Archetype
    stats = {}
    for r in records:
        stats[r["archetype"]] = stats.get(r["archetype"], 0) + 1

    print("\nThống kê phân bổ theo 8 Archetype:")
    for arch, count in sorted(stats.items()):
        print(f"  - {arch:18s}: {count:2d} nguyên liệu")


if __name__ == "__main__":
    main()
