import yfinance as yf
import pandas as pd
import json
import time
import random
import requests
from datetime import datetime
from deep_translator import GoogleTranslator

def get_dynamic_tickers():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在從維基百科即時抓取最新成分股名單...")
    sp500_tickers = []
    nasdaq_tickers = []
    
    try:
        sp500_df = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
        sp500_tickers = [str(ticker).replace('.', '-') for ticker in sp500_df['Symbol'].tolist()]
    except Exception as e:
        print(f"S&P 500 名單獲取失敗: {e}")

    try:
        nq_tables = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        for df in nq_tables:
            if 'Ticker' in df.columns:
                nasdaq_tickers = [str(ticker).replace('.', '-') for ticker in df['Ticker'].tolist()]
                break
            elif 'Symbol' in df.columns:
                nasdaq_tickers = [str(ticker).replace('.', '-') for ticker in df['Symbol'].tolist()]
                break
    except Exception as e:
        print(f"NASDAQ 名單獲取失敗: {e}")

    # 合併並去重
    all_tickers = sorted(list(set(sp500_tickers + nasdaq_tickers)))
    
    ticker_market_map = {}
    for t in all_tickers:
        if t in nasdaq_tickers and t in sp500_tickers:
            ticker_market_map[t] = 'BOTH'
        elif t in nasdaq_tickers:
            ticker_market_map[t] = 'NASDAQ'
        else:
            ticker_market_map[t] = 'S&P 500'
            
    print(f"🔍 本次共需處理 {len(all_tickers)} 檔股票。")
    return all_tickers, ticker_market_map

def fetch_stock_data():
    all_tickers, ticker_market_map = get_dynamic_tickers()
    
    if not all_tickers:
        print("⚠️ 無法獲取動態名單，使用備用清單...")
        all_tickers = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMZN', 'META', 'GOOGL', 'BRK-B', 'JPM']
        ticker_market_map = {t: 'S&P 500' for t in all_tickers}

    translator = GoogleTranslator(source='en', target='zh-TW')
    master_data = []
    
    # 【破解關鍵 1】建立偽裝的瀏覽器 Session，欺騙 Yahoo Finance 防爬蟲系統
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    })

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 開始抓取共 {len(all_tickers)} 檔股票數據...")

    for i, ticker in enumerate(all_tickers):
        try:
            # 【破解關鍵 2】將偽裝的 session 帶入 yfinance
            stock = yf.Ticker(ticker, session=session)
            info = stock.info
            
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            if not price or price == 0:
                continue
                
            profit_margin = info.get('profitMargins', 0)
            profit = round(profit_margin * 100, 1) if profit_margin else 0.0
            current_pe = info.get('trailingPE', 0)
            
            english_story = info.get('longBusinessSummary', '暫無簡介')
            chinese_story = '暫無簡介'
            if english_story != '暫無簡介':
                try:
                    # 稍微縮減字數避免 Google 翻譯封鎖
                    chinese_story = translator.translate(english_story[:800]) 
                except:
                    chinese_story = english_story 

            data_dict = {
                "ticker": ticker,
                "name": info.get('shortName', ticker),
                "sector": info.get('sector', '未知'),
                "marketIndex": ticker_market_map.get(ticker, 'S&P 500'),
                "price": round(price, 2),
                "profit": profit,
                "pe": round(current_pe, 2) if current_pe else 0,
                "pb": round(info.get('priceToBook', 0) or 0, 2),
                "ps": round(info.get('priceToSalesTrailing12Months', 0) or 0, 2),
                "evEbitda": round(info.get('enterpriseToEbitda', 0) or 0, 2),
                "shortDesc": info.get('industry', '暫無簡介'),
                "story": chinese_story,
                "estEps": 0.0,
                "actEps": 0.0,
                "surprise": 0.0,
                "nextEarnings": "待公佈",
                "fairPe": round(current_pe, 2) if current_pe and current_pe > 0 else 15.0,
                "epsStd": 0.1,
                "history": []
            }

            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    future_earnings = earnings[earnings.index > pd.Timestamp.now(tz='UTC')].sort_index()
                    if not future_earnings.empty:
                        data_dict["nextEarnings"] = future_earnings.index[0].strftime('%Y-%m-%d')
                        for idx, row in future_earnings.head(2).iterrows():
                            est = row.get('EPS Estimate', None)
                            data_dict["history"].append({
                                "quarter": f"{idx.year} Q{(idx.month-1)//3 + 1}",
                                "est": round(est, 2) if pd.notna(est) else "-",
                                "act": "-", "surprise": "-", "status": "等待公佈"
                            })

                    past_earnings = earnings[earnings.index <= pd.Timestamp.now(tz='UTC')].sort_index(ascending=False).head(8)
                    if not past_earnings.empty:
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            if pd.notna(act):
                                est = row.get('EPS Estimate', 0) or 0
                                data_dict["estEps"] = round(est, 2)
                                data_dict["actEps"] = round(act, 2)
                                data_dict["surprise"] = round(float(row.get('Surprise(%)', 0) or 0), 2)
                                break

                        errors = []
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            est = row.get('EPS Estimate', None)
                            
                            if pd.notna(act) and pd.notna(est):
                                errors.append(act - est)
                            
                            if pd.notna(act):
                                surp_pct = round(float(row.get('Surprise(%)', 0) or 0), 2)
                                data_dict["history"].append({
                                    "quarter": f"{idx.year} Q{(idx.month-1)//3 + 1}",
                                    "est": round(est, 2) if pd.notna(est) else 0,
                                    "act": round(act, 2),
                                    "surprise": surp_pct,
                                    "status": "Beat" if surp_pct > 0 else "Miss"
                                })
                        
                        if len(errors) >= 2:
                            eps_std = round(float(pd.Series(errors).std()), 3)
                            data_dict["epsStd"] = eps_std if eps_std > 0 else 0.1

            except Exception as e_earn:
                pass 

            master_data.append(data_dict)
            
            if (i + 1) % 50 == 0:
                print(f"📊 已經成功處理 {i + 1} 檔股票...")
            
            # 【破解關鍵 3】隨機暫停 0.5 到 1.5 秒，模仿人類慢慢看盤的節奏，絕不被抓
            time.sleep(random.uniform(0.5, 1.5)) 
            
        except Exception as e:
            print(f"❌ 處理 {ticker} 時發生未預期錯誤，已跳過。錯誤原因: {e}")

    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)
        
    print(f"🎉 執行完成！共完美儲存 {len(master_data)} 檔美股資料至 JSON。")

if __name__ == "__main__":
    fetch_stock_data()
