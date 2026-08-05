import yfinance as yf
import pandas as pd
import json
import time
from datetime import datetime

def get_market_tickers():
    print("正在抓取 S&P 500 與 NASDAQ 100 成分股名單...")
    sp500_tickers = []
    nasdaq_tickers = []
    
    try:
        # 抓取 S&P 500
        tables_sp = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        sp500_tickers = [t.replace('.', '-') for t in tables_sp[0]['Symbol'].tolist()]
    except Exception as e:
        print(f"S&P 500 名單抓取失敗: {e}")

    try:
        # 抓取 NASDAQ 100
        tables_nq = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        # 尋找包含 Ticker/Symbol 的表格
        for df in tables_nq:
            if 'Ticker' in df.columns:
                nasdaq_tickers = [t.replace('.', '-') for t in df['Ticker'].tolist()]
                break
            elif 'Symbol' in df.columns:
                nasdaq_tickers = [t.replace('.', '-') for t in df['Symbol'].tolist()]
                break
    except Exception as e:
        print(f"NASDAQ 名單抓取失敗: {e}")

    # 合併不重複的股票清單
    all_tickers = sorted(list(set(sp500_tickers + nasdaq_tickers)))
    
    # 建立標籤字典
    ticker_market_map = {}
    for t in all_tickers:
        if t in nasdaq_tickers and t in sp500_tickers:
            ticker_market_map[t] = 'BOTH'
        elif t in nasdaq_tickers:
            ticker_market_map[t] = 'NASDAQ'
        else:
            ticker_market_map[t] = 'S&P 500'
            
    return all_tickers, ticker_market_map

def fetch_stock_data():
    all_tickers, ticker_market_map = get_market_tickers()
    
    # 如果抓取失敗，提供熱門備用清單
    if not all_tickers:
        all_tickers = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMZN', 'META', 'GOOGL', 'BRK-B', 'JPM', 'JNJ', 'HD', 'XOM', 'COST', 'CVX', 'AVGO']
        ticker_market_map = {t: 'S&P 500' for t in all_tickers}

    master_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 開始抓取共 {len(all_tickers)} 檔股票數據...")

    for i, ticker in enumerate(all_tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 股價與基本面
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            if not price or price == 0:
                continue # 跳過無效資料
                
            profit_margin = info.get('profitMargins', 0)
            profit = round(profit_margin * 100, 1) if profit_margin else 0.0
            
            data_dict = {
                "ticker": ticker,
                "name": info.get('shortName', ticker),
                "sector": info.get('sector', '未知板塊'),
                "marketIndex": ticker_market_map.get(ticker, 'S&P 500'),
                "price": round(price, 2),
                "profit": profit,
                "pe": round(info.get('trailingPE', 0) or 0, 2),
                "pb": round(info.get('priceToBook', 0) or 0, 2),
                "ps": round(info.get('priceToSalesTrailing12Months', 0) or 0, 2),
                "evEbitda": round(info.get('enterpriseToEbitda', 0) or 0, 2),
                "shortDesc": info.get('industry', '暫無簡介'),
                "story": info.get('longBusinessSummary', '暫無詳細公司故事與簡介。'),
                "estEps": 0.0,
                "actEps": 0.0,
                "surprise": 0.0,
                "nextEarnings": "待公佈",
                "history": []
            }

            # 抓取財報數據
            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    # 1. 未來財報日
                    future_earnings = earnings[earnings.index > pd.Timestamp.now(tz='UTC')].sort_index()
                    if not future_earnings.empty:
                        data_dict["nextEarnings"] = future_earnings.index[0].strftime('%Y-%m-%d')

                    # 2. 過去財報歷史 (解決「上季表現 -」的根本問題)
                    past_earnings = earnings[earnings.index <= pd.Timestamp.now(tz='UTC')].sort_index(ascending=False)
                    
                    if not past_earnings.empty:
                        # 找到第一筆有效的過去財報
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            if pd.notna(act):
                                est = row.get('EPS Estimate', 0) or 0
                                surp = row.get('Surprise(%)', 0) or 0
                                surp_pct = round(surp * 100, 2)
                                
                                data_dict["estEps"] = round(est, 2)
                                data_dict["actEps"] = round(act, 2)
                                data_dict["surprise"] = surp_pct
                                break

                        # 填充歷史紀錄表格 (最多8季)
                        count = 0
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            if pd.isna(act): continue
                            
                            est = row.get('EPS Estimate', 0) or 0
                            surp = row.get('Surprise(%)', 0) or 0
                            surp_pct = round(surp * 100, 2)
                            
                            data_dict["history"].append({
                                "quarter": f"{idx.year} Q{(idx.month-1)//3 + 1}",
                                "est": round(est, 2),
                                "act": round(act, 2),
                                "surprise": surp_pct,
                                "status": "Beat" if surp_pct > 0 else "Miss"
                            })
                            count += 1
                            if count >= 8: break
            except Exception as e_earn:
                pass

            master_data.append(data_dict)
            if (i + 1) % 10 == 0:
                print(f"已成功爬取 {i + 1} 檔股票...")
            time.sleep(0.2) # 輕微間隔防封鎖
            
        except Exception as e:
            print(f"跳過 {ticker}: {e}")

    # 存檔
    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)
        
    print(f"完成！共成功儲存 {len(master_data)} 檔美股資料至 sp500_data.json")

if __name__ == "__main__":
    fetch_stock_data()
