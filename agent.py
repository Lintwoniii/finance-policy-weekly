#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""友商金融政策监测 Agent（独立版，不依赖任何平台）

用法：
    python3 agent.py                  # 抓取 9 家 → 更新本周 JSON → 生成 HTML
    python3 agent.py --render-only    # 只用现有 JSON 重新出表（不联网）
    python3 agent.py --only 小鹏 特斯拉 # 只抓指定品牌（调试）
    python3 agent.py --week 2026-W48  # 指定周文件
    python3 agent.py --verbose        # 打印每步细节

输出：
    data/<年>-W<周>.json      本周数据（同周多次抓取直接覆盖更新，只改 checked_at）
    out/友商金融政策动态-周报表.html

设计原则（与业务口径一致）：
1) 抓不到就沿用上期值，并标 partial / pending 与具体原因，绝不编造。
2) 五个业务列只放方案语言；条款原文（财金〔2026〕1号等）一律过滤。
3) 变化按政策窗口起始日判定：落在本周 → 「本周新增 起M.D」，此前 → 「延续 起M.D」。
4) 数值出现差异时不静默改写表格，而是把差异写进「周度变化」列并降级为 partial，
   提示人工确认表述；这样表格永远有官网证据、不会被脚本臆造。
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN_TZ = timezone(timedelta(hours=8))
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "out"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 条款原文/免责声明：只能进证据，绝不进业务列
BANNED = [
    "财金〔2026〕1号", "财金[2026]1号", "贴息政策期限", "消费贴息最高5000元",
    "近似折算年化利率", "最终以金融机构审核为准", "具体以金融机构", "以金融机构最终审核",
    "本页面仅供参考", "活动最终解释权",
]

# 非金融购车权益（现金立减/选装/赠品/礼包等）：只作证据，不进贴息政策列
PERK = ["立减", "车漆", "选装福利", "选装基金", "礼包", "赠品", "脚垫", "贴膜",
        "装潢", "置换补贴", "充电桩", "交付礼包"]


def drop_perks(lines):
    """整行非金融权益直接剔除；混合行按 、；, 拆掉权益小句后保留金融部分。"""
    out = []
    for ln in lines:
        keep = [s for s in re.split(r"[、；;,]", ln) if not any(p in s for p in PERK)]
        if keep:
            out.append("、".join(keep))
    return out

# 抓取优先级：静态 requests 先试，命中不了锚点再用 headless 浏览器
SOURCES = {
    "小鹏":   {"url": "https://www.xiaopeng.com/finance.html", "js": False,
               "anchors": ["年费率", "0息", "首付"]},
    "特斯拉": {"url": "https://www.tesla.cn/financing-calculator", "js": True,
               "anchors": ["贷款方案", "适用金融机构"],
               "api": "https://www.tesla.cn/fs-gateway/financialProducts/products?productLine=AUTO&context=DEFAULT"},
    "理想":   {"url": "https://www.lixiang.com/help/loaninstruction.html", "js": False,
               "anchors": ["5免", "随心还", "年费率"]},
    "蔚来":   {"url": "https://www.nio.cn/news", "js": False,
               "anchors": ["新闻资讯"],
               "scope": "品牌本体无金融方案正文，仅以新闻页作动态证据",
               "force_partial": True},
    "乐道":   {"url": "https://finance.onvo.cn/", "js": True,
               "anchors": ["0息", "首付", "费率"]},
    "极氪":   {"url": "https://www.zeekrlife.com/finance/FinancialCalculator", "js": True,
               "anchors": ["限时特惠", "首付"], "models": False,
               "scope": "直连官方金融接口逐车系核限时特惠/常规分期/尾款产品；7X 接口无在期方案；机构名单接口仅返回占位，以官网计算器为准"},
    "小米":   {"url": "https://www.xiaomiev.com/finance", "js": False,
               "anchors": ["年化费率", "首付", "期"]},
    "鸿蒙智行": {"url": "https://hima.auto/financing-calculator/loaninstruction/", "js": False,
               "anchors": ["年费率", "首付", "期"]},
    "比亚迪": {"url": "https://www.byd.com/cn/ocean-home/models/haibao/haibao-07-EV", "js": False,
               "anchors": ["金融礼", "0首付", "0利息"],
               "probe": ["https://www.byd.com/cn/dynasty-home/models/yuan/yuan-up"],
               "scope": "已核 海豹07EV（海洋网）、元UP（王朝网 yuan-up 页）在期"},
    "腾势":   {"url": "https://www.tengshiauto.com/product-detail/N9-2026", "js": False,
               "anchors": ["0首付", "贴息"],
               "probe": ["https://www.tengshiauto.com/product-detail/26-z9gt.html",
                         "https://www.tengshiauto.com/product-detail/N8.html",
                         "https://www.tengshiauto.com/product-detail/N8L-2026.html",
                         "https://www.tengshiauto.com/product-detail/N8L-EV.html",
                         "https://www.tengshiauto.com/product-detail/D9-2.html",
                         "https://www.tengshiauto.com/product-detail/Z9S.html"],
               "scope": "已核 N9、Z9GT、Z9S、N8、N8L（闪充版/纯电版）、D9 在期（D9 路径更正为 D9-2.html）"},
    "零跑":   {"url": "https://www.leapmotor.cn/A10.html", "js": False,
               "anchors": ["金融礼", "0利息", "0首付"],
               "scope": "仅核 A10 车型页，其他车型未逐一取到"},
}

# 品牌 → 数据文件里的 section 名（比亚迪/腾势合并在一个 section 下）
SECTION_OF = {
    "小鹏": "小鹏", "特斯拉": "特斯拉", "理想": "理想", "乐道": "蔚来",
    "蔚来": "蔚来", "极氪": "极氪", "小米": "小米", "鸿蒙智行": "鸿蒙智行",
    "比亚迪": "比亚迪", "腾势": "比亚迪", "零跑": "零跑",
}

ZEEKR_MODELS = ["001", "X", "001 FR", "009光辉", "MIX", "9X", "8X", "007GT", "007", "009", "7X"]


# ---------------------------------------------------------------- 基础工具
def log(msg, verbose=False):
    if verbose:
        print(msg, flush=True)


def now_cn():
    return datetime.now(CN_TZ)


def norm_req():
    """当前周窗口（周一至周日，Asia/Shanghai）。"""
    today = now_cn()
    monday = today - timedelta(days=today.weekday())
    start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=6)
    iso = start.isocalendar()
    return {
        "year": iso.year,
        "week": iso.week,
        "start": start,
        "end": end,
        "label": f"{start.month}月第{'一二三四五'[max(0, (start.day - 1) // 7)]}周"
                 f"（{start.month}.{start.day}–{end.month}.{end.day}）",
        "judge": f"{start.month}.{start.day}–{end.month}.{end.day}",
    }


def fetch_static(url, timeout=25):
    import requests
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                     timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def resolve_chromium():
    """找可用的 Chromium/Chrome：环境变量 → 常见路径 → playwright 自带。"""
    import os
    cands = [os.environ.get("CHROME_PATH"),
             "/usr/local/bin/chromium", "/usr/bin/chromium", "/usr/bin/chromium-browser",
             "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def fetch_js(url, wait_ms=6000, script=None):
    """用 headless Chromium 渲染后取文本（特斯拉 / 极氪 / 小米这类依赖 JS 的页面）。

    主文档正文之外，把所有 iframe 的正文也拼进来——小米金融试算整块在 iframe 内。
    """
    from playwright.sync_api import sync_playwright
    exe = resolve_chromium()
    with sync_playwright() as p:
        kw = {"headless": True, "args": ["--no-sandbox", "--disable-gpu",
                                         "--disable-blink-features=AutomationControlled"]}
        if exe:
            kw["executable_path"] = exe
        b = p.chromium.launch(**kw)
        page = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 1000},
                          locale="zh-CN")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait_ms)
        if script:
            text = script(page)
        else:
            text = page.inner_text("body")
        # iframe 正文（小米等把试算区放子页面）
        for fr in page.frames[1:]:
            try:
                sub = fr.inner_text("body")
                if len(sub) > 60:
                    text += "\n" + sub
            except Exception:
                continue
        b.close()
        return text


def zeekr_script(page):
    """极氪：逐个切换 11 款车型，记录每款的费率与月供；失败的车型单独标注。"""
    out = []
    ok_models, bad_models = [], []
    for m in ZEEKR_MODELS:
        try:
            # 打开车型下拉
            page.get_by_text("选择车型", exact=False).first.click(timeout=4000)
            page.wait_for_timeout(700)
            opt = page.get_by_text(m, exact=True).first
            opt.click(timeout=4000)
            page.wait_for_timeout(1800)
            body = page.inner_text("body")
            keep = [ln for ln in body.splitlines()
                    if any(k in ln for k in ("年费率", "首付", "月供", "期", "折合", "车价"))]
            out.append(f"[车型 {m}] " + " | ".join(dict.fromkeys(keep))[:400])
            ok_models.append(m)
        except Exception as e:
            bad_models.append(f"{m}({type(e).__name__})")
    out.append("[极氪成功车型] " + "、".join(ok_models))
    out.append("[极氪失败车型] " + "、".join(bad_models))
    return "\n".join(out)


# ------------------------------------------------------- 极氪直连官方金融接口
# 接口链（与官网前端一致）：车型列表 → 版本列表 → 产品类型 → 支持机构/方案。
# 签名：[MOLE, nonce, timestamp] 字典序拼接后 SHA1；头口径与线上 prod 前端对齐
# （app_type=h5、platform=WEB_MOBILE，不带 app_code）。
ZEEKR_MOLE = ("MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCz09z6e9WOcNq+nUMX8Vq1Xe2EmJxu"
               "R3XbturefioF)E(Fl")
ZEEKR_APP_ID = "ONEX97FB91F061405"
ZEEKR_BASE = "https://api-gw-toc.zeekrlife.com/soa-trade-finance-client/v1"
ZEEKR_NONCE_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz1234567890"
ZEEKR_TYPE_NAME = {1: "常规分期", 2: "尾款产品", 5: "直租方案", 6: "限时特惠"}


def _zeekr_headers():
    import hashlib
    import random
    import time
    nonce = "".join(random.choice(ZEEKR_NONCE_CHARS) for _ in range(15))
    ts = str(int(time.time() * 1000))
    sign = hashlib.sha1("".join(sorted([ZEEKR_MOLE, nonce, ts])).encode()).hexdigest()
    return {
        "User-Agent": UA, "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.zeekrlife.com/",
        "x_ca_key": "H5-SIGN-SECRET-KEY", "x_ca_nonce": nonce,
        "x_ca_timestamp": ts, "x_ca_sign": sign,
        "app_type": "h5", "platform": "WEB_MOBILE",
        "WorkspaceId": "prod", "Version": "2",
        "device_id": "".join(str(random.randint(0, 9)) for _ in range(20)),
        "riskTimeStamp": ts, "AppId": ZEEKR_APP_ID,
        f"X-CORS-{ZEEKR_APP_ID}-prod": "1",
    }


def _zeekr_call(session, method, path, body=None):
    r = session.request(method, ZEEKR_BASE + path, json=body,
                        headers=_zeekr_headers(), timeout=25)
    r.raise_for_status()
    j = r.json()
    # 10086「未查询到产品」= 该车系/方案类型在接口侧无在期方案，按空数据处理，不算失败
    if str(j.get("code")) not in ("000000", "10086"):
        raise RuntimeError(j.get("msg") or "极氪接口返回异常")
    return j.get("data") or []


def _zeekr_short(name):
    n = re.sub(r"^ZEEKR\s*", "", name or "").strip()
    return n.replace("009 光辉系列", "009光辉")


def _zeekr_g(pct):
    """'2.99%' / 0.00 → '2.99' / '0' 数值字符串；空 → ''。"""
    if pct in (None, ""):
        return ""
    try:
        return f"{float(str(pct).rstrip('%')):g}"
    except (TypeError, ValueError):
        return ""


def _zeekr_seg_label(tmin, tmax):
    """分段期数转中文：1-24 → 前2年；25-60 → 后3年；37-60 → 后2年。"""
    try:
        lo, hi = int(float(tmin)), int(float(tmax))
    except (TypeError, ValueError):
        return ""
    if lo <= 1:
        return f"前{round(hi / 12)}年"
    return f"后{round((hi - lo + 1) / 12)}年"


def _zeekr_term_label(months):
    try:
        m = int(float(months))
    except (TypeError, ValueError):
        return ""
    return "5年" if m == 60 else f"{m}期"


def _zeekr_item(model, version, ptype, product, item):
    cd = (item.get("clientData") or {}).get("normal") or {}
    rates = []
    for ri in item.get("itemRateResultList") or []:
        segs = ri.get("termInfoList") or []
        if segs:
            for sg in segs:
                rates.append({
                    "tmin": sg.get("termMin"), "tmax": sg.get("termMax"),
                    "fee": sg.get("discountAnnualizedRatePercent") or sg.get("annualizedRatePercent"),
                    "interest": sg.get("discountAnnualizedInterestRatePercent")
                                or sg.get("annualizedInterestRatePercent"),
                })
        else:
            rates.append({
                "tmin": None, "tmax": item.get("loanTerm"),
                "fee": ri.get("discountAnnualizedRatePercent") or ri.get("annualizedRatePercent"),
                "interest": ri.get("discountAnnualizedInterestRatePercent")
                            or ri.get("annualizedInterestRatePercent"),
            })
    return {
        "model": _zeekr_short(model.get("modelName")),
        "version": version.get("versionName"),
        "ptype": ptype, "pname": product.get("financeProductName"),
        "tag": item.get("tagText") or "", "loanTerm": item.get("loanTerm"),
        "downMin": cd.get("downPayRatioMin"), "downMax": cd.get("downPayRatioMax"),
        "unpaidMin": cd.get("unpaidRatioMin"), "unpaidMax": cd.get("unpaidRatioMax"),
        "rates": rates,
    }


def _zeekr_build_lines(records):
    """按车系 × 方案类型聚合为周报政策行；返回 (lines, summary)。"""
    by_model = {}
    for rec in records:
        by_model.setdefault(rec["model"], []).append(rec)

    order = [_zeekr_short(x) for x in
             ["ZEEKR 001", "ZEEKR X", "ZEEKR 001 FR", "ZEEKR 009 光辉系列", "ZEEKR MIX",
              "ZEEKR 9X", "ZEEKR 8X", "ZEEKR 007GT", "ZEEKR 007", "ZEEKR 009", "ZEEKR 7X"]]
    models = order + [m for m in by_model if m not in order]

    lines, rates, models_with = [], set(), []
    for model in models:
        recs = by_model.get(model, [])
        groups = {6: [], 1: [], 2: []}
        for r in recs:
            groups.setdefault(r["ptype"], []).append(r)
        if not recs:
            lines.append(f"{model}：金融接口未返回在期方案（限时特惠/常规分期/尾款产品均无记录）")
            continue
        models_with.append(model)

        # —— 限时特惠（type 6）——
        if groups[6]:
            offers = []
            seen = set()
            for r in groups[6]:
                seg_txts, interest = [], ""
                for rt in r["rates"]:
                    fee = _zeekr_g(rt["fee"])
                    lab = _zeekr_seg_label(rt["tmin"], rt["tmax"])
                    seg_txts.append(f"{lab}年费率{fee}%" if lab else f"{_zeekr_term_label(rt['tmax'])}年费率{fee}%")
                    if fee and fee != "0":
                        interest = _zeekr_g(rt["interest"])
                key = (r["tag"], tuple(seg_txts), interest)
                if key in seen:
                    continue
                seen.add(key)
                head = f"限时特惠 {r['tag']}（5年）" if r["tag"] else "限时特惠（5年）"
                body = "、".join(seg_txts)
                if interest:
                    body += f"（折合年化利率{interest}%）"
                offers.append(f"{head}：首付20%起，{body}")
                for rt in r["rates"]:
                    f = _zeekr_g(rt["fee"])
                    if f and f != "0":
                        rates.add(f + "%")
            if offers:
                lines.append(f"{model}：" + "；".join(offers))

        # —— 常规分期（type 1）——
        if groups[1]:
            zero, normal = [], {}
            for r in groups[1]:
                for rt in r["rates"]:
                    fee = _zeekr_g(rt["fee"])
                    term = _zeekr_term_label(rt["tmax"] or r["loanTerm"])
                    interest = _zeekr_g(rt["interest"])
                    if r["tag"] == "0息" or fee == "0":
                        zero.append(term)
                    else:
                        normal.setdefault(fee, {"terms": [], "interest": []})
                        normal[fee]["terms"].append(term)
                        if interest:
                            normal[fee]["interest"].append(interest)
            parts = []
            for fee, info in normal.items():
                terms = "/".join(dict.fromkeys(info["terms"]))
                iv = info["interest"]
                i_txt = f"（折合年化利率{min(iv)}-{max(iv)}%）" if len(iv) > 1 else (
                    f"（折合年化利率{iv[0]}%）" if iv else "")
                parts.append(f"{terms}年费率{fee}%{i_txt}")
                rates.add(fee + "%")
            if zero:
                parts.append("、".join(dict.fromkeys(zero)) + "0息")
            if parts:
                lines.append(f"{model}：常规分期 " + "；".join(parts))

        # —— 尾款产品（type 2）——
        if groups[2]:
            terms, interests, down, unpaid = [], [], [], []
            for r in groups[2]:
                if r["downMin"] is not None:
                    down.append(r["downMin"])
                if r["unpaidMin"] is not None:
                    unpaid.append(r["unpaidMin"])
                    unpaid.append(r["unpaidMax"])
                for rt in r["rates"]:
                    interests.append(_zeekr_g(rt["interest"]))
                    terms.append(_zeekr_term_label(rt["tmax"] or r["loanTerm"]))
            down_txt = f"首付{min(down):g}%起" if down else ""
            unpaid_txt = ""
            unpaid_v = [x for x in unpaid if x is not None]
            if unpaid_v:
                unpaid_txt = f"、尾款{min(unpaid_v):g}%-{max(unpaid_v):g}%"
            int_map = {}
            for t, i in zip(terms, interests):
                if i:
                    int_map.setdefault(i, [])
                    if t not in int_map[i]:
                        int_map[i].append(t)
            int_txt = "、".join(f"{'/'.join(ts)}年化利率{i}%" for i, ts in int_map.items())
            if int_txt:
                lines.append(f"{model}：尾款产品 {down_txt}{unpaid_txt}，{int_txt}（年化费率按年金口径测算）")

    summary = {"models": models_with, "rates": sorted(rates),
               "no_offer": [m for m in models if m not in models_with]}
    return lines, summary


def zeekr_crawl_api():
    """直连极氪官方金融接口，返回 (政策行列表, 摘要)；失败抛异常。"""
    import requests
    session = requests.Session()
    models = _zeekr_call(session, "GET", "/model/pub/modelInfo/finance/list")
    records = []
    for m in models:
        mid = str(m.get("modelInfoId") or "")
        year = m.get("modelYearCode")
        vbody = {"modelYearCode": year} if year is not None else {"modelInfoId": mid}
        versions = _zeekr_call(session, "POST", "/model/pub/modelVersion/finance/list", vbody)
        for v in versions:
            vid = str(v.get("modelVersionId") or "")
            base = {"modelInfoId": mid, "modelVersionId": vid,
                    "cityCode": "310100", "buyType": 0}
            products = _zeekr_call(session, "POST", "/finance/pub/financeProduct", base)
            for p in products:
                ptype = p.get("financeProductType")
                inst = _zeekr_call(session, "POST", "/finance/pub/supportInstitutionCode",
                                    {**base, "financeProductType": ptype})
                for item in inst:
                    records.append(_zeekr_item(m, v, ptype, p, item))
    lines, summary = _zeekr_build_lines(records)
    return lines, summary


def strip_html(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</?(p|div|li|tr|td|h\d|section)[^>]*>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&yen;", "¥")]:
        html = html.replace(a, b)
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in html.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def clean_text(text, limit_lines=100000):
    lines = []
    for ln in text.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if not ln:
            continue
        if any(b in ln for b in BANNED):
            continue
        lines.append(ln)
        if len(lines) >= limit_lines:
            break
    return "\n".join(lines)


# ---------------------------------------------------------------- 指纹与抽取
NUM = r"(\d+(?:\.\d+)?)"


def fingerprint(text):
    """把页面里的政策数字压成可比较的指纹集合（费率/首付/期数/贴息/日期）。"""
    fp = set()
    for ln in text.splitlines():
        for m in re.finditer(NUM + r"\s*%", ln):
            if any(k in ln for k in ("年费率", "年化费率", "利率", "费率")):
                fp.add(f"费率{m.group(1)}%")
            elif "首付" in ln or "尾款" in ln:
                fp.add(f"比例{m.group(1)}%")
    for m in re.finditer(r"(\d+)\s*期\s*(?:0息|免息|0利率)", text):
        fp.add(f"{m.group(1)}期0息")
    for m in re.finditer(r"首付\s*" + NUM + r"\s*万", text):
        fp.add(f"首付{m.group(1)}万")
    for m in re.finditer(r"贴息\s*(?:约)?\s*" + NUM + r"\s*万", text):
        fp.add(f"贴息{m.group(1)}万")
    for m in re.finditer(r"(\d+)\s*个月|(\d+)\s*年\s*(?:0息|免息)", text):
        fp.add(f"期数{(m.group(1) or m.group(2))}")
    for m in re.finditer(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[–\-—~至]\s*(\d{1,2})\s*月\s*(\d{1,2})", text):
        fp.add(f"窗口{m.group(1)}.{m.group(2)}-{m.group(3)}.{m.group(4)}")
    for m in re.finditer(r"(20\d{2})[./](\d{1,2})[./](\d{1,2})\s*[–\-—]\s*(20\d{2})?[./]?(\d{1,2})[./](\d{1,2})", text):
        fp.add(f"窗口{m.group(2)}.{m.group(3)}-{m.group(5)}.{m.group(6)}")
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})\s*[–\-—]\s*(\d{1,2})\.(\d{1,2})", text):
        fp.add(f"窗口{m.group(1)}.{m.group(2)}-{m.group(3)}.{m.group(4)}")
    return sorted(fp)


def policy_lines(text, max_lines=40):
    """挑出方案语言行（含费率/首付/期/贴息），已过禁词过滤。"""
    keys = ("年费率", "年化费率", "0息", "免息", "首付", "贴息", "期", "免", "折合", "月供", "大定", "开票")
    out, seen = [], set()
    for ln in text.splitlines():
        if not any(k in ln for k in keys):
            continue
        if any(p in ln for p in PERK):
            continue
        if len(ln) > 160:
            ln = ln[:160]
        if ln in seen:
            continue
        seen.add(ln)
        out.append(ln)
        if len(out) >= max_lines:
            break
    return out


def window_dates(text):
    """抽取政策窗口「起始日」，返回 [(月,日)]。

    只在含活动期语义的行里找日期，且区分起始/截止：
      - "11.1–11.30" / "11月1日-11月30日"  取 11.1
      - "自 11.9 起" / "11.13 起"          取 11.9 / 11.13
      - "11月30日（含）前下订"              这是截止日，不当作起始
    费率里的 "2.5%"、"1.99%" 不会被当成日期。
    """
    import re as _re
    CEIL_HINT = ("有效期", "活动期", "活动时间", "权益期", "大定", "开票", "下定", "下订", "起")
    heads = []
    for ln in text.splitlines():
        if any(h in ln for h in CEIL_HINT) and _re.search(r"\d", ln):
            heads.append(ln)

    def clean(x):
        try:
            m, d = int(x[0]), int(x[1])
        except Exception:
            return None
        return (m, d) if 1 <= m <= 12 and 1 <= d <= 31 else None

    found = []
    for ln in heads:
        # A–B 区间：取 A
        for m in _re.finditer(r"(?<!\d)(\d{1,2})\s*[月./]\s*(\d{1,2})\s*(?:日)?\s*[–\-—~至]\s*\d{1,2}\s*[月./]\s*\d{1,2}", ln):
            c = clean((m.group(1), m.group(2)))
            if c:
                found.append(c)
        # "自 X 起" / "X 起"（排除 "前"）
        for m in _re.finditer(r"(?:自\s*)?(?<!\d)(\d{1,2})\s*[月./]\s*(\d{1,2})\s*(?:日)?\s*起", ln):
            c = clean((m.group(1), m.group(2)))
            if c:
                found.append(c)
        # 中文日期区间 "11月1日至11月30日"
        for m in _re.finditer(r"(\d{1,2})月(\d{1,2})日\s*[至–\-—]?\s*(\d{1,2})月(\d{1,2})日", ln):
            c = clean((m.group(1), m.group(2)))
            if c:
                found.append(c)

    seen, uniq = set(), []
    for x in sorted(found):
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def judge_change(since, week_start):
    """按政策窗口起始日判定：本周内→new，此前→carry。since=(月,日)。"""
    if not since:
        return "carry", ""
    m, d = (since.month, since.day) if hasattr(since, "month") else since
    if (m, d) >= (week_start.month, week_start.day):
        return "new", f"本周新增 起{m}.{d}"
    return "carry", f"延续 起{m}.{d}"


def policy_models(line):
    """把方案行解析成基础车型集合：去子品牌前缀、按 / 拆、取首个词。
    「智界R7 2027款/RX：…」→ {R7, RX}；「享界V8：…」→ {V8}。"""
    cut = len(line)
    for ch in ("：", ":", "（", "("):
        i = line.find(ch)
        if 0 < i < cut:
            cut = i
    head = line[:cut].strip()
    subs = r"(问界|智界|享界|尊界|尚界|腾势|比亚迪)"
    out = set()
    for tok in re.split(r"[/、，,]", head):
        tok = re.sub(subs, "", tok)
        tok = re.sub(r"\s+", " ", tok).strip()
        if not tok:
            continue
        out.add(tok.split(" ")[0])
    return out


# ---------------------------------------------------------------- 车型清单发现
# ---------------------------------------------------------------- 比亚迪文本提炼
VER = r"(闪充版|纯电版|2026款|高配版|含先锋版)"


def to_year(n, unit):
    n = int(n)
    return max(1, round(n / 12)) if unit == "期" else n


PAY = [
    r"([\d]+)%首付(?:起)?(?:至高)?\s*(\d+)\s*(年|期)(?:期)?(?P<pre>前\d年)?0息",
    r"首付\s*([\d]+)%(?:起)?(?:至高)?\s*(\d+)\s*(年|期)(?:期)?(?P<pre>前\d年)?0息",
    r"([\d]+)成首付(?:起)?(?:至高)?\s*(\d+)\s*(年|期)(?:期)?(?P<pre>前\d年)?0息",
]


def tokens(b):
    out = []
    if "5050" in b or "50-50" in b:
        m2 = re.search(r"(\d+)\s*年-?5050免息", b) or re.search(r"50-50\s*(\d+)\s*(?:年|期)0息", b)
        yr = to_year(m2.group(1), "期" if m2 and "期" in m2.group(0) else "年") if m2 else 1
        out.append(f"{yr}年-5050免息")
    if "0首付" in b and "0利息" in b and "0月供" in b:
        out.append("0首付/0利息/0月供")
    elif "0首付" in b:
        out.append("0首付")
    m = re.search(r"(\d+(?:\.\d+)?)万(?:元)?(?:定额)?贷?\s*(?:至高)?\s*(\d+)\s*(年|期)0息", b)
    if m:
        out.append(f"{m.group(1)}万 {to_year(m.group(2), m.group(3))}年0息")
    m = re.search(r"首付\s*(\d+)%\s*尾款\s*(\d+)%\s*(\d+)\s*(年|期)0息0月供", b)
    if m:
        out.append(f"{m.group(1)}%尾款 {to_year(m.group(3), m.group(4))}年0息0月供")
    for pat in PAY:
        for mm in re.finditer(pat, b):
            pct = mm.group(1)
            if "成首付" in mm.group(0):
                pct = {"1": "10", "2": "20", "3": "30"}.get(pct, pct)
            pre = "前2年" if (mm.group("pre") and "2" in mm.group("pre")) else ""
            out.append(f"{pct}%首付 {to_year(mm.group(2), mm.group(3))}年{pre}0息")
    for mm in re.finditer(r"年费率\s*([\d.]+)%", b):
        out.append(f"年费率{mm.group(1)}%")
    if "超长贷" in b:
        out.append("至高5年超长贷")
    return list(dict.fromkeys(out))


def norm_body(body):
    body = body.replace("&NoBreak;", "").replace("\u00a0", "")
    body = re.sub(r"\s+", " ", body)
    body = re.sub(r"弹性贷款\s*5-0-5\s*产品：.*?2-5-3 产品：.*?尾款。?", "弹性贷款 5-0-5/3-4-3/2-5-3", body)
    body = re.sub(r"融资租赁\s*直接租赁：0 首付起，1-5 年期，年费率 ([\d.]+)%；售后回租：0 首付起，1-5 年期，年费率 ([\d.]+)%",
                  r"融资租赁 直租\1%/回租\2%", body)
    return body

def norm_clause(c):
    c = c.strip().rstrip("。").strip()
    m = re.match(r"首付\s*([\d.]+)\s*万元起[，,]\s*(\d(?:-\d)?)\s*年期[，,]\s*年费率\s*([\d.]+)%$", c)
    if m:
        return f"首付{m.group(1)}万起 {m.group(2)}年 {m.group(3)}%"
    m = re.match(r"首付\s*([\d.]+)\s*万元起[，,]\s*5\s*年期[，,]\s*前\s*(\d)\s*年年费率\s*0%[，,]\s*后\s*(\d)\s*年年费率\s*([\d.]+)%$", c)
    if m:
        return f"首付{m.group(1)}万起 5免{m.group(2)}（前{m.group(2)}年0/后{m.group(3)}年{m.group(4)}%）"
    m = re.match(r"0\s*首付起[，,]\s*1-5\s*年期[，,]\s*年费率\s*([\d.]+)%$", c)
    if m:
        return f"0首付 1-5年 {m.group(1)}%"
    return c

def merge_zero(parts):
    rates, others = [], []
    for p in parts:
        m = re.match(r"0首付 1-5年 ([\d.]+)%$", p)
        if m:
            if m.group(1) not in rates:
                rates.append(m.group(1))
        else:
            others.append(p)
    if rates:
        others.insert(0, "0首付 1-5年 " + "%/".join(rates) + "%")
    return others

def compact_hima(lines):

    groups, order = {}, []
    for ln in lines:
        if "：" not in ln:
            continue
        head, body = ln.split("：", 1)
        parts = merge_zero([norm_clause(x) for x in re.split(r"[；;]", norm_body(body)) if x.strip()])
        key = "；".join(parts)
        groups.setdefault(key, [])
        if key not in order:
            order.append(key)
        groups[key].append(head.strip())
    return [f"{'/'.join(groups[k])}：{k}" for k in order]


def compact_zeekr(lines):
    """极氪：政策行已由官方接口按车系/方案类型聚合，这里只剔除异常占位行。"""
    out = []
    for ln in lines:
        if "异常" in ln or "未自动" in ln:
            continue
        out.append(ln)
    return out

def compact_li(lines):
    """理想：按车型分组；产品名（随心还/月息年本等）不单独成行，只保留车型组行。"""
    product_heads = {"随心还", "月息年本", "常规贷款", "标准贷款", "弹性贷款"}
    out = []
    for ln in lines:
        head = ln.split("：", 1)[0].strip() if "：" in ln else ln.strip()
        if head in product_heads:
            continue
        out.append(ln)
    return out


def compact_byd(lines):
    merged, generic = {}, []
    for ln in lines:
        if "：" not in ln:
            generic.append(ln)
            continue
        head, body = ln.split("：", 1)
        head = re.sub(r"（[^）]*）", "", head).strip()
        base = re.sub(VER, "", head).strip()
        tk = tokens(body)
        if not tk:
            generic.append(ln)
            continue
        merged.setdefault(base, {"tk": [], "ver": set()})
        for t in tk:
            if t not in merged[base]["tk"]:
                merged[base]["tk"].append(t)
        if head != base:
            merged[base]["ver"].add(head.replace(base, "").strip())
    out = list(generic)
    for base, info in merged.items():
        vers = [v for v in sorted(info["ver"]) if v]
        label = base + ("（" + "/".join(vers) + "）" if vers else "")
        out.append(f"{label}：{'、'.join(info['tk'])}")
    return out



def discover_models(name, text=""):
    """各品牌官网车型清单：[(车型名, 官网车型页 or "")]。优先用本次抓到的页面正文。"""
    import requests
    UA = {"User-Agent": "Mozilla/5.0"}
    if name == "小鹏":
        cands = []
        for ln in (text or "").splitlines():
            x = ln.strip()
            if re.match(r"^(20\d\d款)?(G\d|P\d\+|X\d|L\d{2}|M\d{2}|GX)$", x):
                cands.append(x)
        return [(x, "") for x in dict.fromkeys(cands)]
    if name == "理想":
        sm = requests.get("https://www.lixiang.com/sitemap.xml", headers=UA, timeout=20).text
        locs = re.findall(r"<loc>([^<]+)</loc>", sm)
        out = []
        for u in locs:
            seg = u.replace("https://www.lixiang.com/", "").strip("/")
            if re.match(r"^(L\d{1,2}|MEGA|i\d{1,2})$", seg):
                out.append((seg, u))
        return out
    if name == "小米":
        cands = sorted(set(re.findall(r"(N90|SU7|YU7|YU9)", text or "")))
        return [(n, "") for n in cands]
    if name == "比亚迪":
        out = []
        for home, cn in [("ocean-home", {"haibao": "海豹", "haiou": "海鸥", "haishi": "海狮", "haitun": "海豚"}),
                         ("dynasty-home", {"han": "汉", "qin": "秦", "song": "宋", "tang": "唐", "xia": "夏", "yuan": "元"})]:
            h = requests.get(f"https://www.byd.com/cn/{home}", headers=UA, timeout=20).text
            slugs = set(re.findall(rf"/cn/{home}/models/([A-Za-z0-9\-_]+)", h))
            for sl, nm in cn.items():
                if sl in slugs:
                    out.append((nm, f"https://www.byd.com/cn/{home}/models/{sl}"))
        return out
    if name == "零跑":
        t = clean_text(fetch_js("https://www.leapmotor.cn/", wait_ms=8000))
        cands = sorted(set(re.findall(r"(Lafa\d?|[ABCD]\d{1,2}|T\d{2})", t)))
        return [(x, f"https://www.leapmotor.cn/{x}.html") for x in cands]
    return []


def find_plan_lines(text, cap=3):
    """从车型页正文里抽方案语言行（只留带费率/首付语义的短句）。"""
    out = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if 6 < len(s) < 110 and re.search(r"首付|0息|免息|年费率|贴息|月供", s) and s not in out:
            out.append(s)
    return out[:cap]


def hima_activity(text):
    """鸿蒙页面「活动时间：2026 年 11 月 20 日-11 月 30 日」→ (11,20)。"""
    t = text.replace("&NoBreak;", "").replace("\u00a0", "")
    m = re.search(r"活动时间[：:]\s*\d{4}\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", t)
    return (int(m.group(1)), int(m.group(2))) if m else None


HIMA_SUBS = ("问界", "智界", "享界", "尊界", "尚界")


def parse_hima_rows(text):
    """把鸿蒙智行金融页解析成 {子品牌: [车型组方案行]}，新车会自动进表。"""
    def norm(x):
        return re.sub(r"\s+", " ", x.replace("&NoBreak;", "").replace("\u00a0", "")).strip()

    lines = [norm(x) for x in text.splitlines()]
    lines = [x for x in lines if x]
    sec, offer, items, offer_start = None, None, [], 0
    for ln in lines:
        if ln == "问界" or ln.startswith("智界、享界"):
            sec = "问界" if ln == "问界" else "other"
            offer = None
            continue
        if sec is None:
            continue
        if ln.startswith("其他说") or ln.startswith("隐私声明"):
            break
        if re.match(r"^\d+、", ln):
            offer = re.sub(r"^\d+、", "", ln).strip()
            offer_start = len(items)
            continue
        if offer is None and not ln.startswith("（"):
            continue   # 顶部导航/页头，不属于任何方案
        if ln.startswith("（") and "）" in ln:
            items.append({"offer": offer or "", "terms": [ln.split("）", 1)[1].strip()],
                          "models": "", "orgs": ""})
            continue
        if ln.startswith("适用车型"):
            models = ln.split("：", 1)[1] if "：" in ln else ""
            if items and not items[-1]["models"]:
                items[-1]["models"] = models
            else:
                items.append({"offer": offer or "", "terms": [], "models": models, "orgs": ""})
            for it in items[offer_start:]:      # 同一方案内缺车型的兄弟条目一起补
                if not it["models"]:
                    it["models"] = models
            continue
        if ln.startswith("金融服务机构"):
            orgs = ln.split("：", 1)[1] if "：" in ln else ""
            if items and not items[-1]["orgs"]:
                items[-1]["orgs"] = orgs
            else:
                items.append({"offer": offer or "", "terms": [], "models": "", "orgs": orgs})
            continue
        if not items or (items[-1]["models"] and items[-1]["orgs"]):
            items.append({"offer": offer or "", "terms": [ln], "models": "", "orgs": ""})
        else:
            items[-1]["terms"].append(ln)

    grouped = {}
    for it in items:
        if not it["models"]:
            continue
        body = re.sub(r"；+", "；", "；".join(it["terms"])).strip("；")
        label = f"{it['offer']} {body}".strip() if it["offer"] else body
        if it["offer"] and body.startswith(("0 首付起", "首付")):
            label = body
        for mv in re.split(r"[、,]", it["models"]):
            mv = mv.strip()
            if not mv:
                continue
            sub = mv[:2]
            if sub not in HIMA_SUBS:
                continue
            model = re.sub(r"\s+", " ", mv)
            model = re.sub(r"^(问界|智界|享界|尊界|尚界)\s*", r"\1", model)
            grouped.setdefault(sub, {}).setdefault(model, []).append(label)

    out = {}
    for sub, models in grouped.items():
        rows = []
        for model, labels in models.items():
            uniq = []
            for x in labels:
                if x and x not in uniq:
                    uniq.append(x)
            rows.append(f"{model}：{'；'.join(uniq)}")
        out[sub] = rows
    return out



def week_diff(prev_row, row):
    """对照上一周：返回新增车型组列表与费率/机构是否变化。"""
    pk = set().union(*[policy_models(x) for x in prev_row.get("policy", [])]) if prev_row.get("policy") else set()
    ck = set().union(*[policy_models(x) for x in row.get("policy", [])]) if row.get("policy") else set()
    # 上期为「全系通用」口径时，视为已覆盖本期全部车系，拆车型行不算新增方案
    if any("全系" in x for x in prev_row.get("policy") or []):
        pk = ck
    new = sorted(ck - pk)
    rate_chg = prev_row.get("rates") != row.get("rates")
    org_chg = prev_row.get("orgs") != row.get("orgs")
    return new, rate_chg, org_chg



# ---------------------------------------------------------------- 抓取调度
def crawl_brand(name, cfg, verbose=False):
    url = cfg["url"]
    js = cfg.get("js", False)
    text, method, err, zeekr = None, "", "", None
    # 极氪：优先直连官方金融接口（签名四接口链），失败再退回静态/headless
    if name == "极氪":
        try:
            zlines, zsum = zeekr_crawl_api()
            if zlines:
                zeekr = {"lines": zlines, "summary": zsum}
                text, method, js = "\n".join(zlines), "requests-api", False
                log("  [极氪接口] 取到车系 %d 款" % len(zsum["models"]), verbose)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log(f"  [极氪接口失败] {err}", verbose)
    if text is None:
        try:
            raw = fetch_static(url)
            text = strip_html(raw)
            if not any(a in text for a in cfg["anchors"]):
                js = True
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log(f"  [静态失败] {name} {err}", verbose)
            js = True

    # JSON 接口兜底（特斯拉计算器 SPA 数据走 fs-gateway）：浏览器超时/空壳时直接取产品接口
    if cfg.get("api") and not (text and any(a in text for a in cfg["anchors"])):
        try:
            api_text = fetch_static(cfg["api"], timeout=20)
            if any(a in api_text for a in cfg["anchors"]):
                text = api_text
                method = "requests-api"
                js = False
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log(f"  [接口失败] {name} {err}", verbose)

    if js:
        try:
            if name == "极氪" and cfg.get("models"):
                text = fetch_js(url, wait_ms=5000, script=zeekr_script)
            else:
                try:
                    text = fetch_js(url, wait_ms=9000)
                except Exception:
                    text = fetch_js(url, wait_ms=9000)   # 浏览器启动/加载超时重试一次
            method = "headless"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            log(f"  [浏览器失败] {name} {err}", verbose)
            text = text or ""
    else:
        method = method or "requests"

    text = clean_text(text or "")
    ok = bool(text) and any(a in text for a in cfg["anchors"])

    # 追加探测页（同品牌的其他车型页）：只判断可达性，不参与数值比对
    probes = []
    for pu in cfg.get("probe", []):
        try:
            pt = clean_text(strip_html(fetch_static(pu)))
            if not any(a in pt for a in cfg["anchors"]) and len(pt) < 5000:
                try:  # 静态是空壳（JS 渲染页）时改用 headless 再读一次
                    pt = clean_text(fetch_js(pu, wait_ms=9000))
                except Exception:
                    pass
            pt_ok = len(pt) > 400 and any(a in pt for a in cfg["anchors"])
            probes.append({"url": pu, "ok": pt_ok,
                           "reason": "" if pt_ok else f"页面可达但无方案锚点（正文 {len(pt)} 字）"})
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            reason = f"HTTP {code}" if code else f"{type(e).__name__}"
            probes.append({"url": pu, "ok": False, "reason": reason})

    return {"text": text, "method": method, "ok": ok, "url": url, "err": err,
            "probes": probes, "zeekr": zeekr}


# ---------------------------------------------------------------- 主流程
def load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--week", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    win = norm_req()
    week_id = args.week or f"{win['year']}-W{win['week']:02d}"
    data_path = DATA_DIR / f"{week_id}.json"

    # 上周文件（用于「变化」列的周对周差分）
    PREV = None
    for p in reversed(sorted(DATA_DIR.glob("*.json"))):
        if p.stem != week_id:
            PREV = load_json(p)
            break

    BASE_REF = load_json(BASE / "baseline.json")

    # 数据文件：有则用，无则由上一周/基线复制
    data = load_json(data_path)
    if not data:
        prev = sorted(DATA_DIR.glob("*.json"))
        base = load_json(prev[-1]) if prev else load_json(BASE / "baseline.json")
        if not base:
            raise SystemExit("缺少 baseline.json，无法初始化")
        data = json.loads(json.dumps(base))
        data["week"] = win["label"]
        data["judge_window"] = win["judge"]
        data["updated"] = f"{now_cn().month}.{now_cn().day}"
        for sec in data["sections"]:
            sec.pop("fingerprint", None)

    stamp = now_cn().strftime("%Y-%m-%d %H:%M")
    data["checked_at_all"] = f"{stamp} 抓取"
    data["updated"] = f"{now_cn().month}.{now_cn().day}"

    by_name = {s["brand"]: s for s in data["sections"]}
    changes, problems = [], []
    res_map = {}   # name -> {status, note, gap, url, method, since, diff}

    names = [] if args.render_only else (args.only or list(SOURCES.keys()))
    for name in names:
        cfg = SOURCES[name]
        sec = by_name.get(SECTION_OF[name])
        if sec is None:
            continue
        log(f"→ {name} {cfg['url']}", args.verbose)
        res = crawl_brand(name, cfg, args.verbose)

        # 极氪直连接口成功：用接口聚合行替换表内政策行与费率
        if res.get("zeekr"):
            z = res["zeekr"]
            r0 = sec["rows"][0]
            r0["policy"] = z["lines"]
            if z["summary"]["rates"]:
                r0["rates"] = z["summary"]["rates"]

        # 正文过薄（Bot 校验页/空壳页）不算取到
        anchors_hit = [a for a in (cfg.get("anchors") or []) if a in (res.get("text") or "")]
        if res["ok"] and not policy_lines(res.get("text") or "") and name != "鸿蒙智行":
            res["ok"] = False
            res["err"] = "官网正文无方案文案（仅新闻/权益页），无可核费率"
        if res["ok"] and len(res.get("text") or "") < 900 and not anchors_hit:
            try:
                raw = fetch_static(cfg["url"]) or ""
            except Exception:
                raw = ""
            res["ok"] = False
            res["err"] = (f"官网返回 Bot 校验页（EO_Bot_Ssid 挑战脚本，静态仅 {len(raw)} 字节），"
                          f"headless 正文仅 {len(res.get('text') or '')} 字，无方案正文"
                          if "EO_Bot_Ssid" in raw else
                          f"正文仅 {len(res.get('text') or '')} 字，无方案正文")
        if not res["ok"]:
            why = res["err"] or "页面无方案锚点（正文未渲染出费率/首付文案）"
            try:
                raw = fetch_static(cfg["url"]) or ""
                if "EO_Bot_Ssid" in raw or len(raw) < 1500:
                    why = (f"官网命中 JavaScript Bot 校验页（EO_Bot_Ssid 挑战脚本，静态仅 {len(raw)} 字节，"
                           "headless 渲染后正文也无方案锚点），沿用上期值")
            except Exception:
                pass
            problems.append(f"{name}：未取到（已尝试 {cfg['url']}）· {why}")
            res_map[name] = {"status": "partial", "failed": True, "url": cfg["url"], "method": res["method"],
                             "note": f"{name} 本轮未取到（已尝试 {cfg['url']}）：{why}，沿用上期值",
                             "gap": why, "since": None, "diff": []}
            continue

        # ---- 车型清单发现：官网上了新车就自动补行（不依赖表里是否写过）
        try:
            disc = discover_models(name, res["text"])
        except Exception as e:
            disc = []
            log(f"  清单发现失败：{type(e).__name__}", args.verbose)
        if disc:
            covered = set()
            for r in sec["rows"]:
                for pl in (r.get("policy") or []):
                    covered |= policy_models(pl)
            seen = set(sec.get("models_seen") or [])
            def same(m):
                m0 = re.sub(r"^20\d\d款", "", m)
                for c in list(covered) + list(seen):
                    c0 = re.sub(r"^20\d\d款", "", c)
                    if m0 == c0 or c0.startswith(m0) or m0.startswith(c0):
                        return True
                return False
            nop_cache = list(sec.get("models_nop") or [])
            if not seen:
                # 首次建立该品牌车型清单：只落基线，不算“新增”（避免把老车型误报成新车）
                sec["models_seen"] = sorted({m for m, _ in disc})
                log(f"  建立车型基线 {len(disc)} 款：{'、'.join(m for m, _ in disc)}", args.verbose)
                fresh = []
            else:
                fresh = [m for m in disc if not same(m[0])]
            # 上轮“无方案文本”的车型：每轮挑 1 个重试，拿到方案就补行
            retry = [(m, u) for (m, u) in disc if m in nop_cache][:1]
            if fresh:
                target = sec["rows"][0]
                added, nolf = [], []
                for m, u in (fresh[:3] + retry):
                    lines = []
                    if u:
                        try:
                            t2 = clean_text(fetch_js(u, wait_ms=8000) if name == "零跑" else fetch_static(u))
                            lines = find_plan_lines(t2)
                        except Exception:
                            lines = []
                    if lines:
                        target["policy"].append(f"{m}：{'；'.join(lines)}")
                        added.append(m)
                    else:
                        nolf.append(m)
                got = [m for m, _ in fresh if m not in nolf and m not in added]
                nop_cache = sorted((set(nop_cache) | set(nolf)) - set(added))
                sec["models_nop"] = nop_cache
                sec["models_seen"] = sorted(seen | set(got) | set(added))
                if added:
                    res["_added"] = added
                res["_nop"] = nop_cache
                log(f"  清单 {len(disc)} 款，新入表 {'、'.join(added) or '无'}，无方案文本 {'、'.join(nolf) or '无'}", args.verbose)

        fp_new = fingerprint(res["text"])
        if name == "鸿蒙智行":
            hima_rows = parse_hima_rows(res["text"])
            if hima_rows:
                for r in sec["rows"]:
                    if r.get("sub") in hima_rows:
                        r["policy"] = hima_rows[r["sub"]]
            res["hima_since"] = hima_activity(res["text"])
        sec.setdefault("fingerprint", {})
        if isinstance(sec["fingerprint"], list):      # 兼容旧版指纹格式
            sec["fingerprint"] = {}
        fp_old = (sec["fingerprint"] or {}).get(name) or []
        first = not fp_old or isinstance(fp_old, list) and not fp_old
        diff = [x for x in fp_new if x not in fp_old] if fp_old else []

        dates = sorted(window_dates(res["text"]))
        since = dates[0] if dates else None
        _, since_txt = judge_change(since, win["start"])

        # 追加探测页结果 → 影响核对结论
        bad_probe = [p for p in res.get("probes", []) if not p["ok"]]
        probe_txt = "；".join(f"{p['url'].split('/')[-1]} 未取到（{p['reason']}）" for p in bad_probe)
        scope = cfg.get("scope", "")
        status = "checked"
        if diff or cfg.get("force_partial") or bad_probe:
            status = "partial"

        note = (f"{name} 官网实抓（{res['method']}），方案行数 {len(policy_lines(res['text']))}"
                + (f"，活动期起始 {since[0]}.{since[1]}" if since else ""))
        if scope:
            note += f"；{scope}"
        if diff:
            note += f"；数值变化 {'、'.join(diff[:6])}，表内表述待人工确认"
        if bad_probe:
            note += f"；{probe_txt}"
        if res.get("_added"):
            note += f"；官网新车型已补行：{'、'.join(res['_added'])}"
        if res.get("_nop"):
            note += f"；官网已列车型但方案页无文本：{'、'.join(res['_nop'])}"

        res_map[name] = {
            "status": status, "url": cfg["url"], "method": res["method"],
            "since": since, "diff": diff, "note": note, "gap": probe_txt,
            "hima_since": res.get("hima_since"), "nop": res.get("_nop") or [],
        }
        sec["fingerprint"][name] = fp_new
        if diff:
            changes.append(f"{name}：{'、'.join(diff[:6])}")

    # 比亚迪/腾势：把长段落提炼成“车型：短要点”，并对上周同样口径归一后再比对
    def _compact_sec(d):
        for sc in d["sections"]:
            fn = {"比亚迪": compact_byd, "鸿蒙智行": compact_hima, "极氪": compact_zeekr, "理想": compact_li}.get(sc["brand"])
            for r2 in sc["rows"]:
                if not r2.get("policy"):
                    continue
                sm = {}
                for ln2 in r2["policy"]:
                    if "：" not in ln2:
                        continue
                    h2 = re.sub(r"（[^）]*）", "", ln2.split("：")[0]).strip()
                    ds2 = window_dates(ln2)
                    if ds2:
                        sm[h2] = ds2[0]
                if sm:
                    r2["since_map"] = sm
                if fn:
                    r2["policy"] = fn(r2["policy"])
                r2["policy"] = drop_perks(r2["policy"])
    _compact_sec(data)
    if PREV:
        _compact_sec(PREV)

    # 同一 section 可能有多个抓取来源（比亚迪/腾势、蔚来/乐道），统一汇总状态与备注
    for sec in data["sections"]:
        srcs = [n for n in names if SECTION_OF.get(n) == sec["brand"]]
        if not srcs:
            continue
        notes, gaps, urls, sts = [], [], [], []
        for n in srcs:
            r = res_map.get(n)
            if not r:
                continue
            notes.append(r["note"])
            if r["gap"]:
                gaps.append(r["gap"])
            urls.append(r["url"])
            sts.append(r["status"])
        status = "checked" if sts and all(s == "checked" for s in sts) else "partial"
        if not sts:
            status = sec["verified"].get("status", "pending")
        sec["verified"] = {
            "status": status,
            "url": urls[0] if urls else sec["verified"].get("url", ""),
            "checked_at": stamp,
            "note": "；".join(notes),
            "gap": "；".join(gaps),
        }

        # 周度变化：只对照上一周表 —— 抓不到=无法爬取；无差异=无变化；有差异=变化（起M.D）
        used = set()
        row_srcs = []
        for r in sec["rows"]:
            sub = r.get("sub") or ""
            if len(srcs) == 1:
                hit = list(srcs)
            else:
                hit = [n for n in srcs if n == sub or (sub and n in sub)]
                if not hit:
                    hit = next(([n] for n in srcs if n not in used), [])
            used |= set(hit)
            row_srcs.append(hit)

        prev_sec = None
        if PREV:
            prev_sec = next((x for x in PREV["sections"] if x["brand"] == sec["brand"]), None)

        for r, rs in zip(sec["rows"], row_srcs):
            if any(res_map.get(n, {}).get("failed") for n in rs) or not r.get("policy"):
                r["change"]["items"] = [{"kind": "fail", "since": "", "text": ""}]
                continue
            items = []
            pr = None
            if prev_sec:
                pr = next((x for x in prev_sec["rows"] if x.get("sub") == r.get("sub")), None)
            if pr:
                new_keys, rate_chg, org_chg = week_diff(pr, r)
                for k in new_keys:
                    line = next((x for x in r["policy"] if k in policy_models(x)), "")
                    ds = window_dates(line)
                    if not ds:
                        ds = [x for x in [res_map.get(n, {}).get("hima_since") for n in rs] if x][:1]
                    if not ds and BASE_REF:
                        for sc2 in BASE_REF["sections"]:
                            if sc2["brand"] != sec["brand"]:
                                continue
                            for r3 in sc2["rows"]:
                                if (r3.get("sub") or "") != (r.get("sub") or ""):
                                    continue
                                for ln3 in r3.get("policy") or []:
                                    if k in policy_models(ln3):
                                        ds3 = window_dates(ln3)
                                        if ds3:
                                            ds = [ds3[0]]
                                            break
                                if ds:
                                    break
                    if not ds and r.get("since_map"):
                        for h2, d2 in r["since_map"].items():
                            if k == h2 or h2.startswith(k) or k.startswith(h2):
                                ds = [d2]
                                break
                    since_s = f"{ds[0][0]}.{ds[0][1]}" if ds else ""
                    label = f"{r.get('sub')}{k}" if r.get("sub") else k
                    items.append({"kind": "change", "since": since_s, "text": f"新增 {label} 方案"})
                if rate_chg:
                    items.append({"kind": "change", "since": "",
                                  "text": "费率更新 " + " / ".join(pr.get("rates", []))
                                           + " → " + " / ".join(r.get("rates", []))})
                if org_chg:
                    items.append({"kind": "change", "since": "", "text": "合作机构更新"})
                # 官网已列、方案页无正文的新车型 → 变化（待核）
                pm = set()
                for pr2 in prev_sec["rows"]:
                    for pl in (pr2.get("policy") or []):
                        pm |= {re.sub(r"^20\d\d款", "", x) for x in policy_models(pl)}
                for n in rs:
                    for m in (res_map.get(n, {}).get("nop") or []):
                        m0 = re.sub(r"^20\d\d款", "", m)
                        if any(m0 == re.sub(r"^20\d\d款", "", x) for x in pm):
                            continue
                        items.append({"kind": "change", "since": "",
                                      "text": f"新增 {m}（官网已列，方案页无正文，待核）"})
            # 只保留“上一周窗口或本周”内的新增，更早的历史变化一律不写
            lws = (win["start"] - timedelta(days=7)).date()
            kept = []
            for it in items:
                if it.get("text", "").startswith("新增") and it.get("since"):
                    try:
                        mm, dd = it["since"].split(".")[:2]
                        dt = datetime(now_cn().year, int(mm), int(dd)).date()
                        if dt < lws:
                            continue
                    except Exception:
                        pass
                kept.append(it)
            r["change"]["items"] = kept or [{"kind": "none", "since": "", "text": ""}]

    data["digest_lead"] = (
        f"{stamp} 独立抓取：{len(names)} 个来源，"
        + ("数值变化 " + "；".join(changes) if changes else "金融数值无变化，仅更新时间戳")
        + ("；异常：" + "；".join(problems) if problems else "")
    )
    data["checked_at_all"] = f"{stamp} 抓取"

    # 统计与落盘
    n_checked = sum(1 for s in data["sections"] if s["verified"]["status"] == "checked")
    n_partial = sum(1 for s in data["sections"] if s["verified"]["status"] == "partial")
    n_pending = sum(1 for s in data["sections"] if s["verified"]["status"] == "pending")
    data["stats"] = {"checked": n_checked, "partial": n_partial, "pending": n_pending}
    save_json(data_path, data)
    print(f"JSON  {data_path.relative_to(BASE)}  checked {n_checked} / partial {n_partial} / pending {n_pending}")

    if args.render_only:
        pass

    from render import render_html
    html = render_html(data)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "友商金融政策动态-周报表.html"
    out.write_text(html, encoding="utf-8")
    print(f"HTML  {out.relative_to(BASE)}  {len(html)} chars")

    if problems:
        print("\n未取到：")
        for p in problems:
            print("  -", p)
    if changes:
        print("\n数值变化：")
        for c in changes:
            print("  -", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
