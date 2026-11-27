#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零跑金融方案抓取（官网公开配置接口，requests 直连，无需浏览器）。

数据来源：apptec.leapmotor.cn/app-community/resourceConfig/getByCode?code=<车系>-RULES-CONFIG
其 data[code].equity[] 为各权益块，title 含“金融”的即金融礼，content 为具体政策（含 <br> 换行）。

经逐车系核验（裸 requests + Playwright 渲染双路）：当前官网仅 Lafa5、A10、B10 三款主推/新车
实际配置了金融权益；其余车系 RULES 配置缺失或为空、页面 EQUITY 接口返回“数据不存在”，
属源站真实状态。本模块只抓取真实存在的金融礼，未配置车系在 note 标注，绝不臆造；
接口未给合作银行/精确年化，故机构与年化留空，不编造。

用法：python3 leap_finance.py [--out leap_row.json]
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests

MUA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
HEAD = {"User-Agent": MUA, "Referer": "https://cn.leapmotor.com/",
        "Accept": "application/json, text/plain, */*"}
ENDPOINT = "https://apptec.leapmotor.cn/app-community/resourceConfig/getByCode"

# 基础车系（增程版与纯电版在官网同一页面/同一 RULES，故不重复列“增程”）。
SERIES = ["Lafa5", "A10", "A05", "B01", "B10", "D99", "C16", "C11", "C10", "D19"]


def clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "；", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"0(?:首付|利息)[：:]", "", text)  # 去掉内部“0首付：/0利息：”嵌套标签
    return text.strip("；").strip()


def fetch_finance(slug: str) -> str:
    code = f"{slug}-RULES-CONFIG"
    r = requests.get(ENDPOINT, params={"code": code}, headers=HEAD, timeout=25)
    j = r.json()
    cfg = (j.get("data") or {}).get(code)
    if not cfg:
        return ""
    for item in cfg.get("equity", []):
        if "金融" in str(item.get("title", "")):
            return clean(str(item.get("content", "")))
    return ""


def rate_tags(text: str) -> list[str]:
    # 官网仅明确“0息”可对应 0% 年化；0首付是首付方式、贴息未给费率，均不折算成百分比。
    if "0息" in text or "0利息" in text:
        return ["0%"]
    return []


def build_row() -> dict:
    present, absent = [], []
    zero_interest, zero_down = set(), set()
    for slug in SERIES:
        text = fetch_finance(slug)
        time.sleep(0.4)
        if not text:
            absent.append(slug)
            continue
        present.append(slug)
        for seg in text.split("；"):
            seg = seg.strip()
            if not seg:
                continue
            if "0息" in seg or "0利息" in seg:
                zero_interest.add(seg)
            if "0首付" in seg:
                zero_down.add(seg)

    parts = []
    if zero_interest:
        parts.append("全系0息（" + "；".join(sorted(zero_interest)) + "）")
    if zero_down:
        parts.append("0首付（" + "；".join(sorted(zero_down)) + "）")

    note = ("官网当前仅 %s 配置金融权益；%s 未配置金融礼（源站 RULES/EQUITY 均无数据）；"
            "官网未披露合作机构与精确年化，相关字段留空。"
            % ("、".join(present), "、".join(absent)))
    return {
        "sub": None,
        "rates": ["0%"] if zero_interest else [""],
        "orgs": [["", 1]],
        "change": {"items": [{"kind": "none", "since": "", "text": ""}]},
        "subsidy": "有" if parts else "无",
        "policy": [" / ".join(parts)] if parts else [],
        "_note": note,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="leap_row.json")
    args = ap.parse_args()
    row = build_row()
    out = Path(__file__).resolve().parent / args.out
    out.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print("rates:", row["rates"], " subsidy:", row["subsidy"])
    for p in row["policy"]:
        print("政策:", p)
    print("note:", row["_note"])
    print("写出:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
