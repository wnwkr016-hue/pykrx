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
MIN_PRICE = 5000           
MIN_TRADING_VALUE = 2000000000 

# ---------------------------------------------------------
# 1. 텔레그램 전송 함수
# ---------------------------------------------------------
def send_telegram_msg(message):
    try:
        if not TG_TOKEN or not TG_ID:
            print("❌ 오류: GitHub Secrets 설정이 안되어 있습니다.")
            return

        token = TG_TOKEN.replace("bot", "") 
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": TG_ID, "text": message}
        
        resp = requests.get(url, params=params)
        if resp.status_code == 200:
            print("✅ 텔레그램 전송 성공!")
        else:
            print(f"❌ 전송 실패 (코드 {resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"❌ 연결 오류: {e}")

# ---------------------------------------------------------
# 2. RS 점수 계산 (에러 원천 봉쇄 버전)
# ---------------------------------------------------------
def get_market_ohlcv_safe(target_date):
    for _ in range(5):
        try:
            df_kospi = stock.get_market_ohlcv(target_date, market="KOSPI")
            df_kosdaq = stock.get_market_ohlcv(target_date, market="KOSDAQ")
            if not df_kospi.empty and not df_kosdaq.empty:
                return pd.concat([df_kospi, df_kosdaq]), target_date
        except:
            pass
        target_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    return None, None

def pre_calculate_rs_rank():
    print("📊 시장 전체 RS 점수 계산 중...")
    try:
        now = datetime.now()
        today_str = now.strftime("%Y%m%d")
        
        df_today, real_today = get_market_ohlcv_safe(today_str)
        if df_today is None: return {}, {}

        condition = (df_today['종가'] >= MIN_PRICE) & (df_today['거래대금'] >= MIN_TRADING_VALUE)
        filtered_df = df_today[condition].copy()
        valid_tickers = filtered_df.index
        
        dates = {
            'T0': real_today,
            'T3': (now - timedelta(days=90)).strftime("%Y%m%d"),
            'T6': (now - timedelta(days=180)).strftime("%Y%m%d"),
            'T9': (now - timedelta(days=270)).strftime("%Y%m%d"),
            'T12': (now - timedelta(days=365)).strftime("%Y%m%d")
        }
        
        prices = {'T0': filtered_df['종가']}
        for key in ['T3', 'T6', 'T9', 'T12']:
            df_past, _ = get_market_ohlcv_safe(dates[key])
            if df_past is not None:
                prices[key] = df_past.loc[df_past.index.intersection(valid_tickers)]['종가']
            else:
                prices[key] = pd.Series(dtype='float64')

        df_calc = pd.DataFrame(prices).dropna()
        
        # [방어 코드 1] 데이터프레임 단계에서 0 제거
        df_calc = df_calc[
            (df_calc['T3'] > 0) & 
            (df_calc['T6'] > 0) & 
            (df_calc['T9'] > 0) & 
            (df_calc['T12'] > 0)
        ]

        df_calc['R1'] = (df_calc['T0'] - df_calc['T3']) / df_calc['T3']
        df_calc['R2'] = (df_calc['T3'] - df_calc['T6']) / df_calc['T6']
        df_calc['R3'] = (df_calc['T6'] - df_calc['T9']) / df_calc['T9']
        df_calc['R4'] = (df_calc['T9'] - df_calc['T12']) / df_calc['T12']

        df_calc['Raw_Score'] = (df_calc['R1'] * 0.4) + (df_calc['R2'] * 0.2) + (df_calc['R3'] * 0.2) + (df_calc['R4'] * 0.2)
        df_calc['Rank'] = df_calc['Raw_Score'].rank(ascending=False)
        total_count = len(df_calc)
        
        rs_dict = {}
        change_dict = {}
        
        for ticker, row in df_calc.iterrows():
            rs_score = int(100 - (row['Rank'] / total_count * 100))
            if rs_score > 99: rs_score = 99
            if rs_score < 1: rs_score = 1
            rs_dict[ticker] = rs_score
            
            # [★ 여기가 문제의 구간 - 무적 방어 코드 적용]
            try:
                # 1년 전 주가가 0이거나 비어있으면 계산 안 함
                if row['T12'] == 0 or pd.isna(row['T12']):
                    change_dict[ticker] = 0
                else:
                    change_dict[ticker] = (row['T0'] - row['T12']) / row['T12'] * 100
            except:
                change_dict[ticker] = 0 # 무슨 에러가 나든 그냥 0 처리

        print(f"✅ 정예 종목 {total_count}개 RS 산출 완료")
        return rs_dict, change_dict

    except Exception as e:
        print(f"❌ RS 계산 치명적 오류: {e}")
        return {}, {}

# ---------------------------------------------------------
# 3. 개별 종목 분석
# ---------------------------------------------------------
def check_stock(ticker, rs_map, change_map):
    try:
        rs_score = rs_map.get(ticker, 0)
        if rs_score < 90: return None

        today = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if len(df) < 200: return None

        current_price = df['종가'].iloc[-1]
        current_vol = df['거래량'].iloc[-1]
        
        # 이동평균선
        ma_50 = df['종가'].rolling(50).mean().iloc[-1]
        ma_150 = df['종가'].rolling(150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(200).mean().iloc[-1]
        ma_200_prev = df['종가'].rolling(200).mean().iloc[-20]
        
        # 신고가/신저가
        low_52 = df['저가'].tail(252).min()
        high_52 = df['고가'].tail(252).max()

        # 미너비니 8원칙 (Trend Template)
        cond_trend = (
            current_price > ma_150 and
            current_price > ma_200 and
            current_price > ma_50 and
            ma_150 > ma_200 and
            ma_50 > ma_150 and
            ma_50 > ma_200 and
            ma_200 > ma_200_prev and
            current_price > low_52 * 1.30 and
            current_price > high_52 * 0.75
        )
        if not cond_trend: return None

        # 변동성 축소(VCP) 및 거래량 폭발
        recent_high = df['고가'].tail(20).max()
        recent_low = df['저가'].tail(20).min()
        volatility = (recent_high - recent_low) / recent_low
        avg_vol_50 = df['거래량'].tail(50).mean()
        
        # 거래량이 평소보다 1.5배 이상 터졌는지
        if avg_vol_50 > 0:
            is_vol_explode = current_vol > (avg_vol_50 * 1.5)
        else:
            is_vol_explode = False

        if volatility <= 0.15 and current_price >= recent_high and is_vol_explode:
            name = stock.get_market_ticker_name(ticker)
            year_change = change_map.get(ticker, 0)
            return (f"💎 [미너비니 포착] {name}\n"
                    f"💰 가격: {current_price:,}원\n"
                    f"🏆 RS 점수: {rs_score}점\n"
                    f"📈 1년 수익률: {year_change:.1f}%")
        return None
    except:
        return None

# ---------------------------------------------------------
# 4. 메인 실행
# ---------------------------------------------------------
if __name__ == "__main__":
    wait_sec = random.randint(1, 120)
    print(f"🕵️ 보안 대기: {wait_sec}초...")
    time.sleep(wait_sec)

    print("🚀 분석 시작...")
    
    # [테스트용 알림] - 잘 되면 나중에 주석 처리하세요
    # send_telegram_msg(f"🔔 [봇 실행] 분석 시작합니다 (대기: {wait_sec}초)")

    rs_map, change_map = pre_calculate_rs_rank()
    
    today = datetime.now().strftime("%Y%m%d")
    target_tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(50).index
    
    messages = []
    for ticker in target_tickers:
        msg = check_stock(ticker, rs_map, change_map)
        if msg:
            messages.append(msg)
            print(f"  -> 발견: {ticker}")
        time.sleep(random.uniform(0.5, 2.0))

    if messages:
        send_telegram_msg("\n\n".join(messages))
        print("✅ 전송 완료")
    else:
        print("💤 조건 만족 종목 없음")