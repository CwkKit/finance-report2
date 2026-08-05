import yfinance as yf
import pandas as pd
import json
import time
from datetime import datetime
from deep_translator import GoogleTranslator

# 1. 每次自動從維基百科獲取「最新」的成分股名單
def get_dynamic_tickers():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在從維基百科即時抓取最新成分股名單 (包含最新加入/剔除)...")
    sp500_tickers = []
    nasdaq_tickers = []
    
    # 抓取 S&P 500 最新名單
    try:
        sp500_df = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
        # YF 要求的格式是 BRK-B，而非 BRK.B
        sp500_tickers = [str(ticker).replace('.', '-') for ticker in sp500_df['Symbol'].tolist()]
        print(f"✅ 成功獲取 {len(sp500_tickers)} 檔 S&P 500 股票")
    except Exception as e:
        print(f"❌ S&P 500 名單獲取失敗: {e}")

    # 抓取 NASDAQ 100 最新名單
    try:
        nq_tables = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')
        for df in nq_tables:
            if 'Ticker' in df.columns:
                nasdaq_tickers = [str(ticker).replace('.', '-') for ticker in df['Ticker'].tolist()]
                break
            elif 'Symbol' in df.columns:
                nasdaq_tickers = [str(ticker).replace('.', '-') for ticker in df['Symbol'].tolist()]
                break
        print(f"✅ 成功獲取 {len(nasdaq_tickers)} 檔 NASDAQ 100 股票")
    except Exception as e:
        print(f"❌ NASDAQ 名單獲取失敗: {e}")

    # 合併並去重 (有些公司同時屬於 SPY 和 NQ)
    all_tickers = sorted(list(set(sp500_tickers + nasdaq_tickers)))
    
    # 幫每支股票打上指數標籤
    ticker_market_map = {}
    for t in all_tickers:
        if t in nasdaq_tickers and t in sp500_tickers:
            ticker_market_map[t] = 'BOTH'
        elif t in nasdaq_tickers:
            ticker_market_map[t] = 'NASDAQ'
        else:
            ticker_market_map[t] = 'S&P 500'
            
    print(f"🔍 總計去重後，本次共需處理 {len(all_tickers)} 檔股票。")
    return all_tickers, ticker_market_map

def fetch_stock_data():
    all_tickers, ticker_market_map = get_dynamic_tickers()
    
    # 防呆機制：如果維基百科掛了，提供緊急備用清單
    if not all_tickers:
        print("⚠️ 無法獲取動態名單，使用備用清單...")
        all_tickers = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMZN', 'META', 'GOOGL', 'BRK-B', 'JPM']
        ticker_market_map = {t: 'S&P 500' for t in all_tickers}

    translator = GoogleTranslator(source='en', target='zh-TW')
    master_data = []
    
    # 迴圈開始抓取每一檔
    for i, ticker in enumerate(all_tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 基本防呆：如果抓不到價格，代表這檔可能有問題或下市，跳過
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            if not price or price == 0:
                continue
                
            profit_margin = info.get('profitMargins', 0)
            profit = round(profit_margin * 100, 1) if profit_margin else 0.0
            current_pe = info.get('trailingPE', 0)
            
            # 安全的翻譯機制：就算翻譯失敗，也保留英文，絕不漏掉這家公司
            english_story = info.get('longBusinessSummary', '暫無簡介')
            chinese_story = '暫無簡介'
            if english_story != '暫無簡介':
                try:
                    chinese_story = translator.translate(english_story[:1000]) # 縮減字數避免超時
                except:
                    chinese_story = english_story # 翻譯失敗就用英文

            # 建立資料主體
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
                "fairPe": round(current_pe, 2) if current_pe and current_pe > 0 else 15.0, # 合理 P/E
                "epsStd": 0.1, # 預設標準差
                "history": []
            }

            # 抓取財報日與歷史紀錄
            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    # 1. 未來預估財報 (Futu 風格)
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

                    # 2. 過去 8 季財報
                    past_earnings = earnings[earnings.index <= pd.Timestamp.now(tz='UTC')].sort_index(ascending=False).head(8)
                    if not past_earnings.empty:
                        # 幫主表抓取最新一季的真實 EPS
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            if pd.notna(act):
                                est = row.get('EPS Estimate', 0) or 0
                                data_dict["estEps"] = round(est, 2)
                                data_dict["actEps"] = round(act, 2)
                                data_dict["surprise"] = round((row.get('Surprise(%)', 0) or 0) * 100, 2)
                                break

                        # 自動計算 PEAD 所需的標準差
                        errors = []
                        for idx, row in past_earnings.iterrows():
                            act = row.get('Reported EPS', None)
                            est = row.get('EPS Estimate', None)
                            
                            # 收集預測誤差值
                            if pd.notna(act) and pd.notna(est):
                                errors.append(act - est)
                            
                            # 建立歷史財報表
                            if pd.notna(act):
                                surp_pct = round((row.get('Surprise(%)', 0) or 0) * 100, 2)
                                data_dict["history"].append({
                                    "quarter": f"{idx.year} Q{(idx.month-1)//3 + 1}",
                                    "est": round(est, 2) if pd.notna(est) else 0,
                                    "act": round(act, 2),
                                    "surprise": surp_pct,
                                    "status": "Beat" if surp_pct > 0 else "Miss"
                                })
                        
                        # 寫入自動算好的真實標準差 (Sigma)
                        if len(errors) >= 2:
                            eps_std = round(float(pd.Series(errors).std()), 3)
                            data_dict["epsStd"] = eps_std if eps_std > 0 else 0.1

            except Exception as e_earn:
                pass # 若無財報資料，不影響主資料儲存

            master_data.append(data_dict)
            
            # 進度回報與防封鎖延遲
            if (i + 1) % 50 == 0:
                print(f"📊 已經成功處理 {i + 1} 檔股票...")
            time.sleep(0.3) # 必須保留！防止 Yahoo 鎖 IP
            
        except Exception as e:
            print(f"❌ 處理 {ticker} 時發生未預期錯誤，已跳過。錯誤原因: {e}")

    # 輸出最終的 JSON
    with open("sp500_data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=4)
        
    print(f"🎉 執行完成！共完美儲存 {len(master_data)} 檔美股資料至 JSON。")

if __name__ == "__main__":
    fetch_stock_data()
