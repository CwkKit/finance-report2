import yfinance as yf
import pandas as pd
import json
import time
from datetime import datetime
from deep_translator import GoogleTranslator

def get_market_tickers():
    print("正在抓取 S&P 500 與 NASDAQ 100 成分股名單...")
    sp500_tickers = []
    nasdaq_tickers = []
    
    try:
        tables_sp = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        sp500_tickers = [t.replace('.', '-') for t in tables_sp[0]['Symbol'].tolist()]
    except Exception as e:
        print("S&P 500 名單抓取失敗", e)

    try:
        tables_nq = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        for df in tables_nq:
            if 'Ticker' in df.columns:
                nasdaq_tickers = [t.replace('.', '-') for t in df['Ticker'].tolist()]
                break
            elif 'Symbol' in df.columns:
                nasdaq_tickers = [t.replace('.', '-') for t in df['Symbol'].tolist()]
                break
    except Exception as e:
        print("NASDAQ 名單抓取失敗", e)

    all_tickers = sorted(list(set(sp500_tickers + nasdaq_tickers)))
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
    if not all_tickers:
        all_tickers = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMZN', 'META', 'GOOGL']
        ticker_market_map = {t: 'S&P 500' for t in all_tickers}

    translator = GoogleTranslator(source='en', target='zh-TW')
    master_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 開始抓取共 {len(all_tickers)} 檔股票數據...")

    for i, ticker in enumerate(all_tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            if not price or price == 0: continue
                
            profit_margin = info.get('profitMargins', 0)
            profit = round(profit_margin * 100, 1) if profit_margin else 0.0
            current_pe = info.get('trailingPE', 0)
            
            # 中文翻譯
            english_story = info.get('longBusinessSummary', '暫無簡介')
            chinese_story = '暫無簡介'
            if english_story != '暫無簡介':
                try:
                    chinese_story = translator.translate(english_story[:1500])
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
                "fairPe": round(current_pe, 2) if current_pe and current_pe > 0 else 15.0, # 自動帶入合理 PE
                "epsStd": 0.1, # 預設標準差，後面會自動計算
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
                        # 抓取最新一季的 EPS 給主表用
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            if pd.notna(act):
                                est = row.get('EPS Estimate', 0) or 0
                                data_dict["estEps"] = round(est, 2)
                                data_dict["actEps"] = round(act, 2)
                                data_dict["surprise"] = round((row.get('Surprise(%)', 0) or 0) * 100, 2)
                                break

                        # 計算過去 8 季標準差
                        errors = []
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            est = row.get('EPS Estimate', None)
                            if pd.notna(act) and pd.notna(est):
                                errors.append(act - est)
                            
                            if pd.notna(act):
                                surp_pct = round((row.get('Surprise(%)', 0) or 0) * 100, 2)
                                data_dict["history"].append({
                                    "quarter": f"{idx.year} Q{(idx.month-1)//3 + 1}",
                                    "est": round(est, 2) if pd.notna(est) else 0,
                                    "act": round(act, 2),
                                    "surprise": surp_pct,
                                    "status": "Beat" if surp_pct > 0 else "Miss"
                                })
                        
                        # 寫入真實標準差
                        if len(errors) >= 2:
                            eps_std = round(float(pd.Series(errors).std()), 3)
                            data_dict["epsStd"] = eps_std if eps_std > 0 else 0.1

            except Exception as e_earn:
                pass

            master_data.append(data_dict)
            if (i + 1) % 50 == 0:
                print(f"已處理 {i + 1} 檔...")
            time.sleep(0.3) 
            
        except Exception as e:
            pass

    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)
        
    print(f"完成！共儲存 {len(master_data)} 檔資料。")

if __name__ == "__main__":
    fetch_stock_data()
