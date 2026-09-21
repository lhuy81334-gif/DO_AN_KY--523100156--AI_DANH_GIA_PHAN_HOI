import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT_DIR / "docs"
MDJ_PATH = DOCS_DIR / "seller_feedback_use_case.mdj"
PUML_PATH = DOCS_DIR / "seller_feedback_use_case.puml"


def ref(identifier: str) -> dict[str, str]:
    return {"$ref": identifier}


def element(element_type: str, identifier: str, parent: str, name: str, owned: list[dict] | None = None) -> dict:
    item = {
        "_type": element_type,
        "_id": identifier,
        "_parent": ref(parent),
        "name": name,
    }
    if owned is not None:
        item["ownedElements"] = owned
    return item


def actor_view(identifier: str, diagram_id: str, model_id: str, left: int, top: int) -> dict:
    return {
        "_type": "UMLActorView",
        "_id": identifier,
        "_parent": ref(diagram_id),
        "model": ref(model_id),
        "font": "Arial;13;0",
        "left": left,
        "top": top,
        "width": 90,
        "height": 92,
    }


def use_case_view(identifier: str, diagram_id: str, model_id: str, left: int, top: int, width: int = 230) -> dict:
    return {
        "_type": "UMLUseCaseView",
        "_id": identifier,
        "_parent": ref(diagram_id),
        "model": ref(model_id),
        "font": "Arial;13;0",
        "left": left,
        "top": top,
        "width": width,
        "height": 48,
    }


def association(identifier: str, parent_id: str, actor_id: str, use_case_id: str) -> dict:
    return {
        "_type": "UMLAssociation",
        "_id": identifier,
        "_parent": ref(parent_id),
        "end1": {
            "_type": "UMLAssociationEnd",
            "_id": f"{identifier}_end1",
            "_parent": ref(identifier),
            "reference": ref(actor_id),
        },
        "end2": {
            "_type": "UMLAssociationEnd",
            "_id": f"{identifier}_end2",
            "_parent": ref(identifier),
            "reference": ref(use_case_id),
        },
    }


def association_view(identifier: str, diagram_id: str, model_id: str, tail_view_id: str, head_view_id: str, points: str) -> dict:
    return {
        "_type": "UMLAssociationView",
        "_id": identifier,
        "_parent": ref(diagram_id),
        "model": ref(model_id),
        "font": "Arial;13;0",
        "tail": ref(tail_view_id),
        "head": ref(head_view_id),
        "lineStyle": 1,
        "points": points,
        "showVisibility": True,
        "showEndOrder": "hide",
    }


def build_mdj() -> dict:
    project_id = "PROJECT_SELLER_FEEDBACK"
    model_id = "MODEL_SELLER_FEEDBACK"
    diagram_id = "DIAGRAM_USE_CASE_MAIN"
    subject_id = "SUBJECT_SELLER_FEEDBACK"

    actors = {
        "seller": ("ACTOR_SELLER", "Seller", "VIEW_ACTOR_SELLER", 45, 210),
        "admin": ("ACTOR_ADMIN", "Admin", "VIEW_ACTOR_ADMIN", 45, 585),
    }
    use_cases = [
        ("UC_INPUT_LINK", "Dán link sản phẩm", "VIEW_UC_INPUT_LINK", 300, 120, "seller"),
        ("UC_REQUEST_FETCH", "Yêu cầu thu thập đánh giá", "VIEW_UC_REQUEST_FETCH", 300, 190, "seller"),
        ("UC_VIEW_DASHBOARD", "Xem dashboard phân tích", "VIEW_UC_VIEW_DASHBOARD", 300, 260, "seller"),
        ("UC_SEARCH_SUSPICIOUS", "Tra cứu review nghi ngờ", "VIEW_UC_SEARCH_SUSPICIOUS", 300, 330, "seller"),
        ("UC_VIEW_DETAIL", "Xem chi tiết review", "VIEW_UC_VIEW_DETAIL", 300, 400, "seller"),
        ("UC_COPY_REPLY", "Sao chép phản hồi gợi ý", "VIEW_UC_COPY_REPLY", 300, 470, "seller"),
        ("UC_MANAGE_USERS", "Quản lý tài khoản và phân quyền", "VIEW_UC_MANAGE_USERS", 300, 585, "admin"),
        ("UC_MANAGE_API", "Quản lý cấu hình API/cookie", "VIEW_UC_MANAGE_API", 610, 585, "admin"),
        ("UC_PARSE_LINK", "Nhận diện sàn và mã sản phẩm", "VIEW_UC_PARSE_LINK", 660, 120, ""),
        ("UC_FETCH_API", "Gọi API lấy review", "VIEW_UC_FETCH_API", 660, 190, ""),
        ("UC_SAVE_MONGO", "Chuẩn hóa và lưu MongoDB", "VIEW_UC_SAVE_MONGO", 660, 260, ""),
        ("UC_TRUST", "Phân tích độ tin cậy review", "VIEW_UC_TRUST", 660, 330, ""),
        ("UC_IMAGE", "Kiểm định bằng chứng hình ảnh", "VIEW_UC_IMAGE", 660, 400, ""),
        ("UC_RANK", "Xếp hạng mức cần kiểm tra", "VIEW_UC_RANK", 660, 470, ""),
    ]

    associations = []
    association_views = []
    for index, (uc_id, _name, uc_view_id, uc_left, uc_top, actor_key) in enumerate(use_cases, start=1):
        if not actor_key:
            continue
        actor_id, _actor_name, actor_view_id, actor_left, actor_top = actors[actor_key]
        assoc_id = f"ASSOC_{index:02d}"
        associations.append(association(assoc_id, actor_id, actor_id, uc_id))
        association_views.append(
            association_view(
                f"VIEW_{assoc_id}",
                diagram_id,
                assoc_id,
                actor_view_id,
                uc_view_id,
                f"{actor_left + 90}:{actor_top + 45};{uc_left}:{uc_top + 24}",
            )
        )

    owned_views = [
        {
            "_type": "UMLUseCaseSubjectView",
            "_id": "VIEW_SUBJECT_SELLER_FEEDBACK",
            "_parent": ref(diagram_id),
            "model": ref(subject_id),
            "font": "Arial;13;1",
            "left": 230,
            "top": 70,
            "width": 750,
            "height": 610,
            "nameLabel": None,
        }
    ]
    owned_views.extend(actor_view(view_id, diagram_id, actor_id, left, top) for actor_id, _name, view_id, left, top in actors.values())
    owned_views.extend(use_case_view(view_id, diagram_id, uc_id, left, top) for uc_id, _name, view_id, left, top, _actor in use_cases)
    owned_views.extend(association_views)

    diagram = {
        "_type": "UMLUseCaseDiagram",
        "_id": diagram_id,
        "_parent": ref(model_id),
        "name": "Use Case Tổng Quát",
        "ownedViews": owned_views,
    }
    model_elements = [diagram, element("UMLUseCaseSubject", subject_id, model_id, "Phân tích phản hồi khách hàng")]
    model_elements.extend(element("UMLActor", actor_id, model_id, name, owned=[]) for actor_id, name, _view_id, _left, _top in actors.values())
    model_elements.extend(element("UMLUseCase", uc_id, model_id, name) for uc_id, name, _view_id, _left, _top, _actor in use_cases)
    for assoc in associations:
        actor = next(item for item in model_elements if item["_id"] == assoc["_parent"]["$ref"])
        actor["ownedElements"].append(assoc)

    return {
        "_type": "Project",
        "_id": project_id,
        "name": "Seller Feedback Intelligence",
        "ownedElements": [
            {
                "_type": "UMLModel",
                "_id": model_id,
                "_parent": ref(project_id),
                "name": "Use Case Model",
                "ownedElements": model_elements,
            }
        ],
    }


def build_puml() -> str:
    return """@startuml
left to right direction
actor Seller
actor Admin

rectangle "Phân tích phản hồi khách hàng" {
  usecase "Dán link sản phẩm" as UC1
  usecase "Yêu cầu thu thập đánh giá" as UC2
  usecase "Xem dashboard phân tích" as UC3
  usecase "Tra cứu review nghi ngờ" as UC4
  usecase "Xem chi tiết review" as UC5
  usecase "Sao chép phản hồi gợi ý" as UC6

  usecase "Nhận diện sàn và mã sản phẩm" as SYS1
  usecase "Gọi API lấy review" as SYS2
  usecase "Chuẩn hóa và lưu MongoDB" as SYS3
  usecase "Phân tích độ tin cậy review" as SYS4
  usecase "Kiểm định bằng chứng hình ảnh" as SYS5
  usecase "Xếp hạng mức cần kiểm tra" as SYS6

  usecase "Quản lý tài khoản và phân quyền" as AD1
  usecase "Quản lý cấu hình API/cookie" as AD2
}

Seller --> UC1
Seller --> UC2
Seller --> UC3
Seller --> UC4
Seller --> UC5
Seller --> UC6

Admin --> AD1
Admin --> AD2

UC1 ..> SYS1 : <<include>>
UC2 ..> SYS2 : <<include>>
SYS2 ..> SYS3 : <<include>>
SYS3 ..> SYS4 : <<include>>
SYS4 ..> SYS5 : <<include>>
SYS4 ..> SYS6 : <<include>>
UC3 ..> SYS6 : <<include>>
UC4 ..> UC5 : <<extend>>
@enduml
"""


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    MDJ_PATH.write_text(json.dumps(build_mdj(), ensure_ascii=False, indent=2), encoding="utf-8")
    PUML_PATH.write_text(build_puml(), encoding="utf-8")
    print(f"Created {MDJ_PATH}")
    print(f"Created {PUML_PATH}")


if __name__ == "__main__":
    main()
