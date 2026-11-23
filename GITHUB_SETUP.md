# 推到 GitHub 并自动更新（一次性配置）

这套仓库不依赖豆包、不依赖你的个人电脑：定时抓取跑在 GitHub Actions 上，
表格页托管在 GitHub Pages。账号和仓库在你名下，换电脑、离职都不影响。

## 一、你需要准备的东西

- 一个 GitHub 账号（github.com 注册）。
- 本机装 git（https://git-scm.com/download/win），或用 GitHub Desktop。
- 推送时用「浏览器登录授权」或 Personal Access Token（PAT，勾选 `repo` 权限）。

## 二、建仓库并推送（命令行）

1. 在 GitHub 网页上 **New repository**：
   - 名字：`finance-policy-weekly`
   - 私有（Private）即可；不要勾选 "Add a README" / .gitignore，保持空仓库。
2. 在本目录下执行（把 `<你的用户名>` 换成实际账号名）：

   ```powershell
   git init
   git add .
   git commit -m "init: 友商金融政策监测"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/finance-policy-weekly.git
   git push -u origin main
   ```

   首次推送弹窗里授权 GitHub；若用 PAT，密码处粘贴 token，不要填登录密码。

## 三、打开 Pages（一次性）

仓库 **Settings → Pages**：

- Build and deployment → Source 选 **GitHub Actions**（不要选 Deploy from a branch）。

## 四、手动跑一次验证

仓库 **Actions** 标签页 → 选「友商金融政策周报」→ **Run workflow**。
跑完后访问：

```
https://<你的用户名>.github.io/finance-policy-weekly/
```

应直接打开周报宽表。之后每天 09:00 / 12:00 / 16:00 / 18:00（北京时间）自动跑。

## 五、额度与边界

- 私有仓库：Actions 每月 **2000 分钟**免费额度；本任务每天 4 次、每次约 3–6 分钟，
  月用量远低于额度。公开仓库 Actions 分钟数不限。
- Actions 跑在 GitHub 数据中心 IP 上，部分官网反爬可能比家用网络更严；
  抓不到的品牌会沿用上期值并标 partial/pending 与具体原因，不会编造。
- 本仓库**不含飞书在线表同步**：那一步依赖云端 lark-cli 登录态。
  要在 Actions 里接飞书，需另存 CLI 凭证为仓库 Secrets 并补一个同步步骤。
- 定时频率、品牌清单、费率口径都在 `agent.py` 顶部与 `提炼规则.md`，改完提交即可。
