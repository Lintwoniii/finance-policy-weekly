# GitHub 仓库与自动更新说明

- 仓库：https://github.com/Lintwoniii/finance-policy-weekly （**公开**，main 分支）
- 周报页面：https://lintwoniii.github.io/finance-policy-weekly/

定时抓取跑在 GitHub Actions 上，不依赖豆包会话、不依赖个人电脑；账号和仓库在本人名下，
换电脑、离职都不影响。

## 当前已完成

- 代码、基线数据、提炼规则、Actions 工作流已推送 main。
- 工作流「友商金融政策周报」状态 active：每天北京时间 09:00 / 12:00 / 16:00 / 18:00
  自动抓取；也可在 Actions 页面手动 Run workflow。
- Pages 已开启（Source = GitHub Actions），Actions 变量 `ENABLE_PAGES=true`，
  每次跑完自动把 `out/` 发布到上面的周报页面。
- 已验证：依赖安装、抓取出表、提交数据、上传产物、Pages 部署全部 success，页面可打开。

## 说明与边界

- 仓库为公开：抓取代码、基线数据表任何人可见；公开仓库 Actions 分钟数不限。
- Actions 跑在 GitHub 数据中心 IP 上，部分官网反爬可能比家用网络更严；
  抓不到的品牌沿用上期值并标 partial/pending 与具体原因，不会编造。
- 本仓库**不含飞书在线表同步**：那一步依赖云端 lark-cli 登录态。
  要在 Actions 里接飞书，需另存 CLI 凭证为仓库 Secrets 并补一个同步步骤。
- 定时频率、品牌清单、费率口径都在 `agent.py` 顶部与 `提炼规则.md`，改完提交即可。

## 本地再次推送（需要时）

```powershell
cd finance-policy-weekly
git add .
git commit -m "更新"
git push
```

首次在新机器推送时，用浏览器授权或 PAT（勾选 `repo`、`workflow` 权限）完成认证。
