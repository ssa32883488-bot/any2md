# 测试检查清单

| 文件 | 期望 Markdown 特征 | 切分期望 |
|------|-------------------|----------|
| 01_multilevel_sections | ## 一、二、三、 | 按章节分块 |
| 02_two_column | 双栏段落顺序正确 | 段落/章节块 |
| 03_three_column | 三栏短段落 | 多块 |
| 04_layout_table_body | 表格+## 标题，非单行巨表 | 按 ## 切分 |
| 05_mixed_stress | 5 章+附录，含表格 | 多块，batch 测试 |
| 06_excel_tables | 多 sheet 表格 | 可选切分 |
| *_scan.pdf | OCR 路径 | 与 digital 对比 |