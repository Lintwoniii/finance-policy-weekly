#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蔚来 / 乐道 金融方案移动端 H5 接口抓取（公开 GET，无需签名，无需浏览器）。

两品牌共用网关 gateway-front-external.nio.com，接口结构一致，仅 moat 编号 / platform / channel 不同。
产品政策为品牌级（金融产品、机构、首付比例、期数不随车型变化，仅月供随车价变），
故每品牌取一个代表车型，依次调用：
  area/list        -> 地区 address_id
  models           -> 车型世代（generation_code / price）
  products         -> 推荐方案 + 自定义方案（含 product_code、合作机构、首付、期数）
  loan-detail      -> 分段年化费率 step_loan_annualized_rate
输出对齐金融周报 row schema（sub/rates/orgs/change/subsidy/policy），所有字段可回溯到接口，不臆造。

用法：python3 mobile_finance.py [--out mobile_rows.json]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

MUA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
       "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

# 品牌接入配置：moat 编号、H5 platform、products channel、Referer。
BRANDS = {
    "蔚来": {"moat": "101082", "platform": "nio_app_wap", "channel": "nio_app",
            "referer": "https://vomtools.nio.com/"},
    "乐道": {"moat": "1100147", "platform": "alps_app_wap", "channel": "alps_app",
            "referer": "https://finance.onvo.cn/"},
}

DEFAULT_ADDR = "310100"  # 上海市；政策口径与地区无关，固定用上海即可


class NioClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = f"https://gateway-front-external.nio.com/moat/{cfg['moat']}/v1/in"
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": MUA, "Referer": cfg["referer"],
                               "Accept": "application/json", "Accept-Language": "zh-CN"})

    def _get(self, endpoint: str) -> dict:
        last = None
        for _ in range(3):  # 代理偶发失败，重试
            try:
                r = self.s.get(f"{self.base}/{endpoint}", timeout=25)
                r.raise_for_status()
                j = r.json()
                if j.get("result_code") == "success":
                    return j
                last = j
            except Exception as exc:  # noqa: BLE001
                last = exc
            time.sleep(1.5)
        if isinstance(last, dict):
            return last
        raise last

    def first_generation(self) -> dict:
        j = self._get(f"finance-calculator/models?platform={self.cfg['platform']}&region=CN")
        for model in j["data"]["models"]:
            for g in model["generations"]:
                return g
        raise RuntimeError("models 接口未返回世代")

    def products(self, gen_code: str, price: str, addr: str = DEFAULT_ADDR) -> list[dict]:
        ep = (f"finance-calculator/products?platform={self.cfg['platform']}&region=CN"
              f"&address_id={addr}&generation_code={gen_code}&total_amount={price}"
              f"&channel={self.cfg['channel']}")
        return self._get(ep)["data"]

    def loan_detail(self, bank_id: str, product_code: str, month: str,
                    amount: str, down_ratio: str = "0.00", addr: str = DEFAULT_ADDR) -> dict:
        ep = (f"finance-calculator/loan-detail?platform={self.cfg['platform']}&region=CN"
              f"&address_id={addr}&amount={amount}&bank_id={bank_id}&product_code={product_code}"
              f"&month={month}&tail_ratio=&down_payment_ratio={down_ratio}")
        return self._get(ep).get("data", {})  # 偶发失败返回空，由调用方降级


def step_rate_text(step: list[dict]) -> str:
    """分段年化费率 -> '0%-3%'。"""
    vals = []
    for seg in step:
        pct = float(seg["amount"]) * 100
        vals.append(f"{pct:g}%")
    uniq = list(dict.fromkeys(vals))
    if not uniq:
        return ""
    return "-".join(uniq) if len(uniq) > 1 else uniq[0]


def extract_rate(detail: dict) -> str:
    """统一费率提取：优先分段年化，缺失则取单值 annualized_rate。"""
    step = detail.get("step_loan_annualized_rate")
    if step:
        return step_rate_text(step)
    ar = detail.get("annualized_rate")
    if ar not in (None, ""):
        return f"{float(ar) * 100:g}%"
    return ""


def is_lease(name: str) -> bool:
    return "融资租赁" in name or "租赁" in name


def scheme_descriptor(detail: dict) -> tuple[str, list[float]]:
    """从 loan-detail 推导标准贴息片段。

    返回 (片段文本, 涉及年化数值)：
      分段 0% N 年 + 后段 X% -> '5免N（后M年X%）', [0, X]
      全期 0%               -> '5年0息', [0]
      单值 X%（无免息）      -> 'X%', [X]
    """
    step = detail.get("step_loan_annualized_rate")
    if step:
        zero_months, back = 0, None
        for seg in step:
            months = int(seg["end_month"]) - int(seg["start_month"]) + 1
            rate = float(seg["amount"])
            if rate == 0:
                zero_months += months
            else:
                back = rate * 100
        if zero_months and back is not None:
            n = zero_months // 12
            return f"5免{n}（后{5 - n}年{back:g}%）", [0.0, back]
        if zero_months and back is None:
            return "5年0息", [0.0]
    ar = detail.get("annualized_rate")
    if ar not in (None, ""):
        v = float(ar) * 100
        return ("5年0息" if v == 0 else f"{v:g}%"), [v]
    return "", []


def build_row(brand: str, client: NioClient) -> dict:
    mj = client._get(f"finance-calculator/models?platform={client.cfg['platform']}&region=CN")
    gens = [(m["model_name"], m["generations"][0])
            for m in mj["data"]["models"] if m.get("generations")]

    all_banks, all_leases = set(), set()
    scheme_groups: dict[str, list[str]] = {}   # 标准贴息片段 -> 车型
    no_free: dict[float, list[str]] = {}       # 无免息车型：常规分期费率 -> 车型
    rate_values: list[float] = []
    yuexi = ""

    for mname, g in gens:
        amt = str(int(float(g["price"])))
        blocks = client.products(g["generation_code"], g["price"])
        cust = next((b for b in blocks if b["type"] == "customize_product"), None)

        prod_details = []
        for prod in (cust["info"] if cust else []):
            fname = prod.get("finance_name", "")
            for pi in prod.get("production_infos", []):
                for bi in pi.get("bank_info_list", []):
                    bn = bi.get("bank_name", "").strip()
                    if bn:
                        (all_leases if is_lease(bn) else all_banks).add(bn)
                bank_bi = next((bi for bi in pi.get("bank_info_list", [])
                                if not is_lease(bi.get("bank_name", ""))), None)
                if bank_bi is None:
                    continue
                down = (bank_bi.get("down_payment_ratio") or ["0.00"])[0]
                month = (bank_bi.get("month") or ["60"])[0]
                detail = client.loan_detail(bank_bi["bank_id"], pi.get("product_code", ""),
                                            month, amt, down)
                prod_details.append((fname, detail))
                time.sleep(0.3)

        # 收集该车型全部免息片段（同一名下可能有多个方案，如 5免3 与 5免2）。
        free = []
        for fname, detail in prod_details:
            if "免息" in fname:
                desc, vals = scheme_descriptor(detail)
                if desc:
                    free.append((desc, vals))
        if free:
            for desc, vals in free:
                scheme_groups.setdefault(desc, []).append(mname)
                rate_values.extend(vals)
        else:
            reg = next((d for fn, d in prod_details if fn == "分期贷"), None)
            if reg and reg.get("annualized_rate") not in (None, ""):
                v = float(reg["annualized_rate"]) * 100
                no_free.setdefault(v, []).append(mname)
                rate_values.append(v)

        for fname, detail in prod_details:
            if fname == "月息年本" and detail.get("annualized_rate") not in (None, ""):
                v = float(detail["annualized_rate"]) * 100
                yuexi = f"20%首付 5年月息年本（年费率{v:g}%）"
                rate_values.append(v)
        time.sleep(0.2)

    # 基础对客费率：全部真实年化的 min-max 区间。
    if rate_values:
        lo, hi = min(rate_values), max(rate_values)
        rate_txt = f"{lo:g}%-{hi:g}%" if lo != hi else f"{lo:g}%"
    else:
        rate_txt = ""

    policy = []
    for desc, cars in scheme_groups.items():
        policy.append(f"{'、'.join(dict.fromkeys(cars))}：0首付 {desc}")
    for v, cars in no_free.items():
        policy.append(f"{'、'.join(dict.fromkeys(cars))}：{v:g}%低首付")
    if yuexi and policy:
        policy[0] = policy[0] + "、" + yuexi
    elif yuexi:
        policy.append(yuexi)
    if all_leases:
        policy.append("融资租赁：" + "、".join(sorted(all_leases)))

    return {
        "sub": brand,
        "rates": [rate_txt],
        "orgs": [["、".join(sorted(all_banks) + sorted(all_leases)), 1]],
        "change": {"items": [{"kind": "none", "since": "", "text": ""}]},
        "subsidy": "有" if (scheme_groups or yuexi) else "无",
        "policy": policy,
    }


def fetch_all() -> list[dict]:
    rows = []
    for brand, cfg in BRANDS.items():
        client = NioClient(cfg)
        rows.append(build_row(brand, client))
        time.sleep(1)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="mobile_rows.json")
    args = ap.parse_args()
    rows = fetch_all()
    out = Path(__file__).resolve().parent / args.out
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print("\n=== sub:", r["sub"], " rates:", r["rates"], " subsidy:", r["subsidy"])
        print(" 机构:", r["orgs"][0][0])
        for p in r["policy"]:
            print(" 政策:", p)
    print("\n写出:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
