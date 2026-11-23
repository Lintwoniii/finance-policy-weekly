# GitHub 仓库与自动更新说明

仓库：https://github.com/Lintwoniii/finance-policy-weekly （私有，main 分支）
定时抓取跑在 GitHub Actions 上，不依赖豆包会话、不依赖个人电脑；账号和仓库在本人名下，
换电脑、离职都不影响。

## 当前已完成

- 代码、基线数据、提炼规则、Actions 工作流已推送 main。
- 工作流「友商金融政策周报」状态 active：每天北京时间 09:00 / 12:00 / 16:00 / 18:00
  自动抓取；也可在 Actions 页面手动 Run workflow。
- 已验证：依赖安装、抓取出表、提交本周数据与产物步骤均可在 Runner 上跑通。

## Pages 公开网页链接（当前未开）

GitHub 免费版**私有仓库不支持 Pages**（API 返回 422：plan does not support Pages）。
因此现在仓库里只有代码和 `out/` 产物，还没有一个公开可打开的网页地址。
要拿到 Pages 链接，三选一：

1. **仓库转公开**（推荐，零成本）：Settings → General → Danger Zone → Change visibility
   改为 Public；然后 Settings → Pages → Source 选 GitHub Actions；
   再在仓库 Settings → Secrets and variables → Actions → Variables 新建
   `ENABLE_PAGES=true`。Pages 地址为
   `https://lintwoniii.github.io/finance-policy-weekly/`。
2. **GitHub Pro**（约 $4/月）：解锁私有仓库 Pages，其余同上。
3. **另配静态托管**：每次 Actions 出表后，把 `out/` 目录拖到 Vercel / Netlify /
   自己的 OSS 静态站发布，仓库保持私有。

> 工作流里上传产物和 Pages 部署两个步骤都挂在变量 `ENABLE_PAGES` 上，
> 默认不执行；等 Pages 可用后把该变量置为 `true` 即可，不用改 YAML。

## 本地再次推送（需要时）

```powershell
cd finance-policy-weekly
git add .
git commit -m "更新"
git push
```

首次在新机器推送时，用浏览器授权或 PAT（勾选 `repo`、`workflow` 权限）完成认证。

## 额度与边界

- 私有仓库 Actions 每月 **2000 分钟**免费额度；本任务每天 4 次、每次约 3–6 分钟，
  月用量远低于额度。公开仓库 Actions 分钟数不限。
- Actions 跑在 GitHub 数据中心 IP 上，部分官网反爬可能比家用网络更严；
  抓不到的品牌沿用上期值并标 partial/pending 与具体原因，不会编造。
- 本仓库**不含飞书在线表同步**：那一步依赖云端 lark-cli 登录态。
  要在 Actions 里接飞书，需另存 CLI 凭证为仓库 Secrets 并补一个同步步骤。
- 定时频率、品牌清单、费率口径都在 `agent.py` 顶部与 `提炼规则.md`，改完提交即可。
