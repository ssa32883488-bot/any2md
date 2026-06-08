# any2md GUI

Windows 桌面壳层，调用 `../engine` 中的转换引擎。

**普通用户**：使用 [Releases](https://github.com/ssa32883488-bot/any2md/releases) 中的便携包，无需阅读本文。

## 开发

```powershell
cd gui
$env:PYTHONPATH = "."
python -m app.main
```

## 打包

```powershell
.\build.ps1
```

输出 `dist\any2md_stage\`，打 zip 后作为 Release 附件发布。

更多说明见 [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md)。
