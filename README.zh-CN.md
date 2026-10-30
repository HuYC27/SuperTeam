# SuperTeam 中文说明

> **让桌面上的 AI，真正成为一支队伍。**

SuperTeam 是一个 Windows 多 AI 协作桌面工作台。它将私聊、群聊、文件、技能、记忆、权限和任务记录放在同一个界面中。你可以继续使用已经购买并登录的桌面 AI 账号，也可以为暂时无法稳定转接的软件配置兼容 API。

与普通“多模型客户端”不同，SuperTeam 不默认让所有模型重复回答。群聊可以由两位成员先分别提出方案，再敲定执行者，执行后交给另一位成员验收；普通问候则自然回复，不触发任务分配。`@某成员` 只调用指定成员，`@全体成员` 才让全部成员独立回答。

## 下载

前往 [GitHub Releases](../../releases/latest)：

- 普通用户下载 `SuperTeam-Setup-1.0.0.exe`。
- 免安装使用下载 `SuperTeam-1.0.0-Windows-x64-Portable.zip`。
- 下载后用 PowerShell 执行 `Get-FileHash .\SuperTeam-Setup-1.0.0.exe -Algorithm SHA256`，与 `SHA256SUMS.txt` 核对。

v1.0 社区安装包暂未进行商业代码签名，因此 Windows 可能出现 SmartScreen 提示。校验哈希后再运行，不要从非 GitHub Release 的未知地址下载。

## 接入边界

当前真实验证过 Codex、DeepSeek Harness 与 WorkBuddy 的文本通道；豆包兼容 API 已验证文本、图片理解、文件正文上下文与单张图片生成。千问原软件可以正常响应测试消息，但 SuperTeam 自动桌面转接尚未被标记为端到端通过。发现一个软件、能够打开它、能够自动收发消息和能够安全操作电脑是四个不同层级，界面会分别显示。

SuperTeam 不附带任何账号或密钥。API Key 通过 Windows DPAPI 加密保存在本机；公开源码和安装包均不包含开发机器上的聊天、头像、附件、软件扫描结果或 API 配置。

## 开发与贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。公开 Issue 不得包含真实 API Key、私人聊天、未公开研究材料或受试者数据。

主 README 同时包含中英文功能说明：[返回 README](README.md)。

