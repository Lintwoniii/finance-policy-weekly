#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data/<周>.json 渲染成单文件 HTML（纯表格，无脚本、无统计条、无平台依赖）。"""
import re
from html import escape


def esc(t):
    return escape(str(t), quote=True)


# 首付短语标蓝：首付X万起 / X万首付 / X%首付 / 0首付(起)
DP_PATTERNS = [
    r"首付[\d.]+万起?",
    r"[\d.]+(?:-[\d.]+)?万首付",
    r"[\d.]+%(?:-[\d.]+%)?首付",
    r"0首付起?",
]


def key(t):
    out = esc(t)
    for pat in DP_PATTERNS:
        out = re.sub(pat, r'<span class="dp">\g<0></span>', out)
    return out


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__WEEK__ 友商金融政策动态</title>
<style>
:root{
  --ink:#17222e; --sub:#5a6673; --faint:#8994a0;
  --line:#dcdfe4; --line-strong:#c3c9d1;
  --head:#e9eff8; --brand-bg:#f6f8fb;
  --green:#136c45; --amber:#8a5a12; --accent:#1e5a94;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#fff;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;font-size:13px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{padding:16px 14px 26px;max-width:1760px;margin:0 auto}
h1{text-align:center;font-size:19px;font-weight:700;letter-spacing:.2px;margin-bottom:6px}
.subtxt{text-align:center;font-size:12px;color:var(--faint);margin-bottom:12px}
.tablebox{overflow-x:auto;border:1px solid var(--line)}
table{width:100%;border-collapse:collapse;table-layout:fixed;min-width:1290px;font-size:12.5px}
col.c1{width:74px} col.c2{width:76px} col.c3{width:104px}
col.c4{width:184px} col.c5{width:162px} col.c6{width:86px} col.c7{width:auto} col.c8{width:80px}
thead th{background:var(--head);color:#2c3a4a;font-weight:650;font-size:12.5px;padding:9px 10px;border-bottom:1px solid var(--line-strong);border-right:1px solid var(--line);text-align:center;white-space:nowrap}
tbody th{background:var(--brand-bg);font-weight:650;font-size:13px;text-align:center;border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:10px 6px;vertical-align:middle}
tbody td{border-bottom:1px solid var(--line);border-right:1px solid var(--line);padding:9px 10px;vertical-align:top}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
td:last-child,thead th:last-child{border-right:0}
.c-sub{color:var(--sub);text-align:center;font-size:12.5px;white-space:nowrap;background:var(--brand-bg)}
.c-rate{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.rate-line{display:block;line-height:1.7}
.c-org{color:var(--sub);line-height:1.65}
.org-line{display:block}
.c-change{text-align:center}
.chg{color:var(--faint);white-space:nowrap}
.chg-sub{display:block;font-size:11px;color:var(--faint);margin-top:3px}
.ctag{display:inline-block;font-size:11px;font-weight:650;padding:1px 6px;border-radius:3px;margin-bottom:4px;color:#5f6b78;background:#eceff3}
.ctag.new{color:var(--amber);background:#fbf2df}
.ctag.fail{color:#b23b3b;background:#fbeaea}
.ctext{display:block;font-size:11.5px;line-height:1.55;text-align:left}
.c-subsidy{text-align:center}
.chip{display:inline-block;padding:2px 9px;border-radius:4px;font-size:12px;font-weight:650}
.chip.yes{color:var(--green);background:#e9f4ee}
.chip.no{color:#8a3b2f;background:#f6ece9}
.c-policy{line-height:1.62}
.p-line{display:block}
.dp{color:var(--accent)}
.new-car{font-weight:700;text-decoration:underline;text-underline-offset:2px}
.c-verify{text-align:center;vertical-align:middle!important}
.vchip{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11.5px;font-weight:650;white-space:nowrap}
.vchip.ok{color:var(--green);background:#e9f4ee}
.vchip.part{color:var(--amber);background:#fbf2df}
.vchip.wait{color:#6b7683;background:#eceff3}
.sheet-btn{display:inline-block;margin-left:10px;padding:3px 12px;border:1px solid var(--accent);border-radius:5px;color:var(--accent);font-size:12px;font-weight:600;text-decoration:none;white-space:nowrap}
.sheet-btn:hover{background:#eef4fb}
.foot{margin-top:10px;font-size:11.5px;color:var(--faint);line-height:1.75}
@media (max-width:900px){table{font-size:12px;min-width:1180px}}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}.tablebox{overflow:visible;border:0}table{min-width:0;font-size:9pt}}
</style>
</head>
<body>
<div class="wrap">
  <h1>__WEEK__ 友商金融政策动态<span style="font-size:13px;font-weight:500;color:#8994a0;margin-left:8px">（__UPDATED__）</span></h1>
  <p class="subtxt">9 家官网实抓 · 最近一次抓取 __LAST_CRAWL__ · 官网核对 __N_CHECKED__ 已核对 / __N_PARTIAL__ 部分核对 / __N_PENDING__ 待核 __DOC_BTN__</p>
  <div class="tablebox">
    <table>
      <colgroup>
        <col class="c1" /><col class="c2" /><col class="c3" /><col class="c4" />
        <col class="c5" /><col class="c6" /><col class="c7" /><col class="c8" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col" colspan="2">品牌</th>
          <th scope="col">基础对客费率</th>
          <th scope="col">合作机构</th>
          <th scope="col">周度变化</th>
          <th scope="col">是否有贴息</th>
          <th scope="col">贴息政策</th>
          <th scope="col">官网核对</th>
        </tr>
      </thead>
      <tbody>
__ROWS__
      </tbody>
    </table>
  </div>
  <p class="foot">数据来源：小鹏、特斯拉、理想、蔚来/乐道、极氪、小米、鸿蒙智行、比亚迪/腾势、零跑官网金融方案页，逐页实抓；抓不到即标「部分核对/待核对」并沿用上期值，不补数字。<br />
  变化口径：政策窗口起始日落在 __JUDGE_WINDOW__ 记「本周新增」；此前开启记「延续 起 M.D」。本页由本地/云端定时任务自行抓取生成，不依赖任何内容平台。</p>
</div>
</body>
</html>
"""


def render_html(data):
    rows_html = []
    sections = data["sections"]
    n_checked = sum(1 for s in sections if s["verified"]["status"] == "checked")
    n_partial = sum(1 for s in sections if s["verified"]["status"] == "partial")
    n_pending = sum(1 for s in sections if s["verified"]["status"] == "pending")

    doc_url = (data.get("doc_url") or "").strip()
    doc_btn = ('<a class="sheet-btn" href="%s" target="_blank" rel="noopener">在飞书文档中打开</a>' % esc(doc_url)) if doc_url else ""

    for sec in sections:
        rows = sec["rows"]
        has_sub = any(r.get("sub") for r in rows)
        span = len(rows)
        for i, r in enumerate(rows):
            is_new = any(it.get("text") and "上新" in it["text"] for it in r["change"]["items"])
            tds = []
            if i == 0:
                colspan = "" if has_sub else ' colspan="2"'
                tds.append(f'<th class="c-brand" rowspan="{span}"{colspan} scope="rowgroup">{esc(sec["brand"])}</th>')
            if has_sub:
                tds.append(f'<td class="c-sub">{esc(r.get("sub") or "")}</td>')

            tds.append('<td class="c-rate">' + "".join(
                f'<span class="rate-line">{esc(x)}</span>' for x in r["rates"]) + "</td>")

            orgs = []
            for item in r["orgs"]:
                org, rspan = (item[0], item[1]) if isinstance(item, list) else (str(item), 1)
                attr = f' rowspan="{rspan}"' if rspan > 1 else ""
                orgs.append(f'<span class="org-line"{attr}>{esc(org)}</span>')
            tds.append(f'<td class="c-org">{"".join(orgs)}</td>')

            chg = []
            for it in r["change"]["items"]:
                k, since, text = it["kind"], it.get("since", ""), it.get("text", "")
                if k == "carry":
                    chg.append('<span class="chg">延续</span>')
                elif k == "new":
                    chg.append('<span class="ctag new">本周新增</span>')
                elif k == "change":
                    chg.append('<span class="ctag new">变化</span>')
                elif k == "fail":
                    chg.append('<span class="ctag fail">无法爬取</span>')
                    continue
                elif k == "none":
                    chg.append('<span class="chg">延续</span>')
                    continue
                else:
                    chg.append('<span class="ctag last">上周</span>')
                if text:
                    chg.append(f'<span class="ctext">{key(text)}</span>')
                if since:
                    chg.append(f'<span class="chg-sub">起 {esc(since)}</span>')
            tds.append('<td class="c-change">' + "".join(chg) + "</td>")

            chip = "yes" if r["subsidy"] == "有" else "no"
            tds.append(f'<td class="c-subsidy"><span class="chip {chip}">{esc(r["subsidy"])}</span></td>')
            def render_p(line):
                cls = "p-line new-car" if is_new else "p-line"
                if "：" not in line:
                    return f'<span class="{cls}">{key(line)}</span>'
                head, sep, body = line.partition("：")
                return f'<span class="{cls}">{esc(head)}{sep}{key(body)}</span>'
            tds.append('<td class="c-policy">' + "".join(render_p(x) for x in r["policy"]) + "</td>")

            if i == 0:
                st = sec["verified"]["status"]
                if st == "checked":
                    vchip = '<span class="vchip ok" title="已抓取官网并逐项比对">已核对</span>'
                elif st == "partial":
                    vchip = '<span class="vchip part" title="仅部分车型取到，或数值有变化待确认">部分核对</span>'
                else:
                    vchip = '<span class="vchip wait" title="官网未取到，沿用上期值">待核对</span>'
                tds.append(f'<td class="c-verify" rowspan="{span}">{vchip}</td>')
            rows_html.append("<tr>" + "".join(tds) + "</tr>")

    html = (TEMPLATE
            .replace("__WEEK__", data["week"])
            .replace("__UPDATED__", str(data["updated"]))
            .replace("__LAST_CRAWL__", (data.get("checked_at_all") or "").replace(" 抓取", ""))
            .replace("__N_CHECKED__", str(n_checked))
            .replace("__N_PARTIAL__", str(n_partial))
            .replace("__N_PENDING__", str(n_pending))
            .replace("__JUDGE_WINDOW__", data.get("judge_window", ""))
            .replace("__DOC_BTN__", doc_btn)
            .replace("__ROWS__", "\n".join(rows_html)))
    return html
