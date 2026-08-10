"""
processors/source_helper.py — Utility chuẩn hóa và phân loại nhãn nguồn lead.
"""

from typing import Dict, Any


def get_source_info(source: str) -> Dict[str, Any]:
    """
    Trả về thông tin chi tiết về nguồn lead:
    - label: Tên nhãn đầy đủ tiếng Việt (dùng cho export Excel/CSV)
    - short_label: Nhãn ngắn gọn hiển thị trên badge
    - category: facebook | google_maps | other
    - icon: Biểu tượng đại diện (📝, 💬, 👤, 📍, 👍, 🌐)
    - badge_class: Class CSS định style màu sắc
    """
    s = (source or "").lower().strip()

    if "comment" in s:
        if s.startswith("google_maps"):
            return {
                "label": "Google Maps — Comment",
                "short_label": "Maps — Comment",
                "category": "google_maps",
                "icon": "💬",
                "badge_class": "source-tag--maps-comment",
            }
        return {
            "label": "Facebook — Comment",
            "short_label": "FB — Comment",
            "category": "facebook",
            "icon": "💬",
            "badge_class": "source-tag--fb-comment",
        }
    elif "post" in s:
        return {
            "label": "Facebook — Bài viết",
            "short_label": "FB — Bài viết",
            "category": "facebook",
            "icon": "📝",
            "badge_class": "source-tag--fb-post",
        }
    elif any(k in s for k in ["about", "bio", "profile"]):
        return {
            "label": "Facebook — Profile / Bio",
            "short_label": "FB — Profile",
            "category": "facebook",
            "icon": "👤",
            "badge_class": "source-tag--fb-profile",
        }
    elif "liker" in s:
        return {
            "label": "Facebook — Lượt thích",
            "short_label": "FB — Lượt thích",
            "category": "facebook",
            "icon": "👍",
            "badge_class": "source-tag--fb-liker",
        }
    elif s.startswith("fb"):
        return {
            "label": "Facebook",
            "short_label": "Facebook",
            "category": "facebook",
            "icon": "📘",
            "badge_class": "source-tag--fb-default",
        }
    elif s in ["google_maps_comment", "google_maps_review"]:
        return {
            "label": "Google Maps — Comment",
            "short_label": "Maps — Comment",
            "category": "google_maps",
            "icon": "💬",
            "badge_class": "source-tag--maps-comment",
        }
    elif s in ["google_maps", "google_maps_details"] or "maps" in s:
        return {
            "label": "Google Maps — Details",
            "short_label": "Maps — Details",
            "category": "google_maps",
            "icon": "📍",
            "badge_class": "source-tag--maps-details",
        }
    else:
        clean = s.replace("_", " ").title()
        return {
            "label": clean or "Khác",
            "short_label": clean or "Khác",
            "category": "other",
            "icon": "🌐",
            "badge_class": "source-tag--default",
        }


def format_source_label(source: str) -> str:
    """Trả về chuỗi tên nhãn đầy đủ cho nguồn."""
    return get_source_info(source)["label"]
