import re
from typing import Dict, List, Tuple, Any

POSITIVE_WORDS = {
    "love", "loved", "loving", "great", "excellent", "awesome", "perfect", "beautiful",
    "cute", "soft", "comfy", "comfortable", "well", "good", "nice", "happy", "vibrant",
    "best", "fast", "amazing", "durable", "worth", "recommend", "pleased", "favorite",
    "high quality", "superb", "brilliant", "cozy", "satisfying", "flawless",
    "tot", "on", "dep", "xinh", "hai long", "rat hai long", "cuc ki hai long",
    "ok", "mem", "thom", "ben", "dang tien", "nen mua", "de thuong", "chat luong",
    "giao nhanh", "dong goi ky", "dung mo ta", "ung y"
}

NEGATIVE_WORDS = {
    "bad", "terrible", "poor", "faded", "peeling", "peel", "shrunk", "shrink", "scratchy",
    "itchy", "delayed", "delay", "ripped", "rip", "broken", "cheap", "thin", "flimsy",
    "blurry", "blur", "regret", "awful", "tight", "loose", "disappointed", "disappointing",
    "waste", "horrible", "ugly", "smell", "rough", "overpriced", "faded", "fades", "small", "big",
    "te", "xau", "that vong", "khong hai long", "loi", "rach", "mop", "meo",
    "cham", "tre", "mong", "nho", "rong", "chat", "bong", "phai mau", "sai mau",
    "khong dung mo ta", "kem", "doi tra", "khong nen mua", "hoi te", "bi hu"
}

ASPECT_KEYWORDS: Dict[str, List[str]] = {
    "design": ["design", "graphic", "artwork", "look", "pattern", "cute", "style", "art", "illustration", "mau ma", "thiet ke", "kieu", "form", "hoa tiet"],
    "size": ["size", "sizing", "fit", "small", "large", "tight", "loose", "baggy", "medium", "xl", "xxl", "runs small", "runs large", "kich co", "kich thuoc", "nho", "rong", "chat", "vua", "form"],
    "material": ["material", "fabric", "cotton", "polyester", "texture", "cloth", "blend", "vai", "chat vai", "chat lieu", "mem", "mong", "day"],
    "quality": ["quality", "craft", "cheap", "flimsy", "well made", "poorly made", "stitching", "chat luong", "duong may", "loi", "rach", "kem"],
    "price": ["price", "cost", "expensive", "cheap", "affordable", "value", "worth", "overpriced", "gia", "re", "dat", "dang tien"],
    "personalization": ["personalize", "personalized", "custom", "customized", "name", "custom text", "custom name", "dog name"],
    "shipping": ["shipping", "ship", "delivery", "delivered", "arrived", "packaging", "package", "transit", "giao hang", "van chuyen", "giao", "ship", "dong goi", "hop", "mop", "meo", "cham", "tre"],
    "durability": ["wash", "washed", "shrink", "shrunk", "shrinkage", "durable", "durability", "faded", "lasting", "giat", "co rut", "bong", "phai mau", "ben"],
    "printing": ["print", "printed", "printing", "ink", "blurry", "crisp", "decal", "iron on", "peeling", "hinh in", "muc in", "in", "bong", "mo", "nhat"],
    "color": ["color", "colour", "shade", "bright", "vibrant", "dull", "dark", "mau", "mau sac", "sai mau", "lech mau", "dam", "nhat"],
    "comfort": ["comfortable", "comfort", "soft", "itchy", "scratchy", "cozy", "comfy", "wear", "thoai mai", "mac", "ngua", "mem"],
}


def analyze_text_sentiment(text: str) -> Tuple[str, float]:
    lower = text.lower()
    pos_score = sum(1 for w in POSITIVE_WORDS if re.search(rf"\b{re.escape(w)}\b", lower))
    neg_score = sum(1 for w in NEGATIVE_WORDS if re.search(rf"\b{re.escape(w)}\b", lower))

    if "not " in lower or "n't " in lower or "never " in lower:
        pos_score, neg_score = neg_score, pos_score

    complaint_markers = ["but", "however", "except", "moi toi", "nhung", "tuy nhien", "co dieu"]
    if neg_score > 0 and any(marker in lower for marker in complaint_markers):
        return "negative", min(1.0, 0.7 + 0.1 * neg_score)

    if pos_score > neg_score:
        return "positive", min(1.0, 0.6 + 0.1 * (pos_score - neg_score))
    elif neg_score > pos_score:
        return "negative", min(1.0, 0.6 + 0.1 * (neg_score - pos_score))
    else:
        return "neutral", 0.5


def extract_aspect_sentiments(review_text: str) -> List[Dict[str, Any]]:
    results = []
    clauses = re.split(r"[.!?,\n;]+", review_text)
    detected_aspects = set()

    for aspect, keywords in ASPECT_KEYWORDS.items():
        for clause in clauses:
            clause_clean = clause.strip().lower()
            if not clause_clean:
                continue

            matches_aspect = any(re.search(rf"\b{re.escape(kw)}\b", clause_clean) for kw in keywords)
            if matches_aspect and aspect not in detected_aspects:
                sentiment, conf = analyze_text_sentiment(clause_clean)
                results.append({
                    "aspect": aspect,
                    "sentiment": sentiment,
                    "confidence": conf,
                })
                detected_aspects.add(aspect)
                break

    return results
