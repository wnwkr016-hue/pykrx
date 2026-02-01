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
st.set_page_config(page_title="주식 하락 감지기 Pro", layout="wide")
st.title("📉 주식 하락 위험 감지 대시보드 (Pro)")
st.markdown("기술적 분석 + 시장 심리 + **신용융자 잔고(빚투)** 분석 포함")

# ---------------------------------------------------------
# 사이드바
# ---------------------------------------------------------
st.sidebar.header("설정")
ticker = st.sidebar.text_input("종목코드 입력 (예: 005930)", value="005930")
days = st.sidebar.slider("분석 기간 (일)", 200, 500, 365)

end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

# ---------------------------------------------------------
# 데이터 로딩 함수들
# ---------------------------------------------------------

# 1. 주가 및 펀더멘털 데이터
@st.cache_data
def load_data(ticker, start, end):
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        fundamental = stock.get_market_fundamental_by_date(start, end, ticker)
        return df, fundamental
    except:
        return None, None

# 2. 매크로 지표 (VIX, 국채금리)
@st.cache_data
def get_macro_data():
    try:
        vix = yf.download("^VIX", period="5d", progress=False)
        treasury = yf.download("^TNX", period="5d", progress=False)
        return vix, treasury
    except:
        return None, None

# 3. [추가됨] 신용융자 잔고 (네이버 금융 크롤링)
@st.cache_data
def get_credit_balance_trend():
    try:
        # 네이버 금융 증시자금동향 URL
        url = "https://finance.naver.com/sise/sise_deposit.naver"
        # read_html은 페이지 내의 모든 테이블을 리스트로 가져옴
        tables = pd.read_html(url, encoding='cp949')
        
        # 통상적으로 두 번째 테이블에 주요 데이터가 있음 (구조 변경 가능성 있음)
        # 데이터 정제: '신용융자'가 포함된 행 찾기
        df_fund = tables[0]
        
        # 컬럼 정리 (날짜, 신용융자 잔고 등)
        # 네이버 표 구조상 데이터가 흩어져 있어서 간단히 '신용융자' 컬럼만 추출 시도
        if '신용융자' in df_fund.columns:
            # 최근 데이터 2개만 가져와서 비교
            latest = df_fund.iloc[0]['신용융자'] # 오늘(또는 최근 영업일)
            prev = df_fund.iloc[1]['신용융자']   # 전일
            
            # 콤마, 문자를 숫자로 변환 (예: "20,000" -> 20000)
            latest_val = int(str(latest).replace(',', '').replace('억', ''))
            prev_val = int(str(prev).replace(',', '').replace('억', ''))
            
            return latest_val, prev_val # 단위: 억원
        else:
            # 테이블 구조가 다를 경우 대비 (0, 2번 인덱스 등 확인 필요)
            return None, None
    except Exception as e:
        print(f"신용잔고 크롤링 실패: {e}")
        return None, None

# ---------------------------------------------------------
# 실행 및 분석
# ---------------------------------------------------------
with st.spinner('데이터를 분석 중입니다...'):
    df, fund = load_data(ticker, start_date, end_date)
    vix_df, bond_df = get_macro_data()
    credit_now, credit_prev = get_credit_balance_trend()

if df is None or df.empty:
    st.error("데이터를 가져올 수 없습니다.")
    st.stop()

# ---------------------------------------------------------
# 지표 계산
# ---------------------------------------------------------
df['MA20'] = df['종가'].rolling(window=20).mean()
df['MA50'] = df['종가'].rolling(window=50).mean()
df['Vol_Avg'] = df['거래량'].rolling(window=20).mean()

# RSI
delta = df['종가'].diff(1)
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
df['RSI'] = 100 - (100 / (1 + rs))

# 볼린저 밴드
df['BB_Mid'] = df['종가'].rolling(window=20).mean()
df['BB_Std'] = df['종가'].rolling(window=20).std()
df['BB_Upper'] = df['BB_Mid'] + (2 * df['BB_Std'])

# ---------------------------------------------------------
# 🚨 위험 신호 로직
# ---------------------------------------------------------
signals = []

# 1. 기술적 분석
if df['MA20'].iloc[-2] > df['MA50'].iloc[-2] and df['MA20'].iloc[-1] < df['MA50'].iloc[-1]:
    signals.append("🔴 [Dead Cross] 20일선 하향 돌파")
if df['거래량'].iloc[-1] > df['Vol_Avg'].iloc[-1] * 2 and df['시가'].iloc[-1] > df['종가'].iloc[-1] * 1.03:
    signals.append("🔴 [Panic Selling] 거래량 급증 + 장대음봉")
if df['RSI'].iloc[-2] >= 70 and df['RSI'].iloc[-1] < df['RSI'].iloc[-2]:
    signals.append(f"🔴 [RSI Reversal] 과매수 후 하락 전환 (RSI {df['RSI'].iloc[-2]:.1f})")

# 2. 시장 심리 (VIX, 신용잔고)
if vix_df is not None:
    cur_vix = vix_df['Close'].iloc[-1].item()
    if cur_vix > 30:
        signals.append(f"⚠️ [VIX] 공포지수 {cur_vix:.1f} (매우 높음)")

# [추가됨] 신용융자 잔고 체크
if credit_now is not None:
    # 절대 금액 기준 (예: 20조원 이상이면 과열로 간주, 시장 상황따라 다름)
    # 여기서는 전일 대비 급증 여부나 절대 수치 경고를 줍니다.
    if credit_now > 200000: # 20조원 (단위: 억원)
        signals.append(f"⚠️ [Credit Debt] 시장 신용융자 잔고가 {credit_now:,}억원으로 과열 구간입니다.")
    if credit_now > credit_prev * 1.02: # 하루만에 2% 이상 급증
        signals.append(f"⚠️ [Credit Spike] 빚투 자금이 급증했습니다 (전일대비 +{(credit_now/credit_prev - 1)*100:.2f}%)")

# 3. 매크로
if bond_df is not None:
    cur_bond = bond_df['Close'].iloc[-1].item()
    if cur_bond > 4.5:
        signals.append(f"📉 [Interest Rate] 미 10년물 금리 {cur_bond:.2f}% (고금리)")

# ---------------------------------------------------------
# UI 출력
# ---------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("현재 주가", f"{df['종가'].iloc[-1]:,}원", f"{df['등락률'].iloc[-1]}%")
col2.metric("RSI", f"{df['RSI'].iloc[-1]:.1f}")

if credit_now:
    # 전일 대비 증감 계산
    diff = credit_now - credit_prev
    col3.metric("시장 신용잔고", f"{credit_now/10000:.1f}조원", f"{diff}억")
else:
    col3.metric("시장 신용잔고", "로딩 실패")

if vix_df is not None:
    col4.metric("VIX 지수", f"{vix_df['Close'].iloc[-1].item():.2f}")

st.divider()

st.subheader("🚨 위험 감지 리포트")
if not signals:
    st.success("현재 특이한 하락 징후가 없습니다. ✅")
else:
    for sig in signals:
        st.error(sig)

# (차트 그리기 코드는 이전과 동일하므로 생략하거나 그대로 유지)
st.subheader("📊 차트 분석")
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
fig.add_trace(go.Candlestick(x=df.index, open=df['시가'], high=df['고가'], low=df['저가'], close=df['종가'], name='Price'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='MA 20'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', dash='dot'), name='BB Upper'), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=2, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=70, x1=df.index[-1], y1=70, line=dict(color="red", dash="dash"), row=2, col=1)
st.plotly_chart(fig, use_container_width=True)
