# 1. 필요한 도구들을 가져옵니다.
# (처음 실행 전 터미널에 'pip install pykrx pandas numpy' 입력 필수!)
from pykrx import stock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def analyze_stock(ticker, name):
    """
    종목코드(ticker)를 넣으면 데이터를 자동으로 가져와서 분석하는 함수
    """
    print(f"--- [{name} ({ticker})] 데이터를 수집 중입니다... ---")

    # ---------------------------------------------------------
    # 1. [자동화] 오늘 날짜 기준으로 1년치 데이터 가져오기
    # ---------------------------------------------------------
    today = datetime.now().strftime("%Y%m%d") # 오늘 날짜 (예: 20231025)
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d") # 1년 전 날짜
    
    # pykrx를 이용해 네이버 금융에서 일봉 데이터를 자동으로 긁어옵니다.
    # (Open: 시가, High: 고가, Low: 저가, Close: 종가, Volume: 거래량)
    df = stock.get_market_ohlcv(start_date, today, ticker)
    
    # 데이터가 잘 왔는지 확인 (행이 비어있으면 오류)
    if df.empty:
        print("데이터를 가져오는데 실패했습니다. 종목코드를 확인해주세요.")
        return

    # 컬럼 이름을 영문으로 변경 (분석하기 편하게)
    df = df.rename(columns={'시가': 'Open', '고가': 'High', '저가': 'Low', '종가': 'Close', '거래량': 'Volume'})

    # ---------------------------------------------------------
    # 2. 미너비니 전략 분석 (이전과 동일한 로직)
    # ---------------------------------------------------------
    current_price = df['Close'].iloc[-1]
    
    # 이동평균선 계산
    ma_150 = df['Close'].rolling(window=150).mean().iloc[-1]
    ma_200 = df['Close'].rolling(window=200).mean().iloc[-1]
    
    # 52주 신고가/신저가
    low_52 = df['Low'].tail(252).min()
    high_52 = df['High'].tail(252).max()

    # [필터 1] 2단계 상승 국면인지 확인
    is_stage2 = (
        current_price > ma_150 and
        current_price > ma_200 and
        current_price > low_52 * 1.25 and 
        current_price > high_52 * 0.75
    )

    if not is_stage2:
        print(f"결과: ❌ [탈락] 아직 상승 추세(2단계)가 아닙니다.")
        return

    # [필터 2] VCP 패턴 (변동성 수축) 확인
    recent_high = df['High'].tail(20).max()
    recent_low = df['Low'].tail(20).min()
    volatility = (recent_high - recent_low) / recent_low
    
    if volatility > 0.15: 
        print(f"결과: ⚠️ [관찰 필요] 변동성이 {volatility*100:.1f}%로 아직 큽니다. (15% 미만 권장)")
        return

    # ---------------------------------------------------------
    # 3. 피벗 포인트 & 거래량 폭발 (핵심 매수 신호)
    # ---------------------------------------------------------
    pivot_point = recent_high # 최근 고점을 피벗 포인트로 설정
    
    current_vol = df['Volume'].iloc[-1]       # 오늘 거래량
    avg_vol_50 = df['Volume'].tail(50).mean() # 평소(50일) 평균 거래량
    
    is_volume_explode = current_vol > (avg_vol_50 * 1.5) # 거래량 1.5배 폭발?

    print(f"\n[분석 결과 보고서]")
    print(f"현재가: {current_price:,.0f}원")
    print(f"피벗 포인트(돌파 기준가): {pivot_point:,.0f}원")
    print(f"오늘 거래량: {current_vol:,.0f}주 (평소 대비 {current_vol/avg_vol_50*100:.0f}%)")
    
    if current_price >= pivot_point and is_volume_explode:
        print("""
        ★★ [강력 매수 신호 포착!] ★★
        1. 2단계 상승 추세 확인 완료 (OK)
        2. VCP 변동성 수축 완료 (OK)
        3. 피벗 포인트 돌파 + 거래량 폭발 발생! (기관 개입 가능성 높음)
        
        * 추천 손절가: """ + f"{int(pivot_point * 0.95):,.0f}" + "원 (-5%)")
        
    elif current_price >= pivot_point:
        print("주의: 가격은 돌파했지만 거래량이 부족합니다. (가짜 돌파 위험)")
        
    else:
        print(f"대기: 현재가({current_price})가 아직 피벗 포인트({pivot_point}) 아래입니다.")

# ==========================================
# [사용 방법] 분석하고 싶은 종목 코드만 넣으세요!
# ==========================================

# 예시 1: 삼성전자 (005930)
analyze_stock("005930", "삼성전자")

print("\n" + "="*50 + "\n")

# 예시 2: SK하이닉스 (000660)
analyze_stock("000660", "SK하이닉스")
analyze_stock("042700", "한미반도체")
