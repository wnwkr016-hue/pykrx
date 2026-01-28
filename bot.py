import os
import requests
import json
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time
import random

# --- [설정] 깃허브 비밀금고 ---
TG_TOKEN = os.environ.get('TG_TOKEN')
TG_ID = os.environ.get('TG_ID')

# --- [설정] 필터링 기준 ---
MIN_PRICE = 5000           # 5천원 이상
MIN_TRADING_VALUE = 2000000000 # 20억 이상

# ---------------------------------------------------------
# 1. 텔레그램 전송 함수 (에러 방지 & 디버깅)
# ---------------------------------------------------------
def send_telegram_msg(message):
    try:
        if not TG_TOKEN or not TG_ID:
            print("❌ 오류: GitHub Secrets 설정이 안되어 있습니다.")
            return

        # 'bot' 글자 중복 방지
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
# 2. RS 점수 계산 (한국 시간 적용 + 안전장치)
# ---------------------------------------------------------
def get_market_ohlcv_safe(target_date):
    """최근 영업일을 찾을 때까지 최대 5일 뒤로 가면서 검색"""
    for i in range(5):
        try:
            print(f"   🔎 데이터 검색 중... {target_date} (시도 {i+1})")
            df_kospi = stock.get_market_ohlcv(target_date, market="KOSPI")
            df_kosdaq = stock.get_market_ohlcv(target_date, market="KOSDAQ")
            
            if not df_kospi.empty and not df_kosdaq.empty:
                print(f"   ✅ 데이터 확보 완료! ({target_date})")
                return pd.concat([df_kospi, df_kosdaq]), target_date
        except Exception as e:
            pass
        
        # 데이터가 없으면 하루 전으로 이동
        target_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    return None, None

def pre_calculate_rs_rank():
    print("📊 시장 전체 RS 점수 계산 시작...")
    try:
        # [핵심] 깃허브 서버(UTC) + 9시간 = 한국 시간(KST)
        korea_now = datetime.utcnow() + timedelta(hours=9)
        today_str = korea_now.strftime("%Y%m%d")
        print(f"📅 한국 기준 날짜: {today_str}")
        
        # 1. 오늘(최근) 데이터 가져오기
        df_today, real_today = get_market_ohlcv_safe(today_str)
        if df_today is None: 
            print("❌ 데이터를 가져올 수 없습니다.")
            return {}, {}

        condition = (df_today['종가'] >= MIN_PRICE) & (df_today['거래대금'] >= MIN_TRADING_VALUE)
        filtered_df = df_today[condition].copy()
        valid_tickers = filtered_df.index
        
        print(f"   -> 1차 필터링 통과 종목: {len(valid_tickers)}개")

        # 2. 과거 데이터 수집
        real_date_obj = datetime.strptime(real_today, "%Y%m%d")
        dates = {
            'T0': real_today,
            'T3': (real_date_obj - timedelta(days=90)).strftime("%Y%m%d"),
            'T6': (real_date_obj - timedelta(days=180)).strftime("%Y%m%d"),
            'T9': (real_date_obj - timedelta(days=270)).strftime("%Y%m%d"),
            'T12': (real_date_obj - timedelta(days=365)).strftime("%Y%m%d")
        }
        
        prices = {'T0': filtered_df['종가']}
        for key in ['T3', 'T6', 'T9', 'T12']:
            df_past, _ = get_market_ohlcv_safe(dates[key])
            if df_past is not None:
                prices[key] = df_past.loc[df_past.index.intersection(valid_tickers)]['종가']
            else:
                prices[key] = pd.Series(dtype='float64')

        # 3. 0으로 나누기 방지 및 계산
        df_calc = pd.DataFrame(prices).dropna()
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
            
            try:
                change_dict[ticker] = (row['T0'] - row['T12']) / row['T12'] * 100
            except:
                change_dict[ticker] = 0

        print(f"✅ 정예 종목 {total_count}개 RS 산출 완료")
        return rs_dict, change_dict

    except Exception as e:
        print(f"❌ RS 계산 중 오류 발생: {e}")
        return {}, {}

# ---------------------------------------------------------
# 3. 개별 종목 분석 (앱용 JSON 데이터 반환)
# ---------------------------------------------------------
def check_stock(ticker, rs_map, change_map):
    try:
        rs_score = rs_map.get(ticker, 0)
        if rs_score < 90: return None # RS 90점 미만 탈락

        today = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
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
        
        if avg_vol_50 > 0:
            is_vol_explode = current_vol > (avg_vol_50 * 1.5)
        else:
            is_vol_explode = False

        if volatility <= 0.15 and current_price >= recent_high and is_vol_explode:
            name = stock.get_market_ticker_name(ticker)
            year_change = change_map.get(ticker, 0)
            
            # [JSON용 데이터 딕셔너리 반환]
            return {
                "ticker": ticker,
                "name": name,
                "price": current_price,
                "rs_score": rs_score,
                "change": round(year_change, 1),
                "date": datetime.now().strftime("%Y-%m-%d")
            }
        return None
    except:
        return None

# ---------------------------------------------------------
# 4. 메인 실행 (파일 저장 + 텔레그램 전송)
# ---------------------------------------------------------
if __name__ == "__main__":
    wait_sec = random.randint(1, 120)
    print(f"🕵️ 보안 대기: {wait_sec}초...")
    time.sleep(wait_sec)

    print("🚀 분석 시작...")
    rs_map, change_map = pre_calculate_rs_rank()
    
    # 한국 시간 기준 날짜 다시 계산
    korea_now = datetime.utcnow() + timedelta(hours=9)
    today_str = korea_now.strftime("%Y%m%d")
    
    # 50개만 샘플로 분석 (전체로 하려면 head(50) 제거)
    target_tickers = stock.get_market_cap_by_ticker(today_str, market="KOSPI").head(50).index
    
    results = [] 
    
    for ticker in target_tickers:
        data = check_stock(ticker, rs_map, change_map)
        if data:
            results.append(data)
            print(f"  -> 발견: {data['name']}")
        time.sleep(random.uniform(0.5, 2.0))

    # [1] 앱용 데이터 파일(JSON) 저장
    with open("stocks.json", "w", encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print("✅ stocks.json 파일 생성 완료")

    # [2] 텔레그램 전송
    if results:
        msg_list = []
        for d in results:
            m = (f"💎 {d['name']} ({d['ticker']})\n"
                 f"💰 {d['price']:,}원 | 🏆 RS {d['rs_score']}점\n"
                 f"📈 1년 수익률: {d['change']}%\n"
                 f"🔥 미너비니 조건 만족")
            msg_list.append(m)
        
        full_msg = "\n\n".join(msg_list)
        send_telegram_msg(full_msg)
    else:
        # 데이터가 없어도 빈 파일은 만들어둠
        with open("stocks.json", "w", encoding='utf-8') as f:
            json.dump([], f)
        print("💤 조건 만족 종목 없음")