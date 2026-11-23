友商金融政策监测 Agent（独立版）
=====================================

一个能自己跑的抓取程序：不依赖豆包/任何内容平台，只要有 Python 和一台能上网的机器，
就能每天定时去 9 家车企官网抓金融方案、比对变化、生成那张 8 列宽表。

目录
----
agent.py            主程序（抓取 + 比对 + 落盘 + 出表）
render.py           单文件 HTML 渲染（纯表格，无脚本、无平台注入、无水印）
baseline.json       初始基线（9 品牌 / 15 行，来自 11 月第三周已核定的表）
data/               每周一个 JSON，如 2026-W47.json
out/                生成结果：友商金融政策动态-周报表.html
run.sh / run.bat    一键运行（Linux/macOS、Windows）
requirements.txt    Python 依赖
.github/workflows/crawl.yml   GitHub Actions 每天 4 次自动跑 + 发布 Pages

最快上手
--------
方式一（推荐，零安装、不怕离职）：GitHub Actions
  1) 新建一个自己的仓库（私有公开都行），把本目录整个传上去；
  2) 仓库 Settings → Pages → Source 选 “GitHub Actions”；
  3) Actions 里手动点一次 “友商金融政策周报” → Run workflow，确认能出表；
  4) 之后每天 09/12/16/18（北京时间）自动跑，产出发布到
     https://<你的用户名>.github.io/<仓库名>/  （首页 index.html 即周报宽表）
  链接是你自己的，跟豆包账号无关；离职、换电脑都不影响。
  注意：GitHub 免费版私有仓库不支持 Pages，要公开网页链接需转公开仓库、
  升级 Pro 或另配静态托管，详见 GITHUB_SETUP.md。

方式二：自己电脑（Windows）本地跑
  1) 装 Python 3.10+（python.org，安装时勾 Add to PATH）；
  2) 命令行执行：
       pip install -r requirements.txt
       python -m playwright install chromium
  3) 双击 run.bat，或命令行 python agent.py
  4) 定时：任务计划程序 → 创建任务 → 每天 09:00/12:00/16:00/18:00
     操作填：程序 python，参数 C:\...\agent.py，起始于本目录

方式三：自己的服务器 / 云主机
  crontab -e
  0 9,12,16,18 * * * cd /path/to/agent && python3 agent.py >> crawl.log 2>&1

常用参数
--------
python3 agent.py                  抓 9 家 → 更新本周 JSON → 出表
python3 agent.py --render-only    只用手上的 JSON 重出表（不联网）
python3 agent.py --only 小鹏 特斯拉  只抓指定品牌（调试用）
python3 agent.py --week 2026-W48  指定周文件
python3 agent.py --verbose        打印每步细节

口径（和之前那张表一致，没有放宽）
----------------------------------
1. 抓不到不编：沿用上期值，并把原因写进“官网核对”备注（含试过的 URL 与具体报错），
   不写“反爬”这种含糊结论。品牌不会被整体冒充成已核对。
2. 三档状态：checked（具体车型/方案页抓到且费率机构对得上）、
   partial（只核到部分车型 / 数值有变化待确认 / 有探测页 404）、pending（完全没取到）。
3. 五个业务列只放方案语言；条款原文（财金〔2026〕1号、贴息政策期限、
   消费贴息最高5000元、近似折算年化利率、最终以金融机构审核为准 等）一律过滤，
   只当证据，不进表格。
4. 周度变化按政策窗口起始日判定：起始日落在本周 → 「本周新增 起M.D」；
   此前 → 「延续 起M.D」；上周事件（如新车上市）标 last 并注明不计本周。
5. 数值变化不当场改文案：脚本把差异（费率/首付/期数/贴息/窗口）写进「周度变化」列，
   并把该品牌降级为 partial，提示人工确认表述。表格永远有官网证据，不被脚本臆造。

想改抓取对象 / 口径
------------------
- 改 URL、加车型页、设成必须用浏览器渲染：改 agent.py 顶部 SOURCES 字典
  （url、js、anchors、probe、scope、force_partial）。
- 改品牌与行的对应（例如比亚迪/腾势同属一个 section）：SECTION_OF。
- 改禁词：BANNED 列表。
- 改页面样式：render.py 里的 TEMPLATE（纯表格，不引入任何外部资源）。

已知边界（都是实测结论，不是推测）
----------------------------------
- 乐道 finance.onvo.cn：是绑心愿单的试算器，直访只返回占位页（Vue 初始化成功但正文不渲染），
  独立抓取取不到费率；因此乐道沿用上期值，蔚来 section 记 partial 并附原因。
- 比亚迪 元UP：/models/yuanup 与 /models/yuan-up 两个路径均 404，脚本会实测并把 404 写进备注。
- 腾势 D9 / N8L：车型页 404，沿用上期值。
- 极氪：无头浏览器能拿到计算器默认车型（001 Max）完整试算；下拉逐个切换在无头环境不稳定，
  已保留 zeekr_script()，把 SOURCES["极氪"]["models"] 设成 True 即可尝试逐车型（失败会记在备注里）。
- 蔚来：官网无品牌级金融方案正文，仅新闻页；新闻里若出现金融/权益条目需人工补，脚本只作为证据。
- 特斯拉：静态抓不到「优惠政策」段，脚本自动切浏览器渲染；活动期起始日官网不写，沿用上期。

数据文件结构（沿用既有格式）
--------------------------
{
 "week": "11月第三周（11.16–11.22）",
 "updated": "11.20",
 "checked_at_all": "2026-11-20 11:40 抓取",
 "judge_window": "11.16–11.22",
 "sections": [
   { "brand": "小鹏",
     "rows": [ { "sub": null, "rates": ["2.49%-2.79%"], "orgs": [["中建交招平…", 1]],
                "change": {"items": [{"kind": "carry", "since": "11.1", "text": ""}]},
                "subsidy": "有", "policy": ["…"] } ],
     "verified": {"status": "checked", "url": "...", "checked_at": "2026-11-20 11:40",
                  "note": "...", "gap": ""},
     "fingerprint": {"小鹏": ["费率2.49%", "首付0万", ...]} }
 ],
 "digest_lead": "本次抓取摘要"
}
fingerprint 是本周抓到的数字指纹，用来和上次比；同一周内重复抓取只更新 checked_at 与备注。

飞书在线表格同步（发布线 weekly/）
----------------------------------
- `weekly/sync_sheet.py`：把当周宽表写入固定飞书工作簿「友商金融政策动态周报」，
  每周一个子表（子表名=周报周次标题），同周重复跑只覆盖该子表，历史周次保留。
- 工作簿 token / url 存在 `weekly/sheet_config.json`，复用同一工作簿，不新建第二个表。
- 页面右上角「在飞书表格中打开」按钮链接取自该配置；定时流水线顺序：
  `python3 agent.py` → 复制本周 JSON 到 `weekly/data/` → `python3 weekly/build_weekly.py`
  → `python3 weekly/sync_sheet.py` → lark-cli 复发布同一 app。
