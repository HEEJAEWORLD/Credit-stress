#!/usr/bin/env python3
"""
AI 신용 스트레스 대시보드 - 데이터 수집기 (키 불필요)
- 주가: Stooq CSV (CRWV / NBIS / APLD / ^SPX)
- 신용 프록시: FRED CSV (BBB OAS = BAMLC0A4CBBB, AA OAS = BAMLC0A2CAA)
실패 시 직전 값을 그대로 이어받음(carry-forward). 같은 날짜 행은 갱신.
"""
import os, json, csv, io, datetime, sys
import requests

DATA = os.path.join(os.path.dirname(__file__), "data.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (credit-stress-bot)"}
TIMEOUT = 25

def load():
    if os.path.exists(DATA):
        try:
            return json.load(open(DATA, encoding="utf-8"))
        except Exception:
            pass
    return {"series": []}

def last_value(series, key):
    for row in reversed(series):
        v = row.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return v
    return None

def stooq_close(symbol):
    """Stooq 경량 CSV: symbol,date,time,close 형태에서 종가 추출."""
    url = "https://stooq.com/q/l/?s=%s&f=sd2t2c&e=csv" % symbol
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))
        # header + 1 data row
        data = rows[1] if len(rows) > 1 and rows[0][0].lower() == "symbol" else rows[0]
        close = data[-1].strip()
        return float(close)
    except Exception as e:
        print("  ! stooq %s 실패: %s" % (symbol, e), file=sys.stderr)
        return None

def fred_last(series_id):
    """FRED 무료 CSV에서 마지막 유효값(percent). '.' 결측 무시."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s" % series_id
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))[1:]  # skip header
        for row in reversed(rows):
            if len(row) >= 2 and row[1].strip() not in (".", ""):
                return float(row[1])
        return None
    except Exception as e:
        print("  ! fred %s 실패: %s" % (series_id, e), file=sys.stderr)
        return None

def main():
    db = load()
    series = db.get("series", [])
    today = datetime.date.today().isoformat()

    row = {
        "date": today,
        "crwv": stooq_close("crwv.us"),
        "nbis": stooq_close("nbis.us"),
        "apld": stooq_close("apld.us"),
        "spx":  stooq_close("^spx"),
        "bbb_oas": fred_last("BAMLC0A4CBBB"),
        "aa_oas":  fred_last("BAMLC0A2CAA"),
    }

    # carry-forward: 실패한 값은 직전 유효값으로 채움
    for k in ("crwv", "nbis", "apld", "spx", "bbb_oas", "aa_oas"):
        if not row[k] or row[k] <= 0:
            cf = last_value(series, k)
            if cf is not None:
                print("  ~ %s 캐리포워드: %s" % (k, cf))
                row[k] = cf

    # SPX·신용 둘 다 못 받으면 무의미 → 중단
    if not row["spx"] or not row["bbb_oas"]:
        print("핵심 데이터(SPX 또는 BBB OAS) 확보 실패 — 이번 실행 건너뜀.")
        return

    series = [r for r in series if r.get("date") != today] + [row]
    series.sort(key=lambda r: r["date"])
    db["series"] = series
    db["updated"] = today
    json.dump(db, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    diff = (row["bbb_oas"] - row["aa_oas"]) * 100
    print("✓ %s | BBB-AA=%.0fbp | CRWV=%s NBIS=%s APLD=%s SPX=%s"
          % (today, diff, row["crwv"], row["nbis"], row["apld"], row["spx"]))

if __name__ == "__main__":
    main()
