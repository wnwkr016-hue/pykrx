import os
import requests
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time
import random

# --- [설정] 깃허브 비밀금고에서 가져오기 ---
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_ID = os.environ.get('TG_ID')

# --- [설정] 잡주 필터링 기준 ---
MIN_PRICE = 5000           # 주가 5,000원 이상
MIN_TRADING_VALUE = 2000000000 # 일 거래대금 20억 이상

# ---------------------------------------------------------
# 1. 텔레그램 전송 함수
# ---------------------------------------------------------
def send_telegram_msg(message):
    try:
        # 토큰이나 ID가 없으면 아예 시도도 하지 않음
        if not TG_TOKEN or not TG_ID:
            print("❌ 오류: TG_TOKEN 또는 TG_ID가 설정되지 않았습니다.")
            return

        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        params = {"chat_id": TG_ID, "text": message}
        
        # 전송 시도
        resp = requests.get(url, params=params)
        
        # 결과 확인 (status_code가 200이면 성공, 아니면 실패)
        if resp.status_code == 200:
            print("✅ 텔레그램 전송 성공!")
        else:
            # ★ 여기가 중요합니다. 왜 실패했는지 이유를 알려줍니다.
            print(f"❌ 텔레그램 전송 실패 (코드 {resp.status_code}): {resp.text}")
            
    except Exception as e:
        print(f"❌ 연결 오류 발생: {e}")
# ---------------------------------------------------------
# 2. RS 점수 계산 (잡주 필터링 + IBD 가중치 적용)
# ---------------------------------------------------------
# ---------------------------------------------------------
# [수정됨] 2. RS 점수 계산 (0으로 나누기 오류 해결 버전)
# ---------------------------------------------------------
def get_market_ohlcv_safe(target_date):
    """특정 날짜의 데이터 가져오기 (휴일 처리)"""
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
    print("📊 전체 시장 RS 점수 계산 중... (약 10~15초 소요)")
    try:
        now = datetime.now()
        today_str = now.strftime("%Y%m%d")
        
        # 1. 오늘 데이터로 잡주 필터링
        df_today, real_today = get_market_ohlcv_safe(today_str)
        if df_today is None: return {}, {}

        # 주가 5천원 이상 & 거래대금 20억 이상만 남기기
        condition = (df_today['종가'] >= MIN_PRICE) & (df_today['거래대금'] >= MIN_TRADING_VALUE)
        filtered_df = df_today[condition].copy()
        valid_tickers = filtered_df.index
        
        # 2. 과거 데이터 수집
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
                # 필터링된 종목만 교집합으로 남김
                prices[key] = df_past.loc[df_past.index.intersection(valid_tickers)]['종가']
            else:
                prices[key] = pd.Series(dtype='float64')

        # 3. 수익률 계산 (★여기가 수정되었습니다★)
        df_calc = pd.DataFrame(prices).dropna()
        
        # [ZeroDivisionError 방지] 주가가 0인 데이터 제거 (나눗셈 에러 방지)
        df_calc = df_calc[
            (df_calc['T0'] > 0) & 
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
        
        # 4. 순위 매기기
        df_calc['Rank'] = df_calc['Raw_Score'].rank(ascending=False)
        total_count = len(df_calc)
        
        rs_dict = {}
        change_dict = {}
        for ticker, row in df_calc.iterrows():
            rs_score = int(100 - (row['Rank'] / total_count * 100))
            if rs_score > 99: rs_score = 99
            if rs_score < 1: rs_score = 1
            rs_dict[ticker] = rs_score
            change_dict[ticker] = (row['T0'] - row['T12']) / row['T12'] * 100

        print(f"✅ 정예 종목 {total_count}개 RS 산출 완료")
        return rs_dict, change_dict

    except Exception as e:
        print(f"❌ RS 계산 오류: {e}")
        return {}, {}
# ---------------------------------------------------------
# 3. 개별 종목 정밀 분석 (미너비니 8대 조건)
# ---------------------------------------------------------
def check_stock(ticker, rs_map, change_map):
    try:
        # [조건 8] RS 점수 90점 이상 확인
        rs_score = rs_map.get(ticker, 0)
        if rs_score < 90: return None

        # 데이터 가져오기 (400일치)
        today = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if len(df) < 200: return None

        # 지표 계산
        current_price = df['종가'].iloc[-1]
        current_vol = df['거래량'].iloc[-1]
        ma_50 = df['종가'].rolling(50).mean().iloc[-1]
        ma_150 = df['종가'].rolling(150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(200).mean().iloc[-1]
        ma_200_prev = df['종가'].rolling(200).mean().iloc[-20] # 1달 전 200일선
        low_52 = df['저가'].tail(252).min()
        high_52 = df['고가'].tail(252).max()

        # [미너비니 Trend Template 완벽 구현]
        cond_trend = (
            current_price > ma_150 and
            current_price > ma_200 and
            current_price > ma_50 and      # 조건 5
            ma_150 > ma_200 and            # 조건 2
            ma_50 > ma_150 and             # 조건 4 (정배열)
            ma_50 > ma_200 and             # 조건 4
            ma_200 > ma_200_prev and       # 조건 3 (200일선 상승)
            current_price > low_52 * 1.30 and # 조건 6
            current_price > high_52 * 0.75    # 조건 7
        )
        if not cond_trend: return None

        # [VCP 패턴 & 거래량 폭발]
        recent_high = df['고가'].tail(20).max()
        recent_low = df['저가'].tail(20).min()
        volatility = (recent_high - recent_low) / recent_low
        avg_vol_50 = df['거래량'].tail(50).mean()
        is_vol_explode = current_vol > (avg_vol_50 * 1.5)

        # 최종 통과
        if volatility <= 0.15 and current_price >= recent_high and is_vol_explode:
            name = stock.get_market_ticker_name(ticker)
            year_change = change_map.get(ticker, 0)
            return (f"💎 [미너비니 포착] {name}\n"
                    f"💰 가격: {current_price:,}원\n"
                    f"🏆 RS 점수: {rs_score}점\n"
                    f"📈 1년 수익률: {year_change:.1f}%\n"
                    f"🔥 특징: 정배열 + 신고가 돌파 + 거래량 폭발")
        return None

    except:
        return None

# ---------------------------------------------------------
# 4. 메인 실행 (랜덤 대기 포함)
# ---------------------------------------------------------
if __name__ == "__main__":
    # [보안] 시작 전 1초~2분 랜덤 대기
    wait_sec = random.randint(1, 120)
    print(f"🕵️ 보안 대기: {wait_sec}초...")
    time.sleep(wait_sec)

    print("🚀 분석 시작...")
    rs_map, change_map = pre_calculate_rs_rank()
    
    # 감시 대상: 코스피 시총 상위 50개
    today = datetime.now().strftime("%Y%m%d")
    target_tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(50).index
    
    messages = []
    for ticker in target_tickers:
        msg = check_stock(ticker, rs_map, change_map)
        if msg:
            messages.append(msg)
            print(f"  -> 발견: {ticker}")
        
        # [보안] 종목 간 0.5~2초 랜덤 휴식
        time.sleep(random.uniform(0.5, 2.0))

    if messages:
        full_msg = "\n\n".join(messages)
        send_telegram_msg(full_msg)
        print("✅ 전송 완료")
    else:
        print("💤 조건 만족 종목 없음")