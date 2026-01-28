import sys

print("--- 🚀 [1단계] 봇 실행 시작 ---")

try:
    print(f"python version: {sys.version}")
    
    print("--- ⏳ [2단계] 라이브러리 불러오기 ---")
    import pandas as pd
    print(f"✅ pandas 버전: {pd.__version__}")
    
    import requests
    print("✅ requests 임포트 성공")
    
    import pykrx
    print("✅ pykrx 임포트 성공")
    
    from pykrx import stock
    print("✅ pykrx.stock 모듈 로딩 성공")

except ImportError as e:
    print(f"❌ [치명적 오류] 라이브러리가 설치되지 않았습니다: {e}")
    print("힌트: requirements.txt 파일 안에 오타가 있거나, 설치 단계가 실패했습니다.")
    sys.exit(1)
except Exception as e:
    print(f"❌ [알 수 없는 오류] 임포트 중 에러: {e}")
    sys.exit(1)

print("--- 📡 [3단계] 네이버/KRX 통신 테스트 ---")
try:
    # 가장 쉬운 데이터 요청 (오늘 날짜 말고 종목 이름만)
    target_ticker = "005930"
    print(f"삼성전자({target_ticker}) 이름 물어보는 중...")
    
    name = stock.get_market_ticker_name(target_ticker)
    
    if name:
        print(f"🎉 [성공] 통신 정상! 종목명: {name}")
    else:
        print("⚠️ [경고] 통신은 된 것 같은데 이름이 안 나옵니다.")

except Exception as e:
    print(f"❌ [통신 오류] 네이버 서버 접속 실패: {e}")
    print("힌트: 깃허브 IP가 일시적으로 차단되었거나, pykrx 라이브러리 내부 문제입니다.")
    sys.exit(1)

print("--- ✅ [4단계] 모든 테스트 통과 ---")