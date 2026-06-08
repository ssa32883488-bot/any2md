# 开发者说明

面向从源码运行、打包发布或参与贡献的开发者。普通用户请阅读根目录 [README.md](../README.md)。

## 仓库结构

```
any2md/
├── engine/           # 转换引擎
├── src/any2md/       # CLI 包
├── scripts/          # 安装脚本、压测
├── testset/          # 压测清单（测试文件需本地生成）
└── gui/              # 桌面应用与 PyInstaller 配置
```

## 从源码运行 GUI

```powershell
cd gui
$env:PYTHONPATH = "."
python -m app.main
```

需本机已安装 Python 3.9–3.13 与 GPU 版 Paddle（见 `scripts/setup.ps1`）。

## 打包发布（供 Releases 使用）

```powershell
cd gui
.\build.ps1
```

产物：`gui\dist\any2md_stage\` — 将整个文件夹打成 **`any2md-windows.zip`** 上传到 GitHub Releases，供用户解压即用。

发布前建议在本机验证：首次向导 → 下载模型 → 转换样例 PDF/docx。

## 命令行引擎

```powershell
# 安装依赖（仅开发机）
.\scripts\setup.ps1

python engine\run_parser.py -i sample.pdf -o .\output --route auto -m .\models
```

## 压测

```powershell
python scripts\generate_testset.py
python scripts\make_scan_pdfs.py
.\scripts\run_stress_test.ps1 -Route text -Chunk
```

详见 [testset/README.md](../testset/README.md)。

## 环境变量

| 变量 | 说明 |
|------|------|
| `ANY2MD_PYTHON` | 指定 Python 可执行文件路径（脚本 / 打包用） |
