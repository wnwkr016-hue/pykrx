import streamlit as st
import pandas as pd
import numpy as np
from pykrx import stock
import yfinance as yf
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------
st.set_page_config(page_title="주식 하락 감지기", layout="wide")
st.title("📉 주식 하락 위험 감지 대시보드")
st.markdown("기술적 분석, 시장 심리, 거시 지표를 종합하여 하락 위험을 진단합니다.")

# ---------------------------------------------------------
# 사이드바 (입력창)
# ---------------------------------------------------------
st.sidebar.header("설정")
ticker = st.sidebar.text_input("종목코드 입력 (예: 005930)", value="005930")
days = st.sidebar.slider("분석 기간 (일)", 200, 500, 365)

# 날짜 계산
end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

# ---------------------------------------------------------
# 데이터 로딩 함수 (캐싱 적용으로 속도 향상)
# ---------------------------------------------------------
@st.cache_data
def load_data(ticker, start, end):
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        fundamental = stock.get_market_fundamental_by_date(start, end, ticker)
        return df, fundamental
    except Exception as e:
        return None, None

@st.cache_data
def get_market_sentiment():
    try:
        # VIX (공포지수)
        vix = yf.download("^VIX", period="5d", progress=False)
        # 미국 10년물 국채
        treasury = yf.download("^TNX", period="5d", progress=False)
        return vix, treasury
    except:
        return None, None

# 데이터 로드
with st.spinner('데이터를 분석 중입니다...'):
    df, fund = load_data(ticker, start_date, end_date)
    vix_df, bond_df = get_market_sentiment()

if df is None or df.empty:
    st.error("데이터를 가져올 수 없습니다. 종목 코드를 확인해주세요.")
    st.stop()

# ---------------------------------------------------------
# 1. 기술적 분석 지표 계산
# ---------------------------------------------------------
df['MA20'] = df['종가'].rolling(window=20).mean()
df['MA50'] = df['종가'].rolling(window=50).mean()
df['Vol_Avg'] = df['거래량'].rolling(window=20).mean()

# RSI 계산
delta = df['종가'].diff(1)
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
df['RSI'] = 100 - (100 / (1 + rs))

# 볼린저 밴드
df['BB_Mid'] = df['종가'].rolling(window=20).mean()
df['BB_Std'] = df['종가'].rolling(window=20).std()
df['BB_Upper'] = df['BB_Mid'] + (2 * df['BB_Std'])
df['BB_Lower'] = df['BB_Mid'] - (2 * df['BB_Std'])

# ---------------------------------------------------------
# 위험 신호 탐지 로직
# ---------------------------------------------------------
signals = []

# A. 데드크로스
if df['MA20'].iloc[-2] > df['MA50'].iloc[-2] and df['MA20'].iloc[-1] < df['MA50'].iloc[-1]:
    signals.append("🔴 [Dead Cross] 20일선이 50일선을 하향 돌파 (강한 하락 신호)")

# B. 거래량 실린 장대음봉
if df['거래량'].iloc[-1] > df['Vol_Avg'].iloc[-1] * 2 and df['시가'].iloc[-1] > df['종가'].iloc[-1] * 1.03:
    signals.append("🔴 [Panic Selling] 거래량 급증 + 장대음봉 발생")

# C. RSI 과매수 후 하락
if df['RSI'].iloc[-2] >= 70 and df['RSI'].iloc[-1] < df['RSI'].iloc[-2]:
    signals.append(f"🔴 [RSI Reversal] 과매수({df['RSI'].iloc[-2]:.1f}) 구간 진입 후 꺾임")

# D. 볼린저 밴드 상단 이탈
if df['고가'].iloc[-1] >= df['BB_Upper'].iloc[-1] and df['종가'].iloc[-1] < df['고가'].iloc[-1]:
    signals.append("🔴 [Bollinger] 밴드 상단 터치 후 저항")

# E. VIX 공포지수 (시장 심리)
if vix_df is not None and not vix_df.empty:
    cur_vix = vix_df['Close'].iloc[-1].item()
    if cur_vix > 30:
        signals.append(f"⚠️ [Macro] 공포지수(VIX)가 {cur_vix:.1f}로 매우 위험 수준")

# F. 금리 (거시 경제)
if bond_df is not None and not bond_df.empty:
    cur_bond = bond_df['Close'].iloc[-1].item()
    if cur_bond > 4.5:
        signals.append(f"📉 [Macro] 미국 10년물 국채 금리가 {cur_bond:.2f}%로 높음")

# ---------------------------------------------------------
# 화면 출력 (UI)
# ---------------------------------------------------------

# 상단 요약
col1, col2, col3 = st.columns(3)
col1.metric("현재 주가", f"{df['종가'].iloc[-1]:,}원", f"{df['등락률'].iloc[-1]}%")
col2.metric("RSI (14)", f"{df['RSI'].iloc[-1]:.1f}")
if vix_df is not None:
    col3.metric("VIX 지수", f"{vix_df['Close'].iloc[-1].item():.2f}")

st.divider()

# 신호 출력 구역
st.subheader("🚨 위험 감지 리포트")

if not signals:
    st.success("현재 특이한 하락 징후가 발견되지 않았습니다. ✅")
else:
    for sig in signals:
        st.error(sig)

st.divider()

# 차트 그리기 (Plotly)
st.subheader("📊 기술적 분석 차트")

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                    vertical_spacing=0.1, subplot_titles=('주가 & 이동평균선 & 볼린저밴드', 'RSI & 거래량'), 
                    row_width=[0.3, 0.7])

# 캔들차트
fig.add_trace(go.Candlestick(x=df.index,
                open=df['시가'], high=df['고가'],
                low=df['저가'], close=df['종가'], name='Price'), row=1, col=1)

# 이동평균선
fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='MA 20'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='blue', width=1), name='MA 50'), row=1, col=1)

# 볼린저밴드
fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB Upper'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), name='BB Lower'), row=1, col=1)

# RSI
fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name='RSI'), row=2, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=70, x1=df.index[-1], y1=70, line=dict(color="red", width=1, dash="dash"), row=2, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=30, x1=df.index[-1], y1=30, line=dict(color="green", width=1, dash="dash"), row=2, col=1)

fig.update_layout(xaxis_rangeslider_visible=False, height=800)
st.plotly_chart(fig, use_container_width=True)

# 펀더멘털 정보
if fund is not None and not fund.empty:
    st.subheader("🏢 펀더멘털 체크")
    last_eps = fund['EPS'].iloc[-1]
    last_per = fund['PER'].iloc[-1]
    
    f_col1, f_col2 = st.columns(2)
    f_col1.info(f"EPS (주당순이익): {last_eps}원")
    f_col2.info(f"PER (주가수익비율): {last_per}배")
    
    if last_eps < 0:
        st.warning("⚠️ 주의: 최근 실적이 적자 상태입니다.")

