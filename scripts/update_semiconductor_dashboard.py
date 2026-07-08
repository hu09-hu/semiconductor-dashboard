#!/usr/bin/env python3
import datetime as dt
import html
import json
import re
import ssl
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


LISTED = ["3711", "2449", "6257", "6239"]
OTC = ["6147"]
STOCKS = LISTED + OTC
NAMES = {
    "3711": "日月光投控",
    "2449": "京元電",
    "6257": "矽格",
    "6239": "力成",
    "6147": "頎邦",
}


def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    context = ssl._create_unverified_context()
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=25, context=context) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(2 + attempt * 2)
    raise last_error


def num(value):
    if value in ("", "--", None):
        return 0.0
    text = re.sub(r"[^0-9.\-]", "", str(value).replace(",", "").replace("+", ""))
    return float(text) if text not in ("", "-", ".") else 0.0


def intnum(value):
    return int(num(value))


def roc_to_ad(value):
    year, month, day = map(int, value.split("/"))
    return f"{year + 1911:04d}{month:02d}{day:02d}"


def ad_to_slash(value):
    return f"{value[:4]}/{value[4:6]}/{value[6:]}"


def ad_to_label(value):
    return f"{int(value[4:6])}/{int(value[6:])}"


def month_starts(end_date, months=5):
    year = end_date.year
    month = end_date.month
    out = []
    for offset in range(months - 1, -1, -1):
        m = month - offset
        y = year
        while m <= 0:
            y -= 1
            m += 12
        out.append(f"{y:04d}{m:02d}01")
    return out


def read_prices(end_ad):
    end_date = dt.datetime.strptime(end_ad, "%Y%m%d").date()
    months = month_starts(end_date, 5)
    prices = {stock: [] for stock in STOCKS}

    for stock in LISTED:
        seen = set()
        for month in months:
            data = fetch(
                f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
                f"?date={month}&stockNo={stock}&response=json"
            )
            for row in data.get("data", []):
                ad = roc_to_ad(row[0])
                if ad in seen or ad > end_ad:
                    continue
                seen.add(ad)
                prices[stock].append(
                    {
                        "date": ad,
                        "amount": intnum(row[2]),
                        "shares": intnum(row[1]),
                        "close": num(row[6]),
                        "change": num(row[7]),
                    }
                )

    for stock in OTC:
        seen = set()
        for month in months:
            date_arg = ad_to_slash(month)
            data = fetch(
                f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
                f"?date={date_arg}&code={stock}&response=json"
            )
            for row in data.get("tables", [{}])[0].get("data", []):
                ad = roc_to_ad(row[0])
                if ad in seen or ad > end_ad:
                    continue
                seen.add(ad)
                prices[stock].append(
                    {
                        "date": ad,
                        "amount": intnum(row[2]) * 1000,
                        "shares": intnum(row[1]) * 1000,
                        "close": num(row[6]),
                        "change": num(row[7]),
                    }
                )

    for rows in prices.values():
        rows.sort(key=lambda item: item["date"])
    return prices


def read_institutions(dates):
    institutions = {stock: {} for stock in STOCKS}
    for date in dates:
        data = fetch(
            f"https://www.twse.com.tw/rwd/zh/fund/T86"
            f"?date={date}&selectType=ALLBUT0999&response=json"
        )
        for row in data.get("data", []):
            if row[0] in LISTED:
                institutions[row[0]][date] = {
                    "foreign": intnum(row[4]) + intnum(row[7]),
                    "trust": intnum(row[10]),
                    "dealer": intnum(row[11]),
                    "total": intnum(row[-1]),
                }

        otc_data = fetch(
            f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
            f"?date={ad_to_slash(date)}&type=Daily&response=json"
        )
        for row in otc_data.get("tables", [{}])[0].get("data", []):
            if row[0] in OTC:
                institutions[row[0]][date] = {
                    "foreign": intnum(row[10]),
                    "trust": intnum(row[13]),
                    "dealer": intnum(row[22]),
                    "total": intnum(row[-1]),
                }
    return institutions


def stock_rows(prices, stock, dates):
    by_date = {row["date"]: row for row in prices[stock]}
    return [by_date[date] for date in dates if date in by_date]


def sum_inst(institutions, stock, dates):
    result = {"total": 0, "foreign": 0, "trust": 0, "dealer": 0}
    for date in dates:
        row = institutions[stock].get(date, {})
        for key in result:
            result[key] += row.get(key, 0)
    return result


def stock_window(prices, institutions, stock, dates):
    rows = stock_rows(prices, stock, dates)
    amount = sum(row["amount"] for row in rows)
    ret = (rows[-1]["close"] / rows[0]["close"] - 1) * 100 if len(rows) > 1 and rows[0]["close"] else 0
    up_days = sum(1 for row in rows if row["change"] > 0)
    inst = sum_inst(institutions, stock, dates)
    return {
        "amount": amount,
        "ret": ret,
        "up_days": up_days,
        "days": len(rows),
        "start": rows[0]["close"],
        "end": rows[-1]["close"],
        **inst,
    }


def group_window(prices, institutions, dates):
    amount = inst = foreign = trust = dealer = 0
    rets = []
    advancers = 0
    for stock in STOCKS:
        metric = stock_window(prices, institutions, stock, dates)
        amount += metric["amount"]
        inst += metric["total"]
        foreign += metric["foreign"]
        trust += metric["trust"]
        dealer += metric["dealer"]
        rets.append(metric["ret"])
        if metric["ret"] > 0:
            advancers += 1
    return {
        "from": dates[0],
        "to": dates[-1],
        "days": len(dates),
        "amount": amount,
        "avg_amount": amount / len(dates),
        "inst": inst,
        "foreign": foreign,
        "trust": trust,
        "dealer": dealer,
        "avg_ret": sum(rets) / len(rets),
        "advancers": advancers,
    }


def score_for(prices, institutions, all_dates, days):
    current = all_dates[-days:]
    previous = all_dates[-2 * days : -days] if len(all_dates) >= 2 * days else all_dates[:-days]
    cur = group_window(prices, institutions, current)
    prev = group_window(prices, institutions, previous) if previous else cur
    amount_growth = (cur["avg_amount"] / prev["avg_amount"] - 1) * 100 if prev["avg_amount"] else 0
    inst_ratio = cur["inst"] / 1000 / (cur["amount"] / 1e9) if cur["amount"] else 0
    volume_score = max(0, min(100, 50 + amount_growth * 1.2))
    inst_score = max(0, min(100, 50 + inst_ratio * 2.2))
    price_score = max(0, min(100, 50 + cur["avg_ret"] * 3.0))
    breadth_score = cur["advancers"] / len(STOCKS) * 100
    score = round(volume_score * 0.4 + inst_score * 0.3 + price_score * 0.2 + breadth_score * 0.1)
    return {
        "score": score,
        "amount_growth": amount_growth,
        "inst_ratio": inst_ratio,
        "current": cur,
        "previous": prev,
    }


def fmt_amount(value):
    return f"{value / 100_000_000:,.0f} 億"


def fmt_lots(value):
    sign = "+" if value > 0 else ""
    return f"{sign}{value / 1000:,.0f} 張"


def fmt_pct(value):
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def css_class(value):
    return "positive" if value > 0 else "negative" if value < 0 else ""


def status_for(stock, metric):
    if stock == "3711":
        return "風向球", "watch"
    if metric["total"] > 0 and metric["ret"] > 0:
        return "轉強", "good"
    if metric["total"] < 0 and metric["ret"] < 0:
        return "落後", "bad"
    return "觀察", "watch"


def rank_scores(stock_metrics):
    raw = {}
    for stock, metric in stock_metrics.items():
        raw[stock] = 50 + metric["ret"] * 1.8 + (metric["total"] / 1000) * 0.35
    min_raw = min(raw.values())
    max_raw = max(raw.values())
    result = {}
    for stock, value in raw.items():
        if max_raw == min_raw:
            result[stock] = 50
        else:
            result[stock] = round(25 + (value - min_raw) / (max_raw - min_raw) * 60)
    return result


def build_html(latest_date, summaries, stock_metrics, daily20):
    s5, s20, s60 = summaries[5], summaries[20], summaries[60]
    ranks = rank_scores(stock_metrics)
    sorted_ranks = sorted(ranks.items(), key=lambda item: item[1], reverse=True)
    today = dt.datetime.strptime(latest_date, "%Y%m%d").date()
    subtitle = (
        f"更新日：{today:%Y/%m/%d}｜主分析：{ad_to_label(s20['current']['from'])} 至 "
        f"{ad_to_label(s20['current']['to'])}，共 20 個交易日｜輔助觀察：近 5 日與近 60 日"
    )
    signal = "轉強" if s5["score"] >= 70 and s20["score"] >= 65 else "觀察中" if s20["score"] >= 60 else "偏弱"
    rank_rows = "\n".join(
        f"""
          <div class="rank-row">
            <strong>{html.escape(NAMES[stock])}</strong>
            <div class="track"><div class="fill {'bad' if score < 45 else 'warn' if score < 70 else ''}" style="width: {score}%"></div></div>
            <span>{score}</span>
          </div>"""
        for stock, score in sorted_ranks
    )
    table_rows = []
    for stock in STOCKS:
        metric = stock_metrics[stock]
        status, kind = status_for(stock, metric)
        table_rows.append(
            f"""
            <tr>
              <td>{stock}</td><td>{html.escape(NAMES[stock])}</td><td>{fmt_amount(metric['amount'])}</td>
              <td>{metric['start']:.1f}</td><td>{metric['end']:.1f}</td>
              <td class="{css_class(metric['ret'])}">{fmt_pct(metric['ret'])}</td>
              <td class="{css_class(metric['total'])}">{fmt_lots(metric['total'])}</td>
              <td class="{css_class(metric['foreign'])}">{fmt_lots(metric['foreign'])}</td>
              <td class="{css_class(metric['trust'])}">{fmt_lots(metric['trust'])}</td>
              <td><span class="pill {kind}">{html.escape(status)}</span></td>
            </tr>"""
        )
    daily_points = []
    min_amount = min(row["amount"] for row in daily20)
    max_amount = max(row["amount"] for row in daily20)
    for i, row in enumerate(daily20):
        x = 48 + i * (612 - 48) / (len(daily20) - 1)
        y = 218 - ((row["amount"] - min_amount) / (max_amount - min_amount or 1)) * 180
        daily_points.append(f"{x:.0f},{y:.0f}")
    score_bars = []
    for idx, (label, summary, klass) in enumerate(
        [("5日", s5, "bar-negative"), ("20日", s20, "bar-positive"), ("60日", s60, "bar-amber")]
    ):
        x = 106 + idx * 170
        height = summary["score"] / 100 * 180
        y = 218 - height
        score_bars.append((label, summary["score"], klass, x, y, height))

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>封測資金輪動儀表板</title>
  <style>
    :root {{ --bg:#f7f8f4; --panel:#fff; --ink:#1d251f; --muted:#667066; --line:#dfe4d8; --green:#238263; --red:#c94b3a; --amber:#c8841f; --teal:#0f9f9a; --shadow:0 10px 28px rgba(38,48,38,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif; background:var(--bg); color:var(--ink); line-height:1.5; }}
    header {{ padding:28px clamp(18px,4vw,44px) 18px; border-bottom:1px solid var(--line); background:#fbfcf8; }}
    .topbar, main, footer {{ max-width:1280px; margin:0 auto; }}
    .topbar {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
    h1 {{ margin:0 0 8px; font-size:clamp(26px,3vw,40px); }}
    .subtitle, footer {{ color:var(--muted); font-size:13px; }}
    .badge {{ white-space:nowrap; padding:8px 12px; border:1px solid #cbd8c8; background:#eef7ed; color:#1d6c4e; border-radius:999px; font-weight:700; font-size:13px; }}
    main {{ padding:22px clamp(18px,4vw,44px) 44px; }}
    .grid {{ display:grid; gap:14px; }}
    .kpis {{ grid-template-columns:repeat(4,minmax(0,1fr)); margin-bottom:16px; }}
    .layout {{ grid-template-columns:1.25fr .75fr; align-items:start; }}
    .two-col {{ grid-template-columns:1fr 1fr; margin-top:16px; }}
    .notes {{ margin-top:16px; grid-template-columns:repeat(3,minmax(0,1fr)); }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; min-width:0; }}
    .kpi-label {{ color:var(--muted); font-size:13px; margin-bottom:8px; }}
    .kpi-value {{ font-size:28px; font-weight:800; line-height:1.1; }}
    .kpi-note, .note-body {{ color:var(--muted); font-size:13px; margin-top:8px; }}
    h2 {{ margin:0 0 12px; font-size:19px; }}
    .positive {{ color:var(--green); }} .negative {{ color:var(--red); }} .warning {{ color:var(--amber); }}
    .decision {{ display:grid; grid-template-columns:116px 1fr; gap:14px; align-items:center; }}
    .score-ring {{ width:116px; aspect-ratio:1; border-radius:50%; background:conic-gradient(var(--amber) 0 {s20['score']}%, #eceee6 {s20['score']}% 100%); display:grid; place-items:center; position:relative; }}
    .score-ring::after {{ content:""; position:absolute; inset:12px; background:var(--panel); border-radius:50%; }}
    .score-ring strong {{ position:relative; z-index:1; font-size:28px; }}
    .decision-title {{ font-size:22px; font-weight:800; margin-bottom:6px; }}
    .decision-text {{ color:var(--muted); margin:0; }}
    .signal-list {{ display:grid; gap:10px; margin-top:14px; }}
    .signal {{ display:flex; justify-content:space-between; gap:12px; padding:10px 12px; border-radius:8px; background:#f8faf5; border:1px solid var(--line); font-size:14px; }}
    .rank-list {{ display:grid; gap:12px; }}
    .rank-row {{ display:grid; grid-template-columns:72px 1fr 52px; gap:10px; align-items:center; font-size:14px; }}
    .track {{ height:10px; border-radius:999px; background:#edf0e8; overflow:hidden; }}
    .fill {{ height:100%; border-radius:999px; background:var(--green); }} .fill.warn {{ background:var(--amber); }} .fill.bad {{ background:var(--red); }}
    .chart {{ width:100%; height:260px; overflow:visible; }} .axis-label {{ fill:#6d756d; font-size:12px; }}
    .line-amount {{ fill:none; stroke:var(--teal); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; }}
    .bar-positive {{ fill:var(--green); }} .bar-negative {{ fill:var(--red); }} .bar-amber {{ fill:var(--amber); }}
    .table-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); min-width:780px; }}
    th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:right; font-size:14px; }}
    th {{ color:var(--muted); background:#f7f9f3; }} th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) {{ text-align:left; }}
    .pill {{ display:inline-flex; padding:4px 8px; border-radius:999px; font-weight:800; font-size:12px; }}
    .pill.good {{ color:var(--green); background:#dff3ea; }} .pill.bad {{ color:var(--red); background:#ffe5df; }} .pill.watch {{ color:var(--amber); background:#fff1d7; }}
    footer {{ padding:0 clamp(18px,4vw,44px) 28px; }}
    @media (max-width:980px) {{ .kpis,.layout,.two-col,.notes {{ grid-template-columns:1fr; }} .topbar {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <header><div class="topbar"><div><h1>封測資金輪動儀表板</h1><p class="subtitle">{html.escape(subtitle)}</p></div><div class="badge">20日 Rotation Score：{s20['score']} / 100｜{signal}</div></div></header>
  <main>
    <section class="grid kpis">
      <div class="card"><div class="kpi-label">20日總成交金額</div><div class="kpi-value">{fmt_amount(s20['current']['amount'])}</div><div class="kpi-note">5 檔封測代表股合計</div></div>
      <div class="card"><div class="kpi-label">20日三大法人</div><div class="kpi-value {css_class(s20['current']['inst'])}">{fmt_lots(s20['current']['inst'])}</div><div class="kpi-note">中段資金方向</div></div>
      <div class="card"><div class="kpi-label">近5日 Rotation Score</div><div class="kpi-value {'positive' if s5['score'] >= 70 else 'negative' if s5['score'] < 45 else 'warning'}">{s5['score']}</div><div class="kpi-note">短線加速或退潮</div></div>
      <div class="card"><div class="kpi-label">20日攻擊核心</div><div class="kpi-value">{html.escape(NAMES[sorted_ranks[0][0]])}</div><div class="kpi-note">資金強度排名第一</div></div>
    </section>
    <section class="card" style="margin-bottom:16px"><h2>三週期資金節奏</h2><div class="table-wrap"><table><thead><tr><th>週期</th><th>日期區間</th><th>Rotation Score</th><th>成交金額</th><th>三大法人</th><th>平均股價表現</th><th>判讀</th></tr></thead><tbody>
      <tr><td>5日短線</td><td>{ad_to_label(s5['current']['from'])}-{ad_to_label(s5['current']['to'])}</td><td>{s5['score']}</td><td>{fmt_amount(s5['current']['amount'])}</td><td class="{css_class(s5['current']['inst'])}">{fmt_lots(s5['current']['inst'])}</td><td class="{css_class(s5['current']['avg_ret'])}">{fmt_pct(s5['current']['avg_ret'])}</td><td><span class="pill {'good' if s5['score'] >= 70 else 'bad' if s5['score'] < 45 else 'watch'}">{'轉強' if s5['score'] >= 70 else '退潮' if s5['score'] < 45 else '觀察'}</span></td></tr>
      <tr><td>20日主分析</td><td>{ad_to_label(s20['current']['from'])}-{ad_to_label(s20['current']['to'])}</td><td>{s20['score']}</td><td>{fmt_amount(s20['current']['amount'])}</td><td class="{css_class(s20['current']['inst'])}">{fmt_lots(s20['current']['inst'])}</td><td class="{css_class(s20['current']['avg_ret'])}">{fmt_pct(s20['current']['avg_ret'])}</td><td><span class="pill {'good' if s20['score'] >= 70 else 'watch' if s20['score'] >= 50 else 'bad'}">{'主流確認' if s20['score'] >= 70 else '轉強觀察' if s20['score'] >= 50 else '偏弱'}</span></td></tr>
      <tr><td>60日背景</td><td>{ad_to_label(s60['current']['from'])}-{ad_to_label(s60['current']['to'])}</td><td>{s60['score']}</td><td>{fmt_amount(s60['current']['amount'])}</td><td class="{css_class(s60['current']['inst'])}">{fmt_lots(s60['current']['inst'])}</td><td class="{css_class(s60['current']['avg_ret'])}">{fmt_pct(s60['current']['avg_ret'])}</td><td><span class="pill watch">背景趨勢</span></td></tr>
    </tbody></table></div></section>
    <section class="grid layout">
      <div class="card"><h2>主結論</h2><div class="decision"><div class="score-ring"><strong>{s20['score']}</strong></div><div><div class="decision-title">20日看主流，5日看加速</div><p class="decision-text">若近 5 日分數升破 70、20 日分數續升，且日月光止穩，封測輪動可信度會提高；若近 5 日分數低於 45，代表短線仍在退潮。</p></div></div><div class="signal-list">
        <div class="signal"><span>成交量條件</span><span class="{'positive' if s5['current']['avg_amount'] > s5['previous']['avg_amount'] else 'warning'}">5日均量較前期 {fmt_pct(s5['amount_growth'])}</span></div>
        <div class="signal"><span>法人同步條件</span><span class="{css_class(s5['current']['inst'])}">近5日 {fmt_lots(s5['current']['inst'])}</span></div>
        <div class="signal"><span>上漲家數條件</span><span class="warning">20日 {s20['current']['advancers']}/5 上漲</span></div>
        <div class="signal"><span>成交比重條件</span><span class="warning">可再加入 AI Server、PCB 做相對輪動</span></div>
      </div></div>
      <div class="card"><h2>個股資金強度排名</h2><div class="rank-list">{rank_rows}</div></div>
    </section>
    <section class="grid two-col">
      <div class="card"><h2>20日每日成交金額趨勢</h2><svg class="chart" viewBox="0 0 640 260"><line x1="48" y1="218" x2="612" y2="218" stroke="#dfe4d8"/><line x1="48" y1="38" x2="48" y2="218" stroke="#dfe4d8"/><polyline class="line-amount" points="{' '.join(daily_points)}"/><g fill="#0f9f9a">{"".join(f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="4"/>' for p in daily_points[::3])}</g><g class="axis-label"><text x="38" y="232">{ad_to_label(daily20[0]['date'])}</text><text x="300" y="232">{ad_to_label(daily20[len(daily20)//2]['date'])}</text><text x="590" y="232">{ad_to_label(daily20[-1]['date'])}</text><text x="520" y="52">高點 {fmt_amount(max_amount)}</text><text x="510" y="190">最新 {fmt_amount(daily20[-1]['amount'])}</text></g></svg></div>
      <div class="card"><h2>三週期 Rotation Score</h2><svg class="chart" viewBox="0 0 640 260"><line x1="44" y1="218" x2="612" y2="218" stroke="#bfc8bd"/><g>{''.join(f'<rect class="{klass}" x="{x}" y="{y:.0f}" width="88" height="{height:.0f}" rx="6"/>' for label, score, klass, x, y, height in score_bars)}</g><g class="axis-label">{''.join(f'<text x="{x+12}" y="238">{label}</text><text x="{x+22}" y="{y-8:.0f}">{score}</text>' for label, score, klass, x, y, height in score_bars)}</g></svg></div>
    </section>
    <section class="card" style="margin-top:16px"><h2>代表股明細</h2><div class="table-wrap"><table><thead><tr><th>代號</th><th>股票</th><th>20日成交金額</th><th>期初收盤</th><th>最新收盤</th><th>20日股價變化</th><th>三大法人</th><th>外資</th><th>投信</th><th>狀態</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div></section>
    <section class="grid notes">
      <div class="card"><div class="note-title">下一個轉強訊號</div><p class="note-body">5日 Rotation Score 升破 70、5檔單日成交金額站回 600 億、三大法人由賣轉買。</p></div>
      <div class="card"><div class="note-title">風向球</div><p class="note-body">日月光是封測權值代表，若止穩轉強，族群輪動可信度會提高。</p></div>
      <div class="card"><div class="note-title">風險提醒</div><p class="note-body">若 5日分數低於 45，代表短線退潮，仍需等待資金重新回流。</p></div>
    </section>
  </main>
  <footer>資料來源：台灣證交所、櫃買中心公開行情與三大法人買賣超資料。此儀表板為研究整理，不構成投資建議。</footer>
</body>
</html>
"""


def main():
    today = dt.datetime.now(dt.UTC) + dt.timedelta(hours=8)
    end_ad = today.strftime("%Y%m%d")
    if len(sys.argv) > 1:
        end_ad = sys.argv[1]

    prices = read_prices(end_ad)
    common_dates = sorted(set.intersection(*(set(row["date"] for row in prices[stock]) for stock in STOCKS)))
    if len(common_dates) < 60:
        raise RuntimeError(f"Not enough common trading dates: {len(common_dates)}")
    all_dates = common_dates[-60:]
    latest_date = all_dates[-1]
    # The dashboard's decisive institutional signals are 5D and 20D.
    # Keeping institutional fetches to the recent window makes scheduled runs
    # much more reliable when exchange endpoints are slow.
    institutions = read_institutions(all_dates[-25:])
    summaries = {days: score_for(prices, institutions, all_dates, days) for days in (5, 20, 60)}
    window20 = all_dates[-20:]
    stock_metrics = {stock: stock_window(prices, institutions, stock, window20) for stock in STOCKS}

    daily20 = []
    for date in window20:
        amount = sum(next(row["amount"] for row in prices[stock] if row["date"] == date) for stock in STOCKS)
        inst = sum(institutions[stock].get(date, {}).get("total", 0) for stock in STOCKS)
        daily20.append({"date": date, "amount": amount, "inst": inst})

    root = Path(__file__).resolve().parents[1]
    output = root / "index.html"
    output.write_text(build_html(latest_date, summaries, stock_metrics, daily20), encoding="utf-8")
    print(f"Updated {output} using latest trading date {latest_date}")


if __name__ == "__main__":
    main()
