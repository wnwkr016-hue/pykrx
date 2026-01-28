import os
import requests
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time
import random
import json

# --- [설정] 깃허브 비밀금고 ---
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_ID = os.environ.get('TG_ID')

# --- [설정] 필터링 기준 ---
# 디버깅을 위해 조건을 잠시 낮췄습니다 (5천원 -> 1천원, 20억 -> 1억)
MIN_PRICE = 1000           
MIN_TRADING_VALUE = 100000000 

def send_telegram_msg(message):
    try:
        if not TG_TOKEN or not TG_ID: return
        token = TG_TOKEN.replace("bot", "") 
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": TG_ID, "text": message}
        requests.get(url, params=params)
    except: pass

def get_market_ohlcv_safe(target_date):
    """데이터를 가져오고, 몇 개를 가져왔는지 로그를 찍습니다."""
    for i in range(5):
        try:
            print(f"   [시도 {i+1}] {target_date} 데이터 요청 중...", end="")
            df_kospi = stock.get_market_ohlcv(target_date, market="KOSPI")
            df_kosdaq = stock.get_market_ohlcv(target_date, market="KOSDAQ")
            
            if not df_kospi.empty and not df_kosdaq.empty:
                full_df = pd.concat([df_kospi, df_kosdaq])
                print(f" 성공! ({len(full_df)}개 종목)")
                return full_df, target_date
            else:
                print(" 실패 (빈 데이터)")
        except Exception as e:
            print(f" 에러: {e}")
        
        # 실패하면 하루 전으로
        target_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    
    print("❌ 최종 실패: 5일치 데이터를 다 뒤져도 없습니다.")
    return None, None

def pre_calculate_rs_rank():
    print("\n📊 [진단 모드] RS 점수 계산 시작")
    
    # 1. 한국 시간 설정
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today_str = korea_now.strftime("%Y%m%d")
    print(f"📅 기준 날짜(한국시간): {today_str}")

    # 2. 오늘 데이터 가져오기
    df_today, real_today = get_market_ohlcv_safe(today_str)
    
    if df_today is None:
        print("🚨 [원인 발견] 오늘 데이터를 아예 못 가져왔습니다.")
        return {}, {}

    # 3. 데이터 샘플 확인 (단위 확인용)
    print("\n🔎 [데이터 샘플 확인]")
    print(df_today[['종가', '거래대금']].head(3))
    print("------------------------------------------------")

    # 4. 필터링 적용
    print(f"🧐 필터링 전: {len(df_today)}개")
    condition = (df_today['종가'] >= MIN_PRICE) & (df_today['거래대금'] >= MIN_TRADING_VALUE)
    filtered_df = df_today[condition].copy()
    print(f"🧐 필터링 후: {len(filtered_df)}개 (조건: {MIN_PRICE}원↑, {MIN_TRADING_VALUE}원↑)")

    if len(filtered_df) == 0:
        print("🚨 [원인 발견] 필터링 조건이 너무 높아서 다 탈락했습니다.")
        return {}, {}

    valid_tickers = filtered_df.index
    
    # 5. 과거 데이터 수집
    print("\n⏳ 과거 데이터 수집 시작...")
    real_date_obj = datetime.strptime(real_today, "%Y%m%d")
    dates = {
        'T0': real_today,
        'T3': (real_date_obj - timedelta(days=90)).strftime("%Y%m%d"),
        'T6': (real_date_obj - timedelta(days=180)).strftime("%Y%m%d"),
        'T9': (real_date_obj - timedelta(days=270)).strftime("%Y%m%d"),
        'T12': (real_date_obj - timedelta(days=365)).strftime("%Y%m%d")
    }
    
    prices = {'T0': filtered_df['종가']}
    
    # 각 시점별 데이터 수집 상황 체크
    for key in ['T3', 'T6', 'T9', 'T12']:
        print(f"   👉 {key} ({dates[key]}) 가져오는 중...", end=" ")
        df_past, _ = get_market_ohlcv_safe(dates[key])
        
        if df_past is not None:
            prices[key] = df_past.loc[df_past.index.intersection(valid_tickers)]['종가']
            print(f"확보된 종목 수: {len(prices[key])}개")
        else:
            print("🚨 실패! (이 날짜 데이터가 없어서 전체 0개가 될 예정)")
            prices[key] = pd.Series(dtype='float64')

    # 6. 최종 계산
    df_calc = pd.DataFrame(prices)
    print(f"\n🧩 합치기 전 데이터 개수: {len(df_calc)}개")
    
    df_calc = df_calc.dropna()
    print(f"🧹 빈칸 제거(dropna) 후 개수: {len(df_calc)}개 (여기가 0이면 과거 데이터 중 하나가 펑크난 것임)")

    if len(df_calc) == 0:
        print("🚨 [원인 발견] 과거 데이터 중 하나가 비어있어서 교집합이 0개가 되었습니다.")
        return {}, {}

    # (이하 계산 로직은 동일)
    df_calc['R1'] = (df_calc['T0'] - df_calc['T3']) / df_calc['T3']
    df_calc['R2'] = (df_calc['T3'] - df_calc['T6']) / df_calc['T6']
    df_calc['R3'] = (df_calc['T6'] - df_calc['T9']) / df_calc['T9']
    df_calc['R4'] = (df_calc['T9'] - df_calc['T12']) / df_calc['T12']

    df_calc['Raw_Score'] = (df_calc['R1'] * 0.4) + (df_calc['R2'] * 0.2) + (df_calc['R3'] * 0.2) + (df_calc['R4'] * 0.2)
    df_calc['Rank'] = df_calc['Raw_Score'].rank(ascending=False)
    
    rs_dict = {}
    change_dict = {}
    for ticker, row in df_calc.iterrows():
        rs_score = int(100 - (row['Rank'] / len(df_calc) * 100))
        rs_dict[ticker] = rs_score
        try:
            change_dict[ticker] = (row['T0'] - row['T12']) / row['T12'] * 100
        except:
            change_dict[ticker] = 0

    print(f"✅ 최종 산출 성공: {len(rs_dict)}개")
    return rs_dict, change_dict

# ---------------------------------------------------------
# 실행부
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 디버깅 봇 시작...")
    rs_map, change_map = pre_calculate_rs_rank()
    
    if len(rs_map) > 0:
        # 파일 저장 (앱 테스트용)
        with open("stocks.json", "w", encoding='utf-8') as f:
            json.dump([], f) 
        print("✅ (테스트) 빈 파일 생성 완료")
    else:
        print("❌ 결과가 0개여서 종료합니다.")