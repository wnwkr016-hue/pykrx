import streamlit as st
from pykrx import stock
import pandas as pd
import time
import requests # 텔레그램 전송용
from datetime import datetime, timedelta

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="미너비니 주식 관제탑", layout="wide")
st.title("🦅 미너비니 전략 : 실시간 관제탑 (텔레그램 알림)")

# --- [2] 텔레그램 전송 함수 ---
def send_telegram_msg(token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": chat_id, "text": message}
        requests.get(url, params=params)
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

# --- [3] 핵심 분석 로직 ---
def check_minervini_conditions(ticker):
    try:
        today = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        
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
        if not is_stage2: status = "❌ 추세 이탈"
        elif volatility > 0.15: status = "⚠️ 변동성 큼"
        elif current_price >= pivot_point and is_vol_explode: status = "🔥 강력 매수"
        elif current_price >= pivot_point: status = "❓ 거래량 부족"
        else: status = "⏳ 관찰 중"

        return {
            "종목명": stock.get_market_ticker_name(ticker),
            "현재가": f"{current_price:,}원",
            "상태": status,
            "피벗 포인트": f"{pivot_point:,}원",
            "돌파율": f"{(current_price/pivot_point - 1)*100:.1f}%",
            "거래량 강도": f"{vol_ratio*100:.0f}%"
        }
    except:
        return None

# --- [4] 사이드바 설정 ---
st.sidebar.header("텔레그램 설정")
tg_token = st.sidebar.text_input("텔레그램 봇 토큰", type="password")
tg_id = st.sidebar.text_input("텔레그램 Chat ID")

st.sidebar.markdown("---")
menu = st.sidebar.radio("모드 선택", ["KOSPI 30 실시간 감시", "단일 종목 분석"])

# ==========================================
# [모드 1] KOSPI 30 실시간 감시 (텔레그램 기능 추가)
# ==========================================
if menu == "KOSPI 30 실시간 감시":
    st.header("🚨 KOSPI 시총 상위 30위 실시간 감시 (30초 갱신)")
    
    # 이미 알림을 보낸 종목을 기억하기 위한 리스트 (중복 알림 방지)
    if 'sent_tickers' not in st.session_state:
        st.session_state['sent_tickers'] = []

    if st.button("감시 시작 (멈추려면 '새로고침')"):
        status_placeholder = st.empty()
        table_placeholder = st.empty()
        
        while True:
            status_placeholder.markdown("🔄 **데이터 스캔 중... (약 10~20초 소요)**")
            today = datetime.now().strftime("%Y%m%d")
            tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(30).index
            
            results = []
            alert_messages = [] # 알림 보낼 메시지 모음

            progress_bar = st.progress(0)
            for i, ticker in enumerate(tickers):
                res = check_minervini_conditions(ticker)
                if res:
                    results.append(res)
                    
                    # [알림 로직] 강력 매수 신호이고, 아직 알림을 안 보냈다면?
                    if "강력 매수" in res['상태'] and res['종목명'] not in st.session_state['sent_tickers']:
                        msg = f"🚀 [미너비니 포착] {res['종목명']}\n현재가: {res['현재가']}\n피벗 포인트 돌파! 거래량 폭발!"
                        alert_messages.append(msg)
                        st.session_state['sent_tickers'].append(res['종목명']) # 보낸 목록에 추가

                progress_bar.progress((i + 1) / len(tickers))
            
            # 텔레그램 메시지 전송
            if alert_messages and tg_token and tg_id:
                full_msg = "\n\n".join(alert_messages)
                send_telegram_msg(tg_token, tg_id, full_msg)
                st.toast(f"텔레그램 알림 전송 완료! ({len(alert_messages)}건)")

            # 화면 업데이트
            monitor_df = pd.DataFrame(results)
            if not monitor_df.empty:
                monitor_df['우선순위'] = monitor_df['상태'].apply(lambda x: 0 if '강력 매수' in x else (1 if '관찰 중' in x else 2))
                monitor_df = monitor_df.sort_values('우선순위').drop('우선순위', axis=1)
                
                now_time = datetime.now().strftime("%H:%M:%S")
                status_placeholder.success(f"✅ 업데이트: {now_time} (30초 후 재검색)")
                table_placeholder.dataframe(monitor_df, height=800)
            
            # 30초 대기
            time.sleep(30)
            st.rerun()

# ==========================================
# [모드 2] 단일 종목 분석 (기존 유지)
# ==========================================
elif menu == "단일 종목 분석":
    st.header("🔍 단일 종목 정밀 분석")
    ticker = st.text_input("종목코드 (예: 000660)", "000660")
    if st.button("분석 실행"):
        res = check_minervini_conditions(ticker)
        if res:
            st.metric(label=res['종목명'], value=res['현재가'], delta=res['상태'])
            st.json(res)