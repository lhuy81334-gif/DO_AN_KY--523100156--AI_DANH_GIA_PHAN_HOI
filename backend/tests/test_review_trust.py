from app.ml.review_trust import analyze_review_trust


def test_high_rating_with_complaint_is_flagged():
    result = analyze_review_trust({
        "rating": 4,
        "review_text": "Hang on moi toi giao hang hoi meo",
        "sku_info": "black/L",
    })

    assert "high_rating_with_complaint" in result["flags"]
    assert "shipping" in result["negative_aspects"]
    assert result["use_for_text_analysis"] is True


def test_rating_only_review_is_not_used_for_text_analysis():
    result = analyze_review_trust({"rating": 5, "review_text": ""})

    assert "rating_only_review" in result["flags"]
    assert result["use_for_rating_stats"] is True
    assert result["use_for_text_analysis"] is False


def test_low_image_relevance_reduces_evidence_strength():
    result = analyze_review_trust({
        "rating": 1,
        "review_text": "Ao bi rach duong may",
        "images": ["review-image.jpg"],
        "image_relevance_score": 12,
        "verified_purchase": True,
        "sku_info": "white/M",
    })

    assert "image_may_not_match_product" in result["flags"]
    assert result["image_evidence_score"] == 12
    assert result["use_as_strong_evidence"] is False


def test_relevant_image_and_specific_text_can_be_strong_evidence():
    result = analyze_review_trust({
        "rating": 2,
        "review_text": "Ao bi rach duong may sau mot lan giat, hinh in bi bong",
        "images": ["review-image.jpg"],
        "image_relevance_score": 90,
        "verified_purchase": True,
        "sku_info": "black/L",
    })

    assert result["review_trust_score"] >= 70
    assert result["use_as_strong_evidence"] is True


def test_negative_review_with_image_not_supporting_claim_is_flagged():
    result = analyze_review_trust({
        "rating": 1,
        "review_text": "Giao hang bi mop hop",
        "images": ["review-image.jpg"],
        "image_relevance_score": 35,
        "claim_evidence_status": "claim_evidence_mismatch_risk",
    })

    assert "image_does_not_support_review_claim" in result["flags"]
    assert "negative_review_image_does_not_support_claim" in result["flags"]
