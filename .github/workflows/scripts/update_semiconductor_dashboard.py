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
    today = dt.datetime.utcnow() + dt.timedelta(hours=8)
    end_ad = today.strftime("%Y%m%d")
    if len(sys.argv) > 1:
        end_ad = sys.argv[1]

    prices = read_prices(end_ad)
    common_dates = sorted(set.intersection(*(set(row["date"] for row in prices[stock]) for stock in STOCKS)))
    if len(common_dates) < 60:
        raise RuntimeError(f"Not enough common trading dates: {len(common_dates)}")
    all_dates = common_dates[-60:]
    latest_date = all_dates[-1]
    institutions = read_institutions(all_dates)
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
