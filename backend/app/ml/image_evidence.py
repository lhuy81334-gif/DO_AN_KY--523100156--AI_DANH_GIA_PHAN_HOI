import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[3]
IMAGE_CACHE_DIR = ROOT_DIR / "data/cache/review_images"
MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")
DISTRACTOR_LABELS = [
    "a pair of pants or trousers",
    "a pair of shorts",
    "a book",
    "a mobile phone",
    "a food item",
    "a cosmetic bottle",
    "a cardboard shipping box only",
    "a random screenshot",
    "a document or receipt only",
]
GENERAL_OTHER_EVIDENCE_LABELS = [
    "a normal product photo",
    "a random unrelated photo",
    "a screenshot",
    "a receipt only",
]
CLAIM_EVIDENCE_RULES = [
    (
        "shipping_packaging_damage",
        ("giao", "ship", "shipping", "van chuyen", "dong goi", "bao bi", "hop", "thung", "mop", "meo", "bep", "vo hop", "rach hop"),
        [
            "a dented shipping package",
            "a damaged cardboard box",
            "a crushed parcel",
            "torn product packaging",
            "damaged delivery packaging",
        ],
    ),
    (
        "product_damage_or_defect",
        ("rach", "be", "vo", "nut", "hong", "loi", "bong", "xuoc", "lem", "mop goc", "cong", "defect", "broken", "damaged"),
        [
            "a damaged product",
            "a broken product",
            "a defective product",
            "visible product damage",
            "a product quality defect",
        ],
    ),
    (
        "wrong_or_missing_item",
        ("sai mau", "sai size", "sai san pham", "nham", "thieu", "khac hinh", "khong dung", "wrong item", "missing item"),
        [
            "the wrong delivered product",
            "a product different from the listing",
            "missing items in the package",
            "a mismatch between ordered item and received item",
        ],
    ),
    (
        "authenticity_or_label_issue",
        ("hang gia", "fake", "khong chinh hang", "tem", "seal", "ma vach", "logo", "nhan mac", "authentic"),
        [
            "a product label or logo",
            "a product seal",
            "a barcode on packaging",
            "authenticity information on the package",
        ],
    ),
    (
        "product_quality_feedback",
        ("chat luong", "vai", "mau", "size", "form", "in", "mui", "texture", "hieu qua", "da", "kem", "serum", "sach", "giay"),
        [
            "the purchased product",
            "a close up of the product",
            "a product quality issue",
            "the product described in the review",
        ],
    ),
]
PRODUCT_LABEL_RULES = [
    (("ao", "shirt", "t-shirt", "tshirt", "tee", "hoodie", "sweatshirt"), ["a shirt", "a t-shirt", "a clothing top", "a hoodie or sweatshirt"]),
    (("quan", "pants", "trousers", "jeans", "shorts"), ["a pair of pants or trousers", "a pair of jeans", "a pair of shorts"]),
    (("sach", "book"), ["a book", "a printed book", "a cookbook"]),
    (("giay", "shoe", "sneaker"), ["a pair of shoes", "a sneaker"]),
    (("tui", "bag", "backpack"), ["a bag", "a backpack"]),
    (("dien thoai", "phone", "smartphone"), ["a mobile phone", "a smartphone"]),
    (("tai nghe", "earphone", "headphone"), ["a pair of earphones", "headphones"]),
    (("my pham", "cosmetic", "serum", "cream"), ["a cosmetic product", "a cosmetic bottle"]),
    (("do an", "food", "snack"), ["a food item", "a snack package"]),
]

_MODEL = None
_PREPROCESS = None
_TOKENIZER = None
_DEVICE = None
_OPEN_CLIP = None
_TORCH = None


def extract_image_urls(images: Any) -> List[str]:
    urls: List[str] = []
    if not images:
        return urls

    def is_image_url(value: str) -> bool:
        clean = value.split("?", 1)[0].lower()
        if clean.endswith(VIDEO_EXTENSIONS):
            return False
        return clean.endswith(IMAGE_EXTENSIONS) or "image" in clean or "photo" in clean or "review" in clean

    image_items = images if isinstance(images, list) else [images]
    for item in image_items:
        if isinstance(item, str) and item.startswith(("http://", "https://")) and is_image_url(item):
            urls.append(item)
        elif isinstance(item, dict):
            for key in ("full_path", "url", "path", "image_url", "thumbnail_url"):
                value = item.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")) and is_image_url(value):
                    urls.append(value)
                    break
    return urls


def cache_image(url: str, timeout: int = 15) -> Path:
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(url.split("?")[0]).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = hashlib.sha256(url.encode("utf-8")).hexdigest() + suffix
    output = IMAGE_CACHE_DIR / filename
    if output.exists() and output.stat().st_size > 0:
        return output

    session = requests.Session()
    session.trust_env = False
    response = session.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    output.write_bytes(response.content)
    return output


def load_clip_model() -> None:
    global _MODEL, _PREPROCESS, _TOKENIZER, _DEVICE, _OPEN_CLIP, _TORCH
    if _MODEL is not None:
        return
    try:
        import open_clip
        import torch
    except Exception as exc:  # pragma: no cover - optional dependency guard
        raise RuntimeError("open_clip_torch/torch chua duoc cai dat.") from exc

    _OPEN_CLIP = open_clip
    _TORCH = torch
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    _MODEL, _, _PREPROCESS = open_clip.create_model_and_transforms(
        MODEL_NAME,
        pretrained=PRETRAINED,
        device=_DEVICE,
    )
    _MODEL.eval()
    _TOKENIZER = open_clip.get_tokenizer(MODEL_NAME)


def clip_image_text_score(image_path: Path, text: str) -> float:
    load_clip_model()
    if not text.strip():
        return 50.0

    assert _MODEL is not None
    assert _PREPROCESS is not None
    assert _TOKENIZER is not None
    assert _DEVICE is not None
    assert _TORCH is not None

    image = _PREPROCESS(Image.open(image_path).convert("RGB")).unsqueeze(0).to(_DEVICE)
    tokens = _TOKENIZER([text]).to(_DEVICE)

    with _TORCH.no_grad():
        image_features = _MODEL.encode_image(image)
        text_features = _MODEL.encode_text(tokens)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        similarity = (image_features @ text_features.T).item()

    # CLIP cosine thường nằm quanh 0.15-0.35 cho ảnh khớp text. Đưa về thang 0-100.
    return max(0.0, min(100.0, (similarity + 0.05) / 0.40 * 100.0))


def clip_image_label_scores(image_path: Path, labels: List[str]) -> Dict[str, float]:
    load_clip_model()
    if not labels:
        return {}

    assert _MODEL is not None
    assert _PREPROCESS is not None
    assert _TOKENIZER is not None
    assert _DEVICE is not None
    assert _TORCH is not None

    image = _PREPROCESS(Image.open(image_path).convert("RGB")).unsqueeze(0).to(_DEVICE)
    tokens = _TOKENIZER(labels).to(_DEVICE)

    with _TORCH.no_grad():
        image_features = _MODEL.encode_image(image)
        text_features = _MODEL.encode_text(tokens)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        logits = 100.0 * image_features @ text_features.T
        probs = logits.softmax(dim=-1).squeeze(0).detach().cpu().tolist()

    return {label: round(float(prob) * 100.0, 2) for label, prob in zip(labels, probs)}


def clip_image_image_score(left_path: Path, right_path: Path) -> float:
    load_clip_model()

    assert _MODEL is not None
    assert _PREPROCESS is not None
    assert _DEVICE is not None
    assert _TORCH is not None

    left = _PREPROCESS(Image.open(left_path).convert("RGB")).unsqueeze(0).to(_DEVICE)
    right = _PREPROCESS(Image.open(right_path).convert("RGB")).unsqueeze(0).to(_DEVICE)

    with _TORCH.no_grad():
        left_features = _MODEL.encode_image(left)
        right_features = _MODEL.encode_image(right)
        left_features = left_features / left_features.norm(dim=-1, keepdim=True)
        right_features = right_features / right_features.norm(dim=-1, keepdim=True)
        similarity = (left_features @ right_features.T).item()

    # Ảnh review thường là góc chụp thật, khác ảnh catalog; scale vừa phải để tránh phạt nhầm.
    return max(0.0, min(100.0, (similarity - 0.25) / 0.45 * 100.0))


def perceptual_hash(image_path: Path) -> Optional[str]:
    try:
        import imagehash
        return str(imagehash.phash(Image.open(image_path).convert("RGB")))
    except Exception:
        return None


def build_product_prompt(product: Optional[Dict[str, Any]], review: Dict[str, Any], override_text: str = "") -> str:
    if override_text.strip():
        return override_text.strip()
    if product:
        parts = [
            str(product.get("title") or ""),
            str(product.get("category") or ""),
            str(product.get("description") or ""),
        ]
        text = " ".join(part for part in parts if part.strip()).strip()
        if text:
            return text
    sku = str(review.get("sku_info") or "")
    if sku:
        return f"product matching this SKU information: {sku}"
    return "the product that the customer bought"


def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_text.lower()


def contains_keyword(text: str, keyword: str) -> bool:
    clean_keyword = normalize_search_text(keyword)
    if " " in clean_keyword:
        return clean_keyword in text
    return re.search(rf"\b{re.escape(clean_keyword)}\b", text) is not None


def expected_product_labels(product: Optional[Dict[str, Any]], product_text: str = "") -> List[str]:
    joined = normalize_search_text(" ".join(
        str(value or "")
        for value in [
            product_text,
            (product or {}).get("title"),
            (product or {}).get("category"),
            (product or {}).get("description"),
        ]
    ))

    labels: List[str] = []
    for keywords, rule_labels in PRODUCT_LABEL_RULES:
        if any(contains_keyword(joined, keyword) for keyword in keywords):
            labels.extend(rule_labels)

    if not labels:
        labels.append("the purchased product")
    return list(dict.fromkeys(labels))


def review_claim_type(review_text: str) -> str:
    clean = normalize_search_text(review_text)
    for claim_type, keywords, _labels in CLAIM_EVIDENCE_RULES:
        if any(contains_keyword(clean, keyword) for keyword in keywords):
            return claim_type
    return "general_product_feedback"


def expected_claim_evidence_labels(review_text: str) -> Tuple[str, List[str]]:
    claim_type = review_claim_type(review_text)
    for rule_claim_type, _keywords, labels in CLAIM_EVIDENCE_RULES:
        if rule_claim_type == claim_type:
            return claim_type, labels
    return claim_type, ["the purchased product", "the product described in the review", "a customer review product photo"]


def claim_evidence_analysis(image_path: Path, review_text: str) -> Dict[str, Any]:
    claim_type, expected_labels = expected_claim_evidence_labels(review_text)
    labels = list(dict.fromkeys(expected_labels + GENERAL_OTHER_EVIDENCE_LABELS))
    scores = clip_image_label_scores(image_path, labels)
    expected_scores = {label: scores[label] for label in expected_labels if label in scores}
    other_scores = {label: scores[label] for label in GENERAL_OTHER_EVIDENCE_LABELS if label in scores}

    best_expected = max(expected_scores.items(), key=lambda item: item[1]) if expected_scores else ("", 0.0)
    best_other = max(other_scores.items(), key=lambda item: item[1]) if other_scores else ("", 0.0)
    margin = best_expected[1] - best_other[1]

    if best_expected[1] >= 45 and margin >= 8:
        status = "claim_evidence_likely_matches"
    elif best_expected[1] >= 30 and margin >= -10:
        status = "claim_evidence_unclear"
    else:
        status = "claim_evidence_mismatch_risk"

    return {
        "review_claim_type": claim_type,
        "expected_evidence_labels": expected_labels,
        "claim_evidence_score": round(best_expected[1], 2),
        "claim_evidence_status": status,
        "best_claim_label": best_expected[0],
        "best_other_evidence_label": best_other[0],
        "claim_evidence_margin": round(margin, 2),
        "claim_label_scores": scores,
    }


def category_match_analysis(image_path: Path, expected_labels: List[str]) -> Dict[str, Any]:
    labels = list(dict.fromkeys(expected_labels + DISTRACTOR_LABELS))
    scores = clip_image_label_scores(image_path, labels)
    expected = {label: scores[label] for label in expected_labels if label in scores}
    distractors = {label: scores[label] for label in DISTRACTOR_LABELS if label in scores}

    best_expected = max(expected.items(), key=lambda item: item[1]) if expected else ("", 0.0)
    best_distractor = max(distractors.items(), key=lambda item: item[1]) if distractors else ("", 0.0)
    margin = best_expected[1] - best_distractor[1]

    if best_expected[1] >= 45 and margin >= 10:
        status = "category_likely_matches"
    elif best_distractor[1] >= 45 and margin <= -10:
        status = "category_mismatch_risk"
    else:
        status = "category_unclear"

    return {
        "expected_labels": expected_labels,
        "best_expected_label": best_expected[0],
        "best_expected_score": round(best_expected[1], 2),
        "best_other_label": best_distractor[0],
        "best_other_score": round(best_distractor[1], 2),
        "category_margin": round(margin, 2),
        "category_status": status,
        "label_scores": scores,
    }


def summarize_category_results(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    category_details = [item for item in details if item.get("status") == "ok" and item.get("category_status")]
    if not category_details:
        return {
            "category_status": "category_not_checked",
            "best_expected_label": "",
            "best_other_label": "",
            "category_mismatch_count": 0,
        }

    mismatch_items = [item for item in category_details if item.get("category_status") == "category_mismatch_risk"]
    best_item = max(category_details, key=lambda item: float(item.get("category_score") or 0))
    worst_item = min(category_details, key=lambda item: float(item.get("category_margin") or 0))

    if mismatch_items:
        status = "category_mismatch_risk"
    elif any(item.get("category_status") == "category_likely_matches" for item in category_details):
        status = "category_likely_matches"
    else:
        status = "category_unclear"

    return {
        "category_status": status,
        "best_expected_label": best_item.get("best_expected_label", ""),
        "best_other_label": worst_item.get("best_other_label", ""),
        "category_mismatch_count": len(mismatch_items),
        "category_margin": worst_item.get("category_margin", 0),
    }


def product_image_urls(product: Optional[Dict[str, Any]]) -> List[str]:
    if not product:
        return []
    return extract_image_urls(product.get("product_images") or product.get("images") or product.get("image_urls"))


def analyze_review_image_relevance(
    review: Dict[str, Any],
    product: Optional[Dict[str, Any]] = None,
    product_text: str = "",
    max_images: int = 2,
) -> Dict[str, Any]:
    urls = extract_image_urls(review.get("images") or review.get("review_images") or review.get("image_urls"))
    if not urls:
        return {
            "has_images": False,
            "image_relevance_score": 50.0,
            "image_evidence_status": "no_review_image",
            "images_analyzed": 0,
            "details": [],
        }

    prompt = build_product_prompt(product, review, product_text)
    expected_labels = expected_product_labels(product, product_text)
    product_urls = product_image_urls(product)
    product_paths = []
    for product_url in product_urls[:2]:
        try:
            product_paths.append(cache_image(product_url))
        except Exception:
            continue

    details = []
    scores = []

    for url in urls[:max_images]:
        try:
            image_path = cache_image(url)
            text_score = clip_image_text_score(image_path, prompt)
            review_text = str(review.get("review_text") or review.get("content") or review.get("comment") or "")
            claim_result = claim_evidence_analysis(image_path, review_text)
            category_result = category_match_analysis(image_path, expected_labels)
            image_match_scores = [clip_image_image_score(image_path, product_path) for product_path in product_paths]
            product_image_score = sum(image_match_scores) / len(image_match_scores) if image_match_scores else None
            category_score = category_result["best_expected_score"]
            claim_score = claim_result["claim_evidence_score"]
            if product_image_score is None:
                score = 0.45 * text_score + 0.30 * category_score + 0.25 * claim_score
            else:
                blended_score = 0.35 * product_image_score + 0.25 * text_score + 0.20 * category_score + 0.20 * claim_score
                score = max(blended_score, text_score * 0.75)
            claim_allows_packaging = claim_result["review_claim_type"] == "shipping_packaging_damage"
            if category_result["category_status"] == "category_mismatch_risk" and not claim_allows_packaging:
                score = min(score, 34.0)
            if claim_result["claim_evidence_status"] == "claim_evidence_mismatch_risk":
                score = min(score, 44.0)
            scores.append(score)
            details.append(
                {
                    "url": url,
                    "cached_path": str(image_path),
                    "score": round(score, 2),
                    "text_score": round(text_score, 2),
                    "product_image_score": round(product_image_score, 2) if product_image_score is not None else None,
                    "category_score": round(category_score, 2),
                    "category_status": category_result["category_status"],
                    "best_expected_label": category_result["best_expected_label"],
                    "best_other_label": category_result["best_other_label"],
                    "category_margin": category_result["category_margin"],
                    **{key: value for key, value in claim_result.items() if key != "claim_label_scores"},
                    "image_hash": perceptual_hash(image_path),
                    "status": "ok",
                }
            )
        except Exception as exc:
            details.append({"url": url, "score": None, "status": f"error: {exc}"})

    valid_scores = [score for score in scores if score is not None]
    if not valid_scores:
        return {
            "has_images": True,
            "image_relevance_score": 55.0,
            "image_evidence_status": "image_present_not_verified",
            "images_analyzed": 0,
            "details": details,
        }

    final_score = sum(valid_scores) / len(valid_scores)
    category_summary = summarize_category_results(details)
    claim_summary = summarize_claim_results(details)
    if final_score >= 75:
        status = "image_likely_matches_product"
    elif final_score >= 55:
        status = "image_possibly_matches_product"
    elif final_score >= 35:
        status = "image_unclear"
    else:
        status = "image_may_not_match_product"

    return {
        "has_images": True,
        "image_relevance_score": round(final_score, 2),
        "image_evidence_status": status,
        "images_analyzed": len(valid_scores),
        "product_images_used": len(product_paths),
        "product_prompt": prompt,
        "expected_product_labels": expected_labels,
        **category_summary,
        **claim_summary,
        "details": details,
    }


def summarize_claim_results(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    claim_details = [item for item in details if item.get("status") == "ok" and item.get("claim_evidence_status")]
    if not claim_details:
        return {
            "review_claim_type": "not_checked",
            "expected_evidence_labels": [],
            "claim_evidence_score": 0,
            "claim_evidence_status": "claim_evidence_not_checked",
            "best_claim_label": "",
            "best_other_evidence_label": "",
        }

    best_item = max(claim_details, key=lambda item: float(item.get("claim_evidence_score") or 0))
    mismatch_count = sum(1 for item in claim_details if item.get("claim_evidence_status") == "claim_evidence_mismatch_risk")
    if mismatch_count == len(claim_details):
        status = "claim_evidence_mismatch_risk"
    elif any(item.get("claim_evidence_status") == "claim_evidence_likely_matches" for item in claim_details):
        status = "claim_evidence_likely_matches"
    else:
        status = "claim_evidence_unclear"

    return {
        "review_claim_type": best_item.get("review_claim_type", "general_product_feedback"),
        "expected_evidence_labels": best_item.get("expected_evidence_labels", []),
        "claim_evidence_score": best_item.get("claim_evidence_score", 0),
        "claim_evidence_status": status,
        "best_claim_label": best_item.get("best_claim_label", ""),
        "best_other_evidence_label": best_item.get("best_other_evidence_label", ""),
        "claim_mismatch_count": mismatch_count,
    }
