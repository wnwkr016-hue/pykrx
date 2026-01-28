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
        if not TG_TOKEN or not TG_ID: return
        token = TG_TOKEN.replace("bot", "") 
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": TG_ID, "text": message}
        requests.get(url, params=params)
    except: pass

# ---------------------------------------------------------
# 2. RS 점수 계산 (검색 범위 14일로 대폭 증가)
# ---------------------------------------------------------
def get_market_ohlcv_safe(target_date):
    """
    [강화된 버전] 
    최대 14일(2주) 전까지 뒤져서라도 영업일 데이터를 찾아냅니다.
    (추석, 설날 등 긴 연휴 방어용)
    """
    for i in range(14): # 5일 -> 14일로 증가
        try:
            # 로그가 너무 많이 뜨면 지저분하니, 첫 시도와 성공 시에만 출력
            if i == 0:
                print(f"   🔎 {target_date} 데이터 찾는 중...", end=" ")
            
            df_kospi = stock.get_market_ohlcv(target_date, market="KOSPI")
            df_kosdaq = stock.get_market_ohlcv(target_date, market="KOSDAQ")
            
            if not df_kospi.empty and not df_kosdaq.empty:
                full_df = pd.concat([df_kospi, df_kosdaq])
                print(f"✅ 성공! (날짜: {target_date}, {len(full_df)}개)")
                return full_df, target_date
            
        except: pass
        
        # 하루 전으로 이동
        target_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    
    print(f"\n❌ [실패] 14일치를 뒤져도 데이터가 없습니다. ({target_date} 부근)")
    return None, None

def pre_calculate_rs_rank():
    print("\n📊 [진단 모드] RS 점수 산출 시작...")
    try:
        # 한국 시간 설정
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today_str = korea_now.strftime("%Y%m%d")
        
        # 1. 오늘 데이터
        print(f"👉 기준일(T0):", end="")
        df_today, real_today = get_market_ohlcv_safe(today_str)
        if df_today is None: return {}, {}

        # 2. 필터링
        condition = (df_today['종가'] >= MIN_PRICE) & (df_today['거래대금'] >= MIN_TRADING_VALUE)
        filtered_df = df_today[condition].copy()
        print(f"   🧐 필터링 통과 종목: {len(filtered_df)}개")
        
        if len(filtered_df) == 0:
            print("🚨 조건 만족 종목이 0개입니다. (장 마감 전이거나 휴일일 수 있음)")
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
        
        # 4. 과거 데이터 수집 (어디서 비는지 확인)
        prices = {'T0': filtered_df['종가']}
        for key in ['T3', 'T6', 'T9', 'T12']:
            print(f"👉 {key} 시점 ({dates[key]}):", end="")
            df_past, _ = get_market_ohlcv_safe(dates[key])
            
            if df_past is not None:
                prices[key] = df_past.loc[df_past.index.intersection(valid_tickers)]['종가']
            else:
                print(f"🚨 [치명적 오류] {key} 데이터를 못 구해서 전체 계산이 불가능합니다.")
                return {}, {} # 여기서 멈춤

        # 5. 수익률 계산
        df_calc = pd.DataFrame(prices).dropna()
        
        # 0나누기 방지
        df_calc = df_calc[
            (df_calc['T3'] > 0) & (df_calc['T6'] > 0) & 
            (df_calc['T9'] > 0) & (df_calc['T12'] > 0)
        ]

        if len(df_calc) == 0:
            print("🚨 [원인] 데이터는 가져왔으나, 과거 주가 중 0원이 포함되어 계산 불가.")
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

        print(f"✅ 최종 RS 산출 성공: {len(rs_dict)}개 종목")
        return rs_dict, change_dict

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
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
                "change": round(year_change, 1)
            }
        return None
    except: return None

# ---------------------------------------------------------
# 4. 실행부
# ---------------------------------------------------------
if __name__ == "__main__":
    wait_sec = random.randint(10, 180)
    print(f"🕵️ [보안 모드] 봇이 {wait_sec}초 대기합니다...")
    time.sleep(wait_sec)

    print("\n🚀 주식 분석 시작!")
    rs_map, change_map = pre_calculate_rs_rank()
    
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today = korea_now.strftime("%Y%m%d")
    
    target_tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(50).index
    
    results = []
    print(f"\n🔎 {len(target_tickers)}개 종목 분석 중...")

    for ticker in target_tickers:
        data = check_stock(ticker, rs_map, change_map)
        if data:
            results.append(data)
            print(f"  -> 💎 발견: {data['name']}")
        time.sleep(random.uniform(0.5, 1.5)) 

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
        print("💤 조건 만족 종목 없음")