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

# --- [설정] 필터링 기준 ---
MIN_PRICE = 1000               # 1천원 이상 (테스트용)
MIN_TRADING_VALUE = 1000000000 # 10억 이상

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
# 2. RS 점수 계산 (꼼수 버전: 이미 계산된 등락률 가져오기)
# ---------------------------------------------------------
def pre_calculate_rs_rank():
    print("📊 시장 전체 RS 점수 산출 중 (API 활용)...")
    try:
        # 한국 시간
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        
        # 1년 전 날짜 (넉넉하게 370일 전)
        start_date = (korea_now - timedelta(days=370)).strftime("%Y%m%d")

        # [핵심] 우리가 계산 안 함. KRX한테 "1년치 수익률 다 줘" 라고 명령함.
        # 이 함수는 정지된 종목이나 0원인 종목을 알아서 처리해 줌.
        df_kospi = stock.get_market_price_change_by_ticker(start_date, today, market="KOSPI")
        df_kosdaq = stock.get_market_price_change_by_ticker(start_date, today, market="KOSDAQ")
        
        # 데이터 합치기
        df_total = pd.concat([df_kospi, df_kosdaq])
        
        # 필터링 (거래정지 종목 등은 거래량이 0이라서 여기서 걸러짐)
        condition = (df_total['종가'] >= MIN_PRICE) & (df_total['거래대금'] >= MIN_TRADING_VALUE)
        df_clean = df_total[condition].copy()

        # [RS 점수 만들기] 
        # '등락률' 컬럼이 이미 1년 수익률입니다. 이걸로 순위를 매깁니다.
        # (Minervini 정석은 3,6,9개월 가중치지만, 1년 단순 등락률로도 90% 비슷합니다)
        df_clean['Rank'] = df_clean['등락률'].rank(pct=True) # 백분위(0.0 ~ 1.0)로 바로 변환
        
        rs_dict = {}
        change_dict = {}
        
        for ticker, row in df_clean.iterrows():
            rs_score = int(row['Rank'] * 100) # 0.95 -> 95점
            rs_dict[ticker] = rs_score
            change_dict[ticker] = row['등락률']

        print(f"✅ RS 산출 완료: {len(rs_dict)}개 종목")
        return rs_dict, change_dict

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return {}, {}

# ---------------------------------------------------------
# 3. 개별 종목 분석
# ---------------------------------------------------------
def check_stock(ticker, rs_map, change_map):
    try:
        rs_score = rs_map.get(ticker, 0)
        if rs_score < 90: return None 

        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        start_date = (korea_now - timedelta(days=400)).strftime("%Y%m%d")
        
        # 차트 데이터 가져오기
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if len(df) < 120: return None # 상장한지 얼마 안 된 애들 패스

        current_price = int(df['종가'].iloc[-1])
        
        # 이동평균선
        ma_50 = df['종가'].rolling(50).mean().iloc[-1]
        ma_150 = df['종가'].rolling(150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(200).mean().iloc[-1]
        
        # 52주 신고가/신저가
        high_52 = df['고가'].tail(252).max()
        low_52 = df['저가'].tail(252).min()

        # 추세 조건 (간소화)
        cond_trend = (
            current_price > ma_150 and 
            current_price > ma_200 and
            ma_150 > ma_200 and
            current_price > low_52 * 1.30 and 
            current_price > high_52 * 0.75
        )
        
        if cond_trend:
            name = stock.get_market_ticker_name(ticker)
            year_change = change_map.get(ticker, 0)
            return {
                "ticker": ticker,
                "name": name,
                "price": current_price,
                "rs_score": rs_score,
                "change": round(year_change, 1)
            }
        return None
    except: return None

# ---------------------------------------------------------
# 4. 실행부
# ---------------------------------------------------------
if __name__ == "__main__":
    wait_sec = random.randint(10, 60)
    print(f"🕵️ 보안 대기 {wait_sec}초...")
    time.sleep(wait_sec)

    print("\n🚀 봇 실행 (API 모드)")
    rs_map, change_map = pre_calculate_rs_rank()
    
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today = korea_now.strftime("%Y%m%d")
    
    # KOSPI 상위 50개만 테스트
    target_tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(50).index
    
    results = []
    for ticker in target_tickers:
        data = check_stock(ticker, rs_map, change_map)
        if data:
            results.append(data)
            print(f"  -> 💎 발견: {data['name']}")
        time.sleep(0.2)

    if results:
        msg_list = []
        for d in results:
            m = (f"💎 {d['name']} ({d['ticker']})\n"
                 f"💰 {d['price']:,}원 | 🏆 RS {d['rs_score']}점\n"
                 f"📈 1년 수익률: {d['change']}%\n"
                 f"🔥 미너비니 포착")
            msg_list.append(m)
        
        full_msg = "\n\n".join(msg_list)
        send_telegram_msg(full_msg)
        print("✅ 전송 완료")
    else:
        print("💤 조건 만족 종목 없음")