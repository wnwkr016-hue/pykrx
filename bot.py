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
        if not TG_TOKEN or not TG_ID:
            print("❌ Secrets 설정 누락")
            return
        token = TG_TOKEN.replace("bot", "") 
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": TG_ID, "text": message}
        requests.get(url, params=params)
    except: pass

# ---------------------------------------------------------
# 2. RS 점수 계산 (API 활용 - 고속 모드)
# ---------------------------------------------------------
def pre_calculate_rs_rank():
    print("📊 RS 점수 계산 중...")
    try:
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        start_date = (korea_now - timedelta(days=370)).strftime("%Y%m%d")

        df_kospi = stock.get_market_price_change_by_ticker(start_date, today, market="KOSPI")
        df_kosdaq = stock.get_market_price_change_by_ticker(start_date, today, market="KOSDAQ")
        
        df_total = pd.concat([df_kospi, df_kosdaq])
        df_total['Rank'] = df_total['등락률'].rank(pct=True)
        
        rs_dict = {}
        for ticker, row in df_total.iterrows():
            rs_dict[ticker] = int(row['Rank'] * 100)
        return rs_dict
    except:
        return {}

# ---------------------------------------------------------
# 3. 개별 종목 상태 판독 (매수/대기/관망)
# ---------------------------------------------------------
def get_stock_status(ticker, rs_map):
    try:
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        start_date = (korea_now - timedelta(days=400)).strftime("%Y%m%d")
        
        # 차트 데이터 (최소 120일)
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if len(df) < 120: return None

        name = stock.get_market_ticker_name(ticker)
        curr_price = int(df['종가'].iloc[-1])
        rs_score = rs_map.get(ticker, 0)
        
        # 이평선
        ma_50 = df['종가'].rolling(50).mean().iloc[-1]
        ma_150 = df['종가'].rolling(150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(200).mean().iloc[-1]
        
        # 52주 신고가
        high_52 = df['고가'].tail(252).max()
        
        # --- [상태 판독 로직] ---
        is_perfect = (curr_price > ma_50) and (ma_50 > ma_150) and (ma_150 > ma_200)
        is_uptrend = curr_price > ma_200
        is_near_high = curr_price >= (high_52 * 0.75)

        status_text = ""
        icon = ""
        
        if is_perfect and rs_score >= 70 and is_near_high:
            status_text = "매수" # (강력추세)
            icon = "🔴"
        elif is_uptrend:
            status_text = "매수대기" # (조정/약세)
            icon = "🟡"
        else:
            status_text = "관망" # (하락추세)
            icon = "⚪"

        return {
            "name": name,
            "rs": rs_score,
            "status": status_text, # 여기에 '매수', '관망' 등이 들어감
            "icon": icon
        }
    except:
        return None

# ---------------------------------------------------------
# 4. 실행부
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 코스피 상위 30종목 분석 시작...")
    
    rs_map = pre_calculate_rs_rank()
    
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today = korea_now.strftime("%Y%m%d")
    
    # 코스피 상위 30개
    top_30_tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(30).index
    
    report_list = []
    
    for i, ticker in enumerate(top_30_tickers):
        info = get_stock_status(ticker, rs_map)
        if info:
            print(f"[{i+1}] {info['name']} -> {info['status']}")
            report_list.append(info)
        time.sleep(0.1)

    # 텔레그램 전송 (포맷 변경됨!)
    if report_list:
        msg_lines = ["📊 [KOSPI Top 30] 현황판\n"]
        
        for item in report_list:
            # ▼▼▼ 여기가 수정된 부분입니다 ▼▼▼
            # 예시: 🔴 삼성전자 [매수] (RS: 80)
            line = f"{item['icon']} {item['name']} [{item['status']}] (RS:{item['rs']})"
            msg_lines.append(line)
            
        full_msg = "\n".join(msg_lines)
        
        if len(full_msg) > 4000:
            send_telegram_msg(full_msg[:4000])
            send_telegram_msg(full_msg[4000:])
        else:
            send_telegram_msg(full_msg)
        print("✅ 텔레그램 전송 완료")
    else:
        print("❌ 결과 없음")