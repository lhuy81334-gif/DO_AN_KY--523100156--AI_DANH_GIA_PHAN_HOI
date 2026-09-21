from app.db.repositories.platform_repo import PlatformRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.repositories.product_repo import ProductRepository


def test_mongodb_collections_and_relational_ids(db_session):
    platform = PlatformRepository(db_session).get_or_create("tiki", "Tiki")
    shop = ShopRepository(db_session).get_or_create(platform.id, "SHOP_1", "Dog Lover Apparel")
    ProductRepository(db_session).bulk_upsert_products([{
        "platform_id": platform.id,
        "shop_id": shop.id,
        "external_product_id": "PROD_1",
        "title": "Golden Retriever Mom T-Shirt",
        "normalized_title": "golden retriever mom t-shirt",
        "category": "T-Shirt",
        "price": 19.99,
    }])
    product = ProductRepository(db_session).get_by_external_id(platform.id, "PROD_1")
    assert product is not None
    assert product.shop_id == shop.id
    assert product.platform_id == platform.id
