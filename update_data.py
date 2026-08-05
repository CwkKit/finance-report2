import yfinance as yf
import pandas as pd
import json
import time
from datetime import datetime

TICKERS = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'JPM']

def fetch_stock_data():
    master_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 開始抓取美股基本面數據...")

    for ticker in TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            mkt_cap = info.get('marketCap', 0)
            
            data_dict = {
                "ticker": ticker,
                "name": info.get('shortName', ticker),
                "price": round(price, 2) if isinstance(price, (int, float)) else price,
                "marketCap": round(mkt_cap / 1e9, 2) if mkt_cap else 0,
                "pe": round(info.get('trailingPE', 0), 2),
                "ps": round(info.get('priceToSalesTrailing12Months', 0), 2),
                "eps": round(info.get('trailingEps', 0), 2),
                "margin": round(info.get('profitMargins', 0) * 100, 2),
                "evEbitda": round(info.get('enterpriseToEbitda', 0), 2),
                "nextEarnings": "待公佈", 
                "moat": f"{info.get('longBusinessSummary', '暫無公司介紹。')[:150]}...",
                "history": []
            }

            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    future_earnings = earnings[earnings.index > pd.Timestamp.now(tz='UTC')]
                    if not future_earnings.empty:
                        data_dict["nextEarnings"] = future_earnings.index[-1].strftime('%Y-%m-%d')
                    
                    past_earnings = earnings[earnings.index < pd.Timestamp.now(tz='UTC')].head(3)
                    for idx, row in past_earnings.iterrows():
                        est = row.get('EPS Estimate', 0)
                        act = row.get('Reported EPS', 0)
                        surprise = row.get('Surprise(%)', 0)
                        if pd.isna(est) or pd.isna(act): continue
                            
                        surprise_pct = round(surprise * 100, 2) if not pd.isna(surprise) else 0
                        data_dict["history"].append({
                            "quarter": idx.strftime('%Y Q%q'),
                            "est": round(est, 2),
                            "actual": round(act, 2),
                            "surprise": surprise_pct,
                            "beat": True if surprise_pct > 0 else False
                        })
            except Exception as e_earn:
                pass

            master_data.append(data_dict)
            time.sleep(1)
        except Exception as e:
            pass

    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    fetch_stock_data()
