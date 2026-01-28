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

# --- [설정] 실전 필터링 기준 ---
MIN_PRICE = 5000           # 5천원 이상
MIN_TRADING_VALUE = 2000000000 # 20억 이상

# ---------------------------------------------------------
# 1. 텔레그램 전송 함수
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
# 2. RS 점수 계산 (진단 로그 기능 포함)
# ---------------------------------------------------------
def get_market_ohlcv_safe(target_date):
    """데이터를 가져오고, 성공/실패 여부를 상세하게 로그로 남김"""
    for i in range(5):
        try:
            print(f"   [시도 {i+1}] {target_date} 데이터 요청...", end=" ")
            df_kospi = stock.get_market_ohlcv(target_date, market="KOSPI")
            df_kosdaq = stock.get_market_ohlcv(target_date, market="KOSDAQ")
            
            if not df_kospi.empty and not df_kosdaq.empty:
                full_df = pd.concat([df_kospi, df_kosdaq])
                print(f"✅ 성공 ({len(full_df)}개)")
                return full_df, target_date
            else:
                print("⚠️ 실패 (빈 데이터)")
        except: 
            print("⚠️ 에러 발생")
            pass
        
        target_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    
    print("❌ 최종 실패: 5일치 데이터를 다 뒤져도 없습니다.")
    return None, None

def pre_calculate_rs_rank():
    print("\n📊 [진단 모드] RS 점수 산출 시작...")
    try:
        # [핵심] 한국 시간(KST) 강제 변환
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today_str = korea_now.strftime("%Y%m%d")
        print(f"📅 기준 날짜(한국시간): {today_str}")
        
        # 1. 오늘 데이터 가져오기
        df_today, real_today = get_market_ohlcv_safe(today_str)
        if df_today is None: return {}, {}

        # 2. 필터링 로그 출력
        print(f"🧐 필터링 전: {len(df_today)}개")
        condition = (df_today['종가'] >= MIN_PRICE) & (df_today['거래대금'] >= MIN_TRADING_VALUE)
        filtered_df = df_today[condition].copy()
        print(f"🧐 필터링 후: {len(filtered_df)}개 (조건: {MIN_PRICE}원↑, 20억↑)")
        
        if len(filtered_df) == 0:
            print("🚨 [원인] 조건이 너무 까다로워 남은 종목이 없습니다.")
            return {}, {}

        valid_tickers = filtered_df.index
        
        # 3. 과거 날짜 계산
        real_date_obj = datetime.strptime(real_today, "%Y%m%d")
        dates = {
            'T0': real_today,
            'T3': (real_date_obj - timedelta(days=90)).strftime("%Y%m%d"),
            'T6': (real_date_obj - timedelta(days=180)).strftime("%Y%m%d"),
            'T9': (real_date_obj - timedelta(days=270)).strftime("%Y%m%d"),
            'T12': (real_date_obj - timedelta(days=365)).strftime("%Y%m%d")
        }
        
        # 4. 과거 데이터 수집 (상세 로그)
        print("\n⏳ 과거 데이터 수집 중...")
        prices = {'T0': filtered_df['종가']}
        for key in ['T3', 'T6', 'T9', 'T12']:
            print(f"   👉 {key} 시점:", end=" ")
            df_past, _ = get_market_ohlcv_safe(dates[key])
            if df_past is not None:
                prices[key] = df_past.loc[df_past.index.intersection(valid_tickers)]['종가']
            else:
                print(f"🚨 {key} 데이터가 없어 0개 처리됩니다.")
                prices[key] = pd.Series(dtype='float64')

        # 5. 수익률 계산
        df_calc = pd.DataFrame(prices)
        print(f"\n🧩 합치기 전 개수: {len(df_calc)}개")
        df_calc = df_calc.dropna() # 하나라도 비면 탈락
        print(f"🧹 빈칸 제거(dropna) 후 개수: {