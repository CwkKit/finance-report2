import yfinance as yf
import pandas as pd
import json
import time
from datetime import datetime

# 在此處設定股票與其所屬的指數分類
TICKER_MAP = {
    # NASDAQ (NQ) 代表
    'NVDA': 'NASDAQ', 'AAPL': 'NASDAQ', 'MSFT': 'NASDAQ', 
    'AMZN': 'NASDAQ', 'META': 'NASDAQ', 'GOOGL': 'NASDAQ', 
    'TSLA': 'NASDAQ', 'AVGO': 'NASDAQ', 'COST': 'NASDAQ',
    # S&P 500 (SPY) 傳統代表
    'JPM': 'S&P 500', 'BRK-B': 'S&P 500', 'UNH': 'S&P 500', 
    'JNJ': 'S&P 500', 'XOM': 'S&P 500', 'PG': 'S&P 500', 
    'V': 'S&P 500', 'HD': 'S&P 500', 'CVX': 'S&P 500'
}

def fetch_stock_data():
    master_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 開始抓取美股最新數據...")

    for ticker, market_index in TICKER_MAP.items():
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            profit_margin = info.get('profitMargins', 0)
            profit = round(profit_margin * 100, 1) if profit_margin else 0.0
            
            # 建立資料字典 (新增 marketIndex 欄位)
            data_dict = {
                "ticker": ticker,
                "name": info.get('shortName', ticker),
                "sector": info.get('sector', '未知板塊'),
                "marketIndex": market_index,  # 新增：S&P 500 或 NASDAQ
                "price": round(info.get('currentPrice', info.get('regularMarketPrice', 0)), 2),
                "profit": profit,
                "pe": round(info.get('trailingPE', 0), 2),
                "pb": round(info.get('priceToBook', 0), 2),
                "ps": round(info.get('priceToSalesTrailing12Months', 0), 2),
                "evEbitda": round(info.get('enterpriseToEbitda', 0), 2),
                "shortDesc": info.get('industry', '暫無產業簡介'),
                "story": info.get('longBusinessSummary', '暫無詳細企業故事。'),
                "estEps": 0.0,
                "actEps": 0.0,
                "nextEarnings": "待公佈",
                "history": []
            }

            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    future_earnings = earnings[earnings.index > pd.Timestamp.now(tz='UTC')]
                    if not future_earnings.empty:
                        data_dict["nextEarnings"] = future_earnings.index[-1].strftime('%Y-%m-%d')
                    
                    past_earnings = earnings[earnings.index < pd.Timestamp.now(tz='UTC')].head(4)
                    
                    if not past_earnings.empty:
                        latest = past_earnings.iloc[0]
                        data_dict["estEps"] = round(latest.get('EPS Estimate', 0) or 0, 2)
                        data_dict["actEps"] = round(latest.get('Reported EPS', 0) or 0, 2)

                        for idx, row in past_earnings.head(3).iterrows():
                            est = row.get('EPS Estimate', 0)
                            act = row.get('Reported EPS', 0)
                            surp = row.get('Surprise(%)', 0)
                            
                            if pd.isna(est) or pd.isna(act): continue
                                
                            surp_pct = round(surp * 100, 2) if not pd.isna(surp) else 0
                            data_dict["history"].append({
                                "quarter": f"{idx.year} Q{(idx.month-1)//3 + 1}",
                                "est": round(est, 2),
                                "act": round(act, 2),
                                "surprise": surp_pct,
                                "status": "Beat" if surp_pct > 0 else "Miss"
                            })
            except Exception as e_earn:
                pass

            master_data.append(data_dict)
            print(f"成功處理: {ticker} ({market_index})")
            time.sleep(1)
            
        except Exception as e:
            print(f"處理 {ticker} 時發生錯誤: {e}")

    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    fetch_stock_data()
