from app.ml.image_evidence import (
    build_product_prompt,
    expected_claim_evidence_labels,
    expected_product_labels,
    extract_image_urls,
    product_image_urls,
    review_claim_type,
    summarize_category_results,
)
from app.services.product_metadata import extract_product_image_urls


def test_extract_image_urls_from_tiki_shape():
    urls = extract_image_urls([
        {"id": 1, "full_path": "https://example.com/review.jpg", "status": "approved"},
        {"id": 2, "full_path": ""},
    ])

    assert urls == ["https://example.com/review.jpg"]


def test_product_prompt_prefers_manual_text():
    prompt = build_product_prompt(
        {"title": "Generic product"},
        {"sku_info": "black/L"},
        override_text="ao thun den in hinh meo",
    )

    assert prompt == "ao thun den in hinh meo"


def test_product_prompt_uses_product_metadata():
    prompt = build_product_prompt(
        {"title": "Ao thun cotton", "category": "fashion", "description": "mau den"},
        {},
    )

    assert "Ao thun cotton" in prompt
    assert "fashion" in prompt


def test_product_image_urls_reads_product_images():
    urls = product_image_urls({"product_images": ["https://example.com/product.jpg"]})

    assert urls == ["https://example.com/product.jpg"]


def test_expected_product_labels_detects_shirt():
    labels = expected_product_labels({"title": "Ao thun cotton nam", "category": "fashion"})

    assert "a shirt" in labels
    assert "a t-shirt" in labels


def test_expected_product_labels_detects_pants():
    labels = expected_product_labels({"title": "Quan jean nam"})

    assert "a pair of pants or trousers" in labels


def test_expected_product_labels_does_not_match_ao_inside_sao():
    labels = expected_product_labels({"title": "Sach khoa hoc nau an", "description": "tai sao mon an ngon"})

    assert "a book" in labels
    assert "a shirt" not in labels


def test_summarize_category_results_promotes_mismatch_to_top_level():
    summary = summarize_category_results([
        {
            "status": "ok",
            "category_status": "category_mismatch_risk",
            "category_score": 3,
            "best_expected_label": "a shirt",
            "best_other_label": "a pair of pants or trousers",
            "category_margin": -80,
        }
    ])

    assert summary["category_status"] == "category_mismatch_risk"
    assert summary["best_expected_label"] == "a shirt"
    assert summary["best_other_label"] == "a pair of pants or trousers"


def test_review_claim_type_detects_shipping_damage():
    assert review_claim_type("San pham ok nhung giao hang bi mop hop") == "shipping_packaging_damage"


def test_expected_claim_evidence_labels_for_product_defect():
    claim_type, labels = expected_claim_evidence_labels("Ao bi rach duong may va in bi bong")

    assert claim_type == "product_damage_or_defect"
    assert "a damaged product" in labels


def test_extract_product_image_urls_from_tiki_html():
    html = '<meta property="og:image" content="https://salt.tikicdn.com/cache/750x750/ts/product/aa/bb/product.jpg">'

    urls = extract_product_image_urls(html, "tiki")

    assert urls == ["https://salt.tikicdn.com/cache/750x750/ts/product/aa/bb/product.jpg"]


def test_extract_product_image_urls_from_lazada_html():
    html = '{"image":"//img.lazcdn.com/g/p/abc/product.png_720x720q80.png_.webp"}'

    urls = extract_product_image_urls(html, "lazada")

    assert urls == ["https://img.lazcdn.com/g/p/abc/product.png_720x720q80.png_.webp"]


def test_extract_product_image_urls_from_tiktok_shop_html():
    html = '{"image":"https://p16-oec-sg.ibyteimg.com/tos-alisg-i-aphluv4xwc-sg/product.webp"}'

    urls = extract_product_image_urls(html, "tiktok_shop")

    assert urls == ["https://p16-oec-sg.ibyteimg.com/tos-alisg-i-aphluv4xwc-sg/product.webp"]
