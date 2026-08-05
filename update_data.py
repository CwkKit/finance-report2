import yfinance as yf
import pandas as pd
import json
import time
from datetime import datetime

# 您可以在這裡自由新增想追蹤的標的
TICKERS = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMZN']

def fetch_stock_data():
    master_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 開始抓取美股最新基本面與財報數據...")

    for ticker in TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 抓取淨利率並轉為百分比
            profit_margin = info.get('profitMargins', 0)
            profit = round(profit_margin * 100, 1) if profit_margin else 0.0
            
            # 建立符合新版 HTML 的資料結構
            data_dict = {
                "ticker": ticker,
                "name": info.get('shortName', ticker),
                "sector": info.get('sector', '未知板塊'),
                "profit": profit,
                "shortDesc": info.get('industry', '暫無產業簡介'),
                "story": info.get('longBusinessSummary', '暫無詳細企業故事。'),
                "estEps": 0.0,
                "actEps": 0.0,
                "surprise": 0.0,
                "nextEarnings": "待公佈",
                "history": []
            }

            # 抓取財報日與歷史 EPS
            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    # 1. 抓取下次財報日
                    future_earnings = earnings[earnings.index > pd.Timestamp.now(tz='UTC')]
                    if not future_earnings.empty:
                        data_dict["nextEarnings"] = future_earnings.index[-1].strftime('%Y-%m-%d')
                    
                    # 2. 抓取過去財報歷史
                    past_earnings = earnings[earnings.index < pd.Timestamp.now(tz='UTC')].head(4)
                    
                    if not past_earnings.empty:
                        # 將最新一季的 EPS 填入主表格
                        latest = past_earnings.iloc[0]
                        data_dict["estEps"] = round(latest.get('EPS Estimate', 0) or 0, 2)
                        data_dict["actEps"] = round(latest.get('Reported EPS', 0) or 0, 2)
                        data_dict["surprise"] = round((latest.get('Surprise(%)', 0) or 0) * 100, 2)

                        # 將過去 3 季填入彈窗的歷史表格中
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
                print(f"  > 警告: 無法獲取 {ticker} 財報歷史")

            master_data.append(data_dict)
            print(f"成功處理: {ticker}")
            time.sleep(1) # 避免 API 阻擋
            
        except Exception as e:
            print(f"錯誤: {ticker} - {e}")

    # 匯出 JSON
    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    fetch_stock_data()
