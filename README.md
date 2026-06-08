# any2md

把 **PDF、Word、Excel、扫描件、图片** 转成结构清晰的 Markdown，可选 **语义切分**（适合 RAG / 知识库）。Windows 便携版，解压即用。

---

## 下载与使用

### 1. 下载

在 GitHub **[Releases](https://github.com/ssa32883488-bot/any2md/releases)** 下载最新 **`any2md-windows.zip`**，解压到任意目录（建议 **非 C 盘**，例如 `D:\any2md\`）。

### 2. 首次打开

双击 **`any2md.exe`**，按向导完成：

1. **检测 NVIDIA 显卡**（扫描件 OCR 需要 GPU，推荐 ≥ 8 GB 显存）
2. **选择模型存放目录**（勿选 C 盘）
3. **下载模型**（约 2 GB，国内 CDN，仅需一次）
4. 进入主界面

### 3. 日常使用

1. 添加 PDF / docx / xlsx / 图片  
2. 选择解析模式（一般选 **智能**）  
3. 点击 **开始转换**  
4. 在 `output/` 下按时间戳文件夹查看结果  

```
output/
└── 2026-06-08_171311/
    ├── md/       # 完整 Markdown
    ├── json/     # 切分元数据（若启用语义切分）
    ├── chunks/   # 分块 Markdown
    └── assets/   # 图片等资源
```

需要 **语义切分** 时，在菜单中下载 BGE 模型并勾选相应选项即可（向导外另有一次性下载，约 400 MB）。

---

## 系统要求

| 项目 | 要求 |
|------|------|
| 系统 | Windows 10 / 11 64 位 |
| 显卡 | NVIDIA GPU（扫描 PDF / 图片 OCR 必需） |
| 显存 | 建议 ≥ 8 GB |
| 磁盘 | 程序约 500 MB + 模型约 2.5 GB + 输出空间 |

**说明：** Word、Excel、可复制文字的数字 PDF 可在无 OCR 模型时走 CPU 快路径；**扫描件和图片** 必须完成向导中的 OCR 模型下载。

---

## 支持格式

| 格式 | 说明 |
|------|------|
| PDF | 智能识别数字版 / 扫描版 |
| docx / xlsx | 保留标题、表格结构 |
| png / jpg / … | 走 OCR 解析 |

旧版 `.doc` / `.xls` 请先在 Office 中另存为 docx / xlsx。

---

## 解析模式

| 模式 | 适用场景 |
|------|----------|
| **智能** | 默认；自动选择快路径或 OCR |
| **文本** | 只要 docx / xlsx / 数字 PDF，速度最快 |
| **OCR** | 扫描件、图片、复杂版式 PDF |

---

## 常见问题

**首次启动卡在下载？**  
检查网络；模型走国内 BOS 镜像。可关闭代理后重试，或在 **设置 → 重新运行首次设置** 中更换模型目录后重新下载。

**提示需要 NVIDIA 显卡？**  
本程序 OCR 依赖 NVIDIA GPU。仅转换 Word / Excel 时仍可使用，但扫描 PDF 必须满足显卡要求。

**不要把数据放 C 盘？**  
首次向导里把模型目录选到 D 盘等；`output/` 可在主界面指定。

**OCR 失败或显存不足？**  
关闭占用 GPU 的其他程序；复杂扫描件建议保证 8 GB 以上显存。

---

## 目录说明（便携版）

解压后的文件夹可整体拷贝（U 盘、换电脑）：

```
any2md/
├── any2md.exe       # 主程序
├── config.json      # 首次向导完成后自动生成
├── models/          # 模型（向导下载）
├── output/          # 转换结果
└── _internal/       # 运行时依赖，请勿删除
```

---

## 开源与反馈

- 许可证：[MIT](LICENSE)  
- Issue / PR 欢迎提交  
- 从源码构建与二次开发说明见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

---

## 致谢

- [PaddleOCR-VL](https://www.paddleocr.ai/) — 文档版面分析与 VLM 解析
