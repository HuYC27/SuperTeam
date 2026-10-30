# 第一次发布 SuperTeam 到 GitHub

这份说明把“上传源码”和“上传安装包”分开，因为它们在 GitHub 中属于两种不同对象：源码进入仓库并形成提交记录；约 350 MB 的安装包和便携包进入 `v1.0.0` Release。不要把安装包拖进仓库的 Code 页面。

## 你会看到的本地文件

构建完成后，`publish\v1.0.0` 中有两个重要目录：

- `repository`：这是要用 GitHub Desktop 发布的完整源码仓库。
- `release-assets`：这里的安装包、便携包和 `SHA256SUMS.txt` 要在网页的 Releases 页面上传。

`repository` 已经排除了聊天、附件、头像、API 配置、运行数据库、本机扫描图标、日志和构建缓存。不要为了“文件齐全”再把项目根目录里的 `data`、`work`、`dist`、`releases` 或 `ui\assets\installed-app-随机编号.png` 复制进去。

## 第一步：注册并登录

1. 打开 <https://github.com/>，注册账号并验证邮箱。
2. 安装 [GitHub Desktop](https://desktop.github.com/)。
3. 打开 GitHub Desktop，选择 **File → Options → Accounts → Sign in**，浏览器会弹出授权页面。

## 第二步：把准备好的源码加入 GitHub Desktop

1. 在 GitHub Desktop 选择 **File → Add local repository**。
2. 点 **Choose**，选择 SuperTeam 项目中的 `publish\v1.0.0\repository` 文件夹。
3. 如果界面显示该目录已经是 Git 仓库，直接点 **Add repository**。
4. 左下角的历史中应能看到 `release: prepare SuperTeam v1.0.0 public source` 这条提交；顶部当前分支应为 `main`。
5. 点击顶部 **Publish repository**。
6. Repository name 填 `SuperTeam`；Description 建议填写：

   `A Windows workspace where desktop AIs discuss, execute and verify together. 桌面多 AI 协作工作台。`

7. **取消勾选 Keep this code private**，这样才是公开源码。
8. Owner 选择你自己的 GitHub 账号，然后点 **Publish repository**。

发布后进入网页仓库，README、图片、LICENSE、SECURITY 和源代码会自动显示。不要再逐个点击 Add file 上传；以后修改文件，只需在 GitHub Desktop 写提交说明，点击 **Commit to main**，再点击 **Push origin**。

## 第三步：建立 v1.0.0 Release

1. 在仓库网页右侧找到 **Releases**，点击 **Create a new release**。
2. Tag 选择或输入 `v1.0.0`。如果 GitHub 提示创建新标签，确认从 `main` 创建。
3. Release title 填 `SuperTeam v1.0.0`。
4. 打开本地 `release-assets` 文件夹，把下面三个文件拖入 Release 的附件区域：

   - `SuperTeam-Setup-1.0.0.exe`
   - `SuperTeam-1.0.0-Windows-x64-Portable.zip`
   - `SHA256SUMS.txt`

5. Release 正文复制 `docs\RELEASE_NOTES_v1.0.0.md` 的内容。
6. 首次发布建议先勾选 **Set as a pre-release**，自己从 GitHub 下载并安装一次；确认无误后编辑 Release，取消预发布并设为 latest。

## 第四步：修改仓库主页信息

在仓库网页右侧 **About** 区域点击齿轮：

- Description：`Desktop multi-AI collaboration workspace · 桌面多 AI 协作工作台`
- Topics：`ai`、`multi-agent`、`desktop-app`、`windows`、`llm`、`codex`、`deepseek`、`ai-collaboration`
- 勾选 Releases；如果以后建立官网再填写 Website。

进入 **Settings → General → Features**，启用 Issues；进入 **Settings → Code security and analysis**，启用 Private vulnerability reporting（如果当前账号提供该选项）。

## 第五步：别人如何验证安装包

在 Release 页面告诉下载者同时下载 `SHA256SUMS.txt`。下载后在 PowerShell 中运行：

```powershell
Get-FileHash .\SuperTeam-Setup-1.0.0.exe -Algorithm SHA256
```

显示的哈希必须与 `SHA256SUMS.txt` 中同名文件的一行完全相同。由于首版暂未购买 Windows Authenticode 代码签名证书，SmartScreen 可能提示“未知发布者”；哈希校验可以验证文件是否与本次 Release 上传的文件一致，但不能替代商业代码签名。

## 以后更新版本

不要删除旧 Release。更新到 1.0.1 时，修改代码并提交，生成新安装包，建立标签 `v1.0.1` 和新的 Release。版本号采用“主版本.功能版本.修复版本”：兼容性修复使用 1.0.1，新功能可以使用 1.1.0，发生不兼容的大改动才使用 2.0.0。

