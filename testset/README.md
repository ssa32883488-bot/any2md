# any2md 压力测试集

测试文件**不在 Git 仓库中**，需在本机生成。

## 生成测试文件

```powershell
cd C:\any2md

# 需要 Word 或 WPS（用于导出 PDF）
python scripts\generate_testset.py

# 由 digital PDF 生成扫描件（OCR 压测）
python scripts\make_scan_pdfs.py
```

## 目录说明

| 目录 | 内容 |
|------|------|
| `office/` | Word / Excel 源文件 + 配套 PDF |
| `digital/` | 数字 PDF（适合 CPU / auto 快路径） |
| `scan/` | 扫描风格 PDF（`*_scan.pdf`，适合 OCR 压测） |
| `expected/` | 验收检查清单 |
| `output/` | 压测输出（勿提交 Git） |

## 压测命令

```powershell
.\scripts\run_stress_test.ps1 -Route text -Chunk   # Office + 语义切分
.\scripts\run_stress_test.ps1 -Route auto        # 数字 PDF
.\scripts\run_stress_test.ps1 -Route ocr         # 扫描 PDF
```

## 测试用例

| 文件 | 考察点 |
|------|--------|
| 01_multilevel_sections | 多级标题 |
| 02_two_column | 双栏排版 |
| 03_three_column | 三栏排版 |
| 04_layout_table_body | 布局表格 vs 数据表格 |
| 05_mixed_stress | 混合复杂文档 |
| 06_excel_tables | 多 Sheet Excel |

验收清单见 [`expected/checklist.md`](expected/checklist.md)。
