# Bộ PlantUML cuối cho Chương 3

Đây là bộ cuối đã được đặt tên rõ ràng theo thứ tự đưa vào báo cáo.

## Danh sách nên dùng

1. `FINAL_01_use_case_tong_quat.puml`
2. `FINAL_02_phan_ra_chuc_nang.puml`
3. `FINAL_03_use_case_nhap_link.puml`
4. `FINAL_04_use_case_thu_thap_va_phan_tich.puml`
5. `FINAL_05_use_case_dashboard.puml`
6. `FINAL_06_activity_tong_quat.puml`
7. `FINAL_07_sequence_keo_du_lieu.puml`
8. `FINAL_08_component_kien_truc.puml`
9. `FINAL_09_class_domain_model.puml`
10. `FINAL_10_erd_mongodb.puml`
11. `FINAL_11_sequence_doc_link_san_pham.puml`
12. `FINAL_12_sequence_mo_phien_san.puml`
13. `FINAL_13_sequence_thu_thap_review.puml`
14. `FINAL_14_sequence_phan_tich_text.puml`
15. `FINAL_15_sequence_kiem_dinh_hinh_anh.puml`
16. `FINAL_16_sequence_tinh_diem_tin_cay.puml`
17. `FINAL_17_sequence_xem_dashboard.puml`
18. `FINAL_18_sequence_loc_review_theo_sao.puml`
19. `FINAL_19_activity_thu_thap_chi_tiet.puml`
20. `FINAL_20_activity_phan_tich_chi_tiet.puml`
21. `FINAL_21_state_ingestion_job.puml`
22. `FINAL_22_deployment_trien_khai.puml`
23. `FINAL_23_use_case_seller_loc_review.puml`
24. `FINAL_24_use_case_seller_xem_bang_chung_anh.puml`
25. `FINAL_25_use_case_qtv_quan_tri.puml`

## Gợi ý đưa vào báo cáo

```text
3.1 Phân tích yêu cầu hệ thống
    Hình FINAL_01 - Use case tổng quát
    Hình FINAL_02 - Phân rã chức năng

3.2 Đặc tả chức năng chính
    Hình FINAL_03 - Use case nhập link sản phẩm
    Hình FINAL_04 - Use case thu thập và phân tích review
    Hình FINAL_05 - Use case dashboard
    Hình FINAL_23 - Use case lọc review theo số sao
    Hình FINAL_24 - Use case xem bằng chứng hình ảnh
    Hình FINAL_25 - Use case quản trị hệ thống

3.3 Luồng xử lý nghiệp vụ
    Hình FINAL_06 - Activity tổng quát
    Hình FINAL_07 - Sequence kéo dữ liệu
    Hình FINAL_11 - Sequence đọc link sản phẩm
    Hình FINAL_12 - Sequence mở phiên sàn
    Hình FINAL_13 - Sequence thu thập review
    Hình FINAL_14 - Sequence phân tích text
    Hình FINAL_15 - Sequence kiểm định hình ảnh
    Hình FINAL_16 - Sequence tính điểm tin cậy
    Hình FINAL_17 - Sequence xem dashboard
    Hình FINAL_18 - Sequence lọc review theo sao
    Hình FINAL_19 - Activity thu thập chi tiết
    Hình FINAL_20 - Activity phân tích chi tiết

3.4 Thiết kế kiến trúc hệ thống
    Hình FINAL_08 - Component hệ thống
    Hình FINAL_21 - State ingestion job
    Hình FINAL_22 - Deployment triển khai

3.5 Thiết kế dữ liệu
    Hình FINAL_09 - Class/domain model
    Hình FINAL_10 - ERD MongoDB
```

## Cách render

Dùng PlantUML Online:

https://www.plantuml.com/plantuml/uml/

Hoặc nếu đã có `plantuml.jar`:

```powershell
java -jar plantuml.jar "C:\Users\Admin\Desktop\DoANTotNghiep\pod-ai-evaluator\docs\plantuml\FINAL_*.puml"
```
