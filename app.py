import streamlit as st
from pykrx import stock
import pandas as pd
import time
from datetime import datetime, timedelta

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="미너비니 주식 관제탑", layout="wide")
st.title("🦅 미너비니 전략 : 실시간 관제탑")

# --- [2] 핵심 분석 로직 (함수로 분리) ---
def check_minervini_conditions(ticker):
    """종목 하나를 받아서 미너비니 조건(상승추세, VCP, 거래량)을 판별해 결과를 반환"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
        # 데이터 수집
        df = stock.get_market_ohlcv(start_date, today, ticker)
        if df.empty: return None

        current_price = df['종가'].iloc[-1]
        current_vol = df['거래량'].iloc[-1]
        
        # 이평선 및 신고가
        ma_150 = df['종가'].rolling(window=150).mean().iloc[-1]
        ma_200 = df['종가'].rolling(window=200).mean().iloc[-1]
        low_52 = df['저가'].tail(252).min()
        high_52 = df['고가'].tail(252).max()

        # [조건 1] 2단계 상승 국면
        is_stage2 = (
            current_price > ma_150 and
            current_price > ma_200 and
            ma_150 > ma_200 and
            current_price > low_52 * 1.25 and 
            current_price > high_52 * 0.75
        )

        # [조건 2] VCP 변동성 (최근 20일)
        recent_high = df['고가'].tail(20).max()
        recent_low = df['저가'].tail(20).min()
        volatility = (recent_high - recent_low) / recent_low
        pivot_point = recent_high

        # [조건 3] 거래량 폭발 (50일 평균 대비 1.5배)
        avg_vol_50 = df['거래량'].tail(50).mean()
        vol_ratio = current_vol / avg_vol_50 if avg_vol_50 > 0 else 0
        is_vol_explode = vol_ratio >= 1.5

        # 상태 판정
        status = ""
        if not is_stage2:
            status = "❌ 추세 이탈"
        elif volatility > 0.15:
            status = "⚠️ 변동성 큼"
        elif current_price >= pivot_point and is_vol_explode:
            status = "🔥 강력 매수 (돌파)"
        elif current_price >= pivot_point:
            status = "❓ 거래량 부족 (주의)"
        else:
            status = "⏳ 관찰 중 (VCP 형성)"

        return {
            "종목명": stock.get_market_ticker_name(ticker),
            "현재가": f"{current_price:,}원",
            "상태": status,
            "피벗 포인트": f"{pivot_point:,}원",
            "돌파율": f"{(current_price/pivot_point - 1)*100:.1f}%",
            "거래량 강도": f"{vol_ratio*100:.0f}%",
            "변동성": f"{volatility*100:.1f}%"
        }

    except:
        return None

# --- [3] 사이드바 메뉴 ---
menu = st.sidebar.radio("모드 선택", ["단일 종목 분석", "KOSPI 30 실시간 감시"])

# ==========================================
# [모드 1] 단일 종목 분석 (기존 기능)
# ==========================================
if menu == "단일 종목 분석":
    st.header("🔍 단일 종목 정밀 분석")
    ticker = st.text_input("종목코드 입력 (예: 000660)", "000660")
    
    if st.button("분석 실행"):
        with st.spinner("데이터 분석 중..."):
            result = check_minervini_conditions(ticker)
            if result:
                st.metric(label=result['종목명'], value=result['현재가'], delta=result['상태'])
                st.json(result)
            else:
                st.error("데이터를 불러오지 못했습니다.")

# ==========================================
# [모드 2] KOSPI 상위 30 감시 (새 기능!)
# ==========================================
elif menu == "KOSPI 30 실시간 감시":
    st.header("🚨 KOSPI 시총 상위 30위 실시간 감시")
    st.info("이 기능은 1분에 한 번씩 상위 30개 종목을 스캔하여 업데이트합니다.")

    if st.button("감시 시작 (멈추려면 '새로고침' 하세요)"):
        status_placeholder = st.empty() # 상태 메시지 표시 공간
        table_placeholder = st.empty()  # 표 표시 공간
        
        while True:
            # 1. KOSPI 시총 상위 30개 가져오기
            status_placeholder.markdown("🔄 **데이터 스캔 중... 잠시만 기다려주세요.**")
            today = datetime.now().strftime("%Y%m%d")
            
            # 시총 상위 티커 리스트
            tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(30).index
            
            results = []
            
            # 30개 종목 루프 돌면서 분석
            progress_bar = st.progress(0)
            for i, ticker in enumerate(tickers):
                res = check_minervini_conditions(ticker)
                if res:
                    results.append(res)
                progress_bar.progress((i + 1) / len(tickers))
            
            # 데이터프레임으로 변환 및 중요도 순 정렬
            monitor_df = pd.DataFrame(results)
            
            # '강력 매수'가 맨 위로 오게 정렬
            monitor_df['우선순위'] = monitor_df['상태'].apply(lambda x: 0 if '강력 매수' in x else (1 if '관찰 중' in x else 2))
            monitor_df = monitor_df.sort_values('우선순위').drop('우선순위', axis=1)

            # 화면 업데이트
            now_time = datetime.now().strftime("%H:%M:%S")
            status_placeholder.success(f"✅ 업데이트 완료: {now_time} (다음 갱신까지 60초 대기)")
            table_placeholder.dataframe(monitor_df, height=800)
            
            # 60초 대기 (네이버 서버 차단 방지)
            time.sleep(60)
            # 페이지 새로고침 (데이터 갱신 효과)
            st.rerun() 
