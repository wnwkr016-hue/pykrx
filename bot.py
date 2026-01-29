import os
import requests
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time
import random

# --- [설정] 깃허브 비밀금고 ---
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_ID = os.environ.get('TG_ID')

# ---------------------------------------------------------
# 1. 텔레그램 전송
# ---------------------------------------------------------
def send_telegram_msg(message):
    try:
        if not TG_TOKEN or not TG_ID: return
        token = TG_TOKEN.replace("bot", "") 
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": TG_ID, "text": message}
        requests.get(url, params=params)
    except: pass

# ---------------------------------------------------------
# 2. RS 점수 계산 (전체 시장 기준)
# ---------------------------------------------------------
def pre_calculate_rs_rank():
    print("📊 전체 시장 RS 점수 분석 중...")
    try:
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        start_date = (korea_now - timedelta(days=370)).strftime("%Y%m%d")

        # 코스피, 코스닥 모두 가져와서 통합 랭킹 산정
        df_kospi = stock.get_market_price_change_by_ticker(start_date, today, market="KOSPI")
        df_kosdaq = stock.get_market_price_change_by_ticker(start_date, today, market="KOSDAQ")
        
        df_total = pd.concat([df_kospi, df_kosdaq])
        df_total['Rank'] = df_total['등락률'].rank(pct=True)
        
        rs_dict = {}
        for ticker, row in df_total.iterrows():
            rs_dict[ticker] = int(row['Rank'] * 100)
        return rs_dict
    except: return {}

# ---------------------------------------------------------
# 3. [핵심] 미너비니 추세 + VCP 패턴 감지
# ---------------------------------------------------------
def get_stock_status(ticker, rs_map):
    try:
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        start_date = (korea_now - timedelta(days=400)).strftime("%Y%m%d")
        
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if len(df) < 200: return None

        name = stock.get_market_ticker_name(ticker)
        curr_price = int(df['종가'].iloc[-1])
        rs_score = rs_map.get(ticker, 0)
        
        # --- 1단계: 추세 (Trend Template) ---
        ma_50 = df['종가'].rolling(50).mean().iloc[-1]
        ma_150 = df['종가'].rolling(150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(200).mean().iloc[-1]
        ma_200_prev = df['종가'].rolling(200).mean().iloc[-25] 
        high_52 = df['고가'].tail(252).max()
        low_52 = df['저가'].tail(252).min()
        
        cond_trend = (
            curr_price > ma_150 and curr_price > ma_200 and
            ma_150 > ma_200 and
            ma_200 > ma_200_prev and 
            curr_price > ma_50 and
            curr_price >= (low_52 * 1.30) and 
            curr_price >= (high_52 * 0.75) and 
            rs_score >= 70 
        )

        # --- 2단계: VCP 패턴 수학적 감지 ---
        
        # (1) 변동성 축소 확인
        recent_10 = df.tail(10)
        max_price_10 = recent_10['고가'].max()
        min_price_10 = recent_10['저가'].min()
        volatility = (max_price_10 - min_price_10) / min_price_10
        is_tight = volatility <= 0.12 

        # (2) 거래량 말라죽음 확인
        vol_5_avg = df['거래량'].tail(5).mean()
        vol_20_avg = df['거래량'].tail(20).mean()
        is_vol_dry = vol_5_avg < vol_20_avg
        
        # (3) 피벗 포인트 (최근 20일 고점)
        pivot_price = int(df['고가'].tail(20).max()) 
        is_near_pivot = curr_price >= (pivot_price * 0.97) 

        # --- 상태 판정 ---
        status_text = ""
        icon = ""
        
        if cond_trend:
            if is_tight and is_near_pivot:
                if is_vol_dry:
                    status_text = "💎 매수임박 (VCP완성)"
                    icon = "🔴" 
                else:
                    status_text = "매수준비 (돌파직전)"
                    icon = "🟠" 
            else:
                status_text = "관심 (추세좋음)"
                icon = "🟡" 
        else:
            status_text = "관망"
            icon = "⚪" 

        return {
            "name": name,
            "rs": rs_score,
            "status": status_text,
            "icon": icon,
            "pivot_price": pivot_price
        }
    except: return None

# ---------------------------------------------------------
# 4. 실행부
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 [KOSPI & KOSDAQ Top 60] 미너비니 VCP 탐지 시작...")
    
    rs_map = pre_calculate_rs_rank()
    
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today = korea_now.strftime("%Y%m%d")
    
    # [수정] 코스피 30개 + 코스닥 30개 가져오기
    kospi_30 = stock.get_market_cap_by_ticker(today, market="KOSPI").head(30).index
    kosdaq_30 = stock.get_market_cap_by_ticker(today, market="KOSDAQ").head(30).index
    
    # 두 리스트 합치기 (총 60개)
    target_tickers = list(kospi_30) + list(kosdaq_30)
    
    report_list = []
    print(f"🔎 총 {len(target_tickers)}개 대장주 분석 중...")
    
    for i, ticker in enumerate(target_tickers):
        info = get_stock_status(ticker, rs_map)
        if info:
            print(f"[{i+1}] {info['name']}: {info['status']}")
            report_list.append(info)
        time.sleep(0.1) # 속도 유지를 위해 0.1초 대기

    if report_list:
        # 제목 변경: KOSPI & KOSDAQ
        msg_lines = ["📊 [KOSPI & KOSDAQ Top 60] VCP 탐지기\n"]
        
        for item in report_list:
            if "매수" in item['status']:
                line = (f"{item['icon']} {item['name']} **[{item['status']}]**\n"
                        f"   └ 🎯 돌파기준가: {item['pivot_price']:,}원\n"
                        f"   └ RS {item['rs']}점")
            else:
                line = f"{item['icon']} {item['name']} ({item['status']})"
            msg_lines.append(line)
            
        full_msg = "\n".join(msg_lines)
        
        # 내용이 길어지면 나눠서 전송
        if len(full_msg) > 4000:
            send_telegram_msg(full_msg[:4000])
            send_telegram_msg(full_msg[4000:])
        else:
            send_telegram_msg(full_msg)
        print("✅ 리포트 전송 완료")
    else:
        print("❌ 실패")
