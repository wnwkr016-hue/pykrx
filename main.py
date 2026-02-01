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
st.set_page_config(page_title="주식 위험 감지기 Pro", layout="wide")
st.title("📉 주식 하락 위험 진단 AI (Pro Ver.)")
st.markdown("기술적 지표, 시장 심리, 신용 잔고를 종합 분석하여 **하락 확률**을 계산합니다.")

# ---------------------------------------------------------
# 사이드바 설정
# ---------------------------------------------------------
st.sidebar.header("🔍 분석 설정")
ticker = st.sidebar.text_input("종목코드 (예: 005930)", value="005930")
days = st.sidebar.slider("데이터 수집 기간 (일)", 200, 600, 365)

end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

# ---------------------------------------------------------
# 데이터 로딩 (캐싱 적용)
# ---------------------------------------------------------
@st.cache_data
def load_market_data(ticker, start, end):
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        fund = stock.get_market_fundamental_by_date(start, end, ticker)
        return df, fund
    except:
        return None, None

@st.cache_data
def load_macro_data():
    try:
        vix = yf.download("^VIX", period="5d", progress=False)
        bond = yf.download("^TNX", period="5d", progress=False)
        return vix, bond
    except:
        return None, None

@st.cache_data
def get_credit_balance():
    try:
        # 네이버 금융 증시자금동향 크롤링
        url = "https://finance.naver.com/sise/sise_deposit.naver"
        tables = pd.read_html(url, encoding='cp949')
        df_fund = tables[0]
        
        if '신용융자' in df_fund.columns:
            latest = int(str(df_fund.iloc[0]['신용융자']).replace(',', '').replace('억', ''))
            prev = int(str(df_fund.iloc[1]['신용융자']).replace(',', '').replace('억', ''))
            return latest, prev
        return None, None
    except:
        return None, None

# ---------------------------------------------------------
# 🧮 하락 확률 계산 엔진
# ---------------------------------------------------------
def calculate_risk_score(df, fund, vix_df, bond_df, credit_now, credit_prev):
    score = 0
    reasons = []
    
    # 1. 이동평균선 (Dead Cross) - 가중치 20점
    ma20 = df['종가'].rolling(20).mean()
    ma50 = df['종가'].rolling(50).mean()
    if ma20.iloc[-2] > ma50.iloc[-2] and ma20.iloc[-1] < ma50.iloc[-1]:
        score += 20
        reasons.append("🔴 [Dead Cross] 20일선이 50일선을 하향 돌파 (+20%)")

    # 2. 거래량 급증 + 장대음봉 - 가중치 20점
    vol_avg = df['거래량'].rolling(20).mean()
    if df['거래량'].iloc[-1] > vol_avg.iloc[-1] * 2 and df['시가'].iloc[-1] > df['종가'].iloc[-1] * 1.03:
        score += 20
        reasons.append("🔴 [Panic Selling] 거래량 2배 급증 + 장대음봉 (+20%)")

    # 3. 지지선 붕괴 (60일 신저가) - 가중치 15점
    low_60 = df['저가'].rolling(60).min().shift(1)
    if df['종가'].iloc[-1] < low_60.iloc[-1]:
        score += 15
        reasons.append("🟠 [Breakdown] 60일 지지선 붕괴 (신저가) (+15%)")

    # 4. 볼린저 밴드 저항 - 가중치 10점
    bb_mid = df['종가'].rolling(20).mean()
    bb_std = df['종가'].rolling(20).std()
    bb_upper = bb_mid + (2 * bb_std)
    if df['고가'].iloc[-1] >= bb_upper.iloc[-1] and df['종가'].iloc[-1] < df['고가'].iloc[-1]:
        score += 10
        reasons.append("🟠 [Bollinger] 밴드 상단 터치 후 하락 (+10%)")

    # 5. RSI 과매수 반전 - 가중치 10점
    delta = df['종가'].diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    if rsi.iloc[-2] >= 70 and rsi.iloc[-1] < rsi.iloc[-2]:
        score += 10
        reasons.append("🟠 [RSI Reversal] 과매수 구간에서 꺾임 (+10%)")

    # 6. VIX (공포지수) - 가중치 10점
    if vix_df is not None:
        if vix_df['Close'].iloc[-1].item() > 30:
            score += 10
            reasons.append("⚠️ [Macro] 공포지수(VIX) 30 이상 위험권 (+10%)")

    # 7. 신용잔고 과열 - 가중치 5점
    if credit_now is not None:
        if credit_now > 220000: # 22조 기준 (조정 가능)
            score += 5
            reasons.append("⚠️ [Market] 신용융자 잔고 과열 (22조원 이상) (+5%)")
        if credit_now > credit_prev * 1.01: # 1% 급증
            score += 5
            reasons.append("⚠️ [Market] 신용융자 잔고 급증세 (+5%)")

    # 8. 금리 (미국채) - 가중치 5점
    if bond_df is not None:
        if bond_df['Close'].iloc[-1].item() > 4.5:
            score += 5
            reasons.append("📉 [Macro] 고금리 환경 (미 10년물 > 4.5%) (+5%)")
            
    # 9. 실적 (적자기업) - 가중치 5점
    if fund is not None and not fund.empty:
        if fund['EPS'].iloc[-1] < 0:
            score += 5
            reasons.append("📉 [Fundamental] 최근 실적 적자 기업 (+5%)")

    return min(score, 100), reasons, df, rsi

# ---------------------------------------------------------
# 메인 로직 실행
# ---------------------------------------------------------
with st.spinner('데이터 수집 및 위험도 계산 중...'):
    df, fund = load_market_data(ticker, start_date, end_date)
    vix_df, bond_df = load_macro_data()
    credit_now, credit_prev = get_credit_balance()

if df is None or df.empty:
    st.error("데이터 로드 실패. 종목코드를 확인해주세요.")
    st.stop()

# 위험도 계산
risk_score, risk_reasons, df, rsi_series = calculate_risk_score(df, fund, vix_df, bond_df, credit_now, credit_prev)

# ---------------------------------------------------------
# 📊 UI: 게이지 차트 (속도계)
# ---------------------------------------------------------
col_main, col_info = st.columns([2, 1])

with col_main:
    # 게이지 차트 생성
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = risk_score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "하락 위험 확률(%)", 'font': {'size': 24}},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "darkblue"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 30], 'color': "lightgreen"},
                {'range': [30, 70], 'color': "orange"},
                {'range': [70, 100], 'color': "red"}],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': risk_score}}))
    
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_info:
    st.markdown("### 📋 현재 주가 정보")
    st.metric("현재가", f"{df['종가'].iloc[-1]:,}원", f"{df['등락률'].iloc[-1]}%")
    
    st.markdown("### 🌡️ 위험도 상태")
    if risk_score >= 70:
        st.error("🚨 **위험 (High Risk)**\n\n적극적인 매도 또는 관망이 권장됩니다.")
    elif risk_score >= 30:
        st.warning("⚠️ **주의 (Caution)**\n\n분할 매수 혹은 하락 전환에 주의하세요.")
    else:
        st.success("✅ **안정 (Stable)**\n\n특이한 하락 징후가 없습니다.")

st.divider()

# ---------------------------------------------------------
# 위험 요인 상세 리스트
# ---------------------------------------------------------
st.subheader("🧐 위험 감지 상세 내역")

if not risk_reasons:
    st.info("현재 감지된 하락 위험 요인이 없습니다. 시장이 안정적일 수 있습니다.")
else:
    for reason in risk_reasons:
        st.error(reason)

st.divider()

# ---------------------------------------------------------
# 하단: 상세 차트 (캔들 + 이평선 + RSI)
# ---------------------------------------------------------
st.subheader("📈 기술적 분석 차트")

fig_chart = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                          vertical_spacing=0.1, row_heights=[0.7, 0.3])

# 캔들
fig_chart.add_trace(go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], name='Price'), row=1, col=1)

# 이평선
ma20 = df['종가'].rolling(20).mean()
ma50 = df['종가'].rolling(50).mean()
fig_chart.add_trace(go.Scatter(x=df.index, y=ma20, line=dict(color='orange', width=1), name='MA 20'), row=1, col=1)
fig_chart.add_trace(go.Scatter(x=df.index, y=ma50, line=dict(color='blue', width=1), name='MA 50'), row=1, col=1)

# RSI
fig_chart.add_trace(go.Scatter(x=df.index, y=rsi_series, line=dict(color='purple', width=2), name='RSI'), row=2, col=1)
fig_chart.add_shape(type="line", x0=df.index[0], y0=70, x1=df.index[-1], y1=70, line=dict(color="red", dash="dash"), row=2, col=1)
fig_chart.add_shape(type="line", x0=df.index[0], y0=30, x1=df.index[-1], y1=30, line=dict(color="green", dash="dash"), row=2, col=1)

fig_chart.update_layout(height=600, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_chart, use_container_width=True)

# ---------------------------------------------------------
# 추가 데이터 표
# ---------------------------------------------------------
with st.expander("📊 매크로 및 수급 데이터 원본 보기"):
    col_a, col_b, col_c = st.columns(3)
    if vix_df is not None:
        col_a.metric("VIX (공포지수)", f"{vix_df['Close'].iloc[-1].item():.2f}")
    if bond_df is not None:
        col_b.metric("미 10년물 국채", f"{bond_df['Close'].iloc[-1].item():.2f}%")
    if credit_now is not None:
        col_c.metric("신용융자 잔고", f"{credit_now/10000:.1f}조원")

