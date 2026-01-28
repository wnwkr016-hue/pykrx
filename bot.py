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

# --- [설정] 실전 필터링 기준 ---
MIN_PRICE = 5000           # 주가 5천원 이상
MIN_TRADING_VALUE = 2000000000 # 거래대금 20억 이상

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
# 2. RS 점수 계산 (진단 로그 기능 탑재)
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
        print(f"🧹 빈칸 제거(dropna) 후 개수: {len(df_calc)}개")
        
        # 0나누기 방지
        df_calc = df_calc[
            (df_calc['T3'] > 0) & (df_calc['T6'] > 0) & 
            (df_calc['T9'] > 0) & (df_calc['T12'] > 0)
        ]

        if len(df_calc) == 0:
            print("🚨 [원인] 과거 데이터 결측으로 인해 계산 가능한 종목이 0개입니다.")
            return {}, {}

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
            if rs_score > 99: rs_score = 99
            rs_dict[ticker] = rs_score
            change_dict[ticker] = (row['T0'] - row['T12']) / row['T12'] * 100

        print(f"✅ 최종 산출 성공: {len(rs_dict)}개 종목 RS 점수 확보")
        return rs_dict, change_dict

    except Exception as e:
        print(f"❌ RS 계산 치명적 오류: {e}")
        return {}, {}

# ---------------------------------------------------------
# 3. 개별 종목 분석 (JSON용 데이터 반환)
# ---------------------------------------------------------
def check_stock(ticker, rs_map, change_map):
    try:
        rs_score = rs_map.get(ticker, 0)
        if rs_score < 90: return None 

        korea_now = datetime.utcnow() + timedelta(hours=9)
        today = korea_now.strftime("%Y%m%d")
        start_date = (korea_now - timedelta(days=400)).strftime("%Y%m%d")
        
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if len(df) < 200: return None

        current_price = int(df['종가'].iloc[-1])
        current_vol = int(df['거래량'].iloc[-1])
        
        ma_50 = df['종가'].rolling(50).mean().iloc[-1]
        ma_150 = df['종가'].rolling(150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(200).mean().iloc[-1]
        ma_200_prev = df['종가'].rolling(200).mean().iloc[-20]
        
        low_52 = df['저가'].tail(252).min()
        high_52 = df['고가'].tail(252).max()

        cond_trend = (
            current_price > ma_150 and current_price > ma_200 and
            current_price > ma_50 and
            ma_150 > ma_200 and ma_50 > ma_150 and ma_50 > ma_200 and
            ma_200 > ma_200_prev and
            current_price > low_52 * 1.30 and current_price > high_52 * 0.75
        )
        if not cond_trend: return None

        recent_high = df['고가'].tail(20).max()
        recent_low = df['저가'].tail(20).min()
        volatility = (recent_high - recent_low) / recent_low
        avg_vol_50 = df['거래량'].tail(50).mean()
        is_vol_explode = current_vol > (avg_vol_50 * 1.5) if avg_vol_50 > 0 else False

        if volatility <= 0.15 and current_price >= recent_high and is_vol_explode:
            name = stock.get_market_ticker_name(ticker)
            year_change = change_map.get(ticker, 0)
            
            return {
                "ticker": ticker,
                "name": name,
                "price": current_price,
                "rs_score": rs_score,
                "change": round(year_change, 1),
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        return None
    except: return None

# ---------------------------------------------------------
# 4. 실행부 (보안 모드 + 진단 출력)
# ---------------------------------------------------------
if __name__ == "__main__":
    # 1. 랜덤 대기 (10초 ~ 3분)
    wait_sec = random.randint(10, 180)
    print(f"🕵️ [보안 모드] 봇이 {wait_sec}초 동안 대기 후 작동합니다...")
    time.sleep(wait_sec)

    print("\n🚀 주식 분석 봇 가동!")
    
    # RS 점수 계산 (진단 로그 출력됨)
    rs_map, change_map = pre_calculate_rs_rank()
    
    # 한국 시간 설정
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today = korea_now.strftime("%Y%m%d")
    
    # [설정] 상위 50개만 샘플링 (전체를 원하면 .head(50) 삭제)
    target_tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(50).index
    
    results = []
    print(f"\n🔎 {len(target_tickers)}개 종목 정밀 분석 시작...")

    for ticker in target_tickers:
        data = check_stock(ticker, rs_map, change_map)
        if data:
            results.append(data)
            print(f"  -> 💎 발견: {data['name']}")
        
        # 보안 딜레이
        time.sleep(random.uniform(0.5, 1.5)) 

    # [1] JSON 저장
    with open("stocks.json", "w", encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print("✅ stocks.json 저장 완료")

    # [2] 텔레그램 전송
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
        print(f"✅ 텔레그램 전송 완료 ({len(results)}건)")
    else:
        with open("stocks.json", "w", encoding='utf-8') as f:
            json.dump([], f)
        print("💤 조건 만족 종목 없음")