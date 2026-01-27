import streamlit as st
from pykrx import stock
import pandas as pd
import numpy as np
import time
import requests
import random
from datetime import datetime, timedelta
import pytz # 한국 시간 계산용

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="미너비니 주식 관제탑", layout="wide")
st.title("🦅 미너비니 전략 : 스마트 관제탑")

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
st.sidebar.header("설정")
tg_token = st.sidebar.text_input("텔레그램 봇 토큰", type="password")
tg_id = st.sidebar.text_input("텔레그램 Chat ID")

menu = st.sidebar.radio("모드 선택", ["KOSPI 30 실시간 감시", "단일 종목 분석"])

# ==========================================
# [모드 1] KOSPI 30 실시간 감시 (최종 완성형)
# ==========================================
if menu == "KOSPI 30 실시간 감시":
    st.header("🚨 KOSPI 시총 상위 30위 실시간 감시")
    st.markdown("""
    - **운영 시간**: 09:00 ~ 16:30 (자동 감지)
    - **보안 모드**: 종목 간 1초 휴식 / 전체 갱신 3~8분 랜덤 대기
    """)

    # 한국 시간 설정
    KST = pytz.timezone('Asia/Seoul')

    if 'sent_tickers' not in st.session_state:
        st.session_state['sent_tickers'] = []

    if st.button("감시 시작 (멈추려면 '새로고침')"):
        status_placeholder = st.empty()
        table_placeholder = st.empty()
        
        while True:
            # 1. 현재 시간 확인
            now = datetime.now(KST)
            current_time_str = now.strftime("%H:%M:%S")
            
            # 장 운영 시간 설정 (09:00 ~ 16:30)
            start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=16, minute=30, second=0, microsecond=0)
            
            # === [케이스 1] 장 운영 시간인 경우 ===
            if start_time <= now <= end_time:
                status_placeholder.markdown(f"🕒 **[{current_time_str}] 장 운영 중... 데이터를 스캔합니다.**")
                
                try:
                    today = datetime.now().strftime("%Y%m%d")
                    tickers = stock.get_market_cap_by_ticker(today, market="KOSPI").head(30).index
                    
                    results = []
                    alert_messages = []

                    progress_bar = st.progress(0)
                    
                    # 30개 종목 루프
                    for i, ticker in enumerate(tickers):
                        res = check_minervini_conditions(ticker)
                        if res:
                            results.append(res)
                            
                            # 알림 조건: 강력 매수 + 아직 안 보낸 종목
                            if "강력 매수" in res['상태'] and res['종목명'] not in st.session_state['sent_tickers']:
                                msg = f"🚀 [미너비니 포착] {res['종목명']}\n현재가: {res['현재가']}\n피벗 포인트 돌파! 거래량 폭발!"
                                alert_messages.append(msg)
                                st.session_state['sent_tickers'].append(res['종목명'])

                        # 진행률 업데이트
                        progress_bar.progress((i + 1) / len(tickers))
                        
                        # ★ 종목 사이 1초 휴식 (차단 방지)
                        time.sleep(1)
                    
                    # 텔레그램 전송
                    if alert_messages and tg_token and tg_id:
                        full_msg = "\n\n".join(alert_messages)
                        send_telegram_msg(tg_token, tg_id, full_msg)

                    # 결과 화면 표시
                    monitor_df = pd.DataFrame(results)
                    if not monitor_df.empty:
                        monitor_df['우선순위'] = monitor_df['상태'].apply(lambda x: 0 if '강력 매수' in x else (1 if '관찰 중' in x else 2))
                        monitor_df = monitor_df.sort_values('우선순위').drop('우선순위', axis=1)
                        table_placeholder.dataframe(monitor_df, height=800)
                    
                    # ★ 랜덤 대기 시간 설정 (3분 ~ 8분)
                    wait_sec = random.randint(180, 480)
                    wait_min = wait_sec // 60
                    
                    status_placeholder.success(f"✅ 스캔 완료: {current_time_str} (다음 스캔까지 {wait_min}분 대기...)")
                    
                    # 대기
                    time.sleep(wait_sec)
                    st.rerun()

                except Exception as e:
                    status_placeholder.error(f"⚠️ 오류 발생: {e} (1분 후 재시도)")
                    time.sleep(60)
                    st.rerun()
            
            # === [케이스 2] 장 마감 시간인 경우 ===
            else:
                status_placeholder.warning(f"🌙 **[{current_time_str}] 현재는 장 운영 시간이 아닙니다.** (09:00에 다시 시작됩니다)")
                # 서버 자원 절약을 위해 1분 대기 후 시간 다시 확인
                time.sleep(60)
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