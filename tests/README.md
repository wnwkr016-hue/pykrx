# PyKrx VCR 통합 테스트 가이드

## 개요

PyKrx 프로젝트는 `vcrpy`를 사용하여 HTTP 요청/응답을 녹화하고 재생합니다. 이를 통해:
- 실제 네트워크 없이 빠른 테스트 실행
- CI 환경에서 안정적인 테스트
- API 응답 변경 사항 추적

## 디렉터리 구조

```
tests/
├── cassettes/          # VCR cassette 파일들 (YAML 형식)
│   ├── bond/
│   ├── etf/
│   ├── stock/
│   └── ...
├── integration/        # 통합 테스트 (cassette 사용)
│   ├── test_bond_api.py
│   ├── test_etf_api.py
│   ├── test_market_api.py
│   └── ...
├── live/              # Live 서버 테스트 (실제 네트워크 호출)
└── conftest.py        # pytest & VCR 설정
```

## 테스트 작성 방법

### Integration 테스트 (Cassette 사용)

```python
import pytest
from pykrx import stock

class TestStockOhlcv:
    @pytest.mark.cassette('stock/ohlcv_005930_20210104_20210108.yaml')
    def test_get_ohlcv(self, use_cassette):
        df = stock.get_market_ohlcv_by_date("20210104", "20210108", "005930")
        assert len(df) == 5
        assert '시가' in df.columns
```

### Live 테스트 (실제 서버 호출)

```python
class TestServerInterface:
    def test_krx_market_endpoint(self):
        # use_cassette fixture 없이 직접 호출
        df = stock.get_market_ohlcv_by_ticker("20210104")
        assert not df.empty
```

## 실행 명령어

```bash
# Integration 테스트 (cassette 사용, 빠름)
pytest tests/integration/ -v

# Live 테스트 (실제 서버, 느림)
pytest tests/live/ -v

# 모든 테스트
pytest -v

# 특정 테스트만
pytest tests/integration/test_bond_api.py -v
pytest tests/integration/test_etf_api.py::TestEtfTickerList -v
```

## Cassette 관리

### 새 Cassette 녹화
1. 테스트 코드에 `@pytest.mark.cassette('path/to/cassette.yaml')` 추가
2. `use_cassette` fixture를 테스트 메서드 파라미터로 추가
3. 테스트 실행 → cassette 자동 생성

### Cassette 재녹화
```bash
# 특정 cassette 삭제 후 재실행
rm tests/cassettes/bond/yields_by_ticker_20220204.yaml
pytest tests/integration/test_bond_api.py::TestBondOtcTreasuryYiledByTicker::test_business_day -v

# 또는 모든 cassette 재생성
rm -rf tests/cassettes/*
pytest tests/integration/ -v
```

### Cassette Git 관리
- ✅ **Cassette 파일은 Git에 커밋해야 합니다**
- CI에서 네트워크 없이 테스트 실행
- API 응답 변경 추적 가능
- 크기가 큰 cassette는 `.gitattributes`로 LFS 고려

## CI/CD 통합

GitHub Actions는 integration 테스트만 실행합니다:

```yaml
# .github/workflows/test.yml
- name: Run integration tests
  run: pytest tests/integration/ -v
```

Live 테스트는 CI에서 제외됩니다 (실제 서버 부하 방지).

## VCR 설정 (`conftest.py`)

```python
@pytest.fixture(scope='module')
def vcr_config():
    return {
        'cassette_library_dir': 'tests/cassettes',
        'record_mode': 'once',  # 한 번만 녹화
        'match_on': ['uri', 'method', 'body'],  # 요청 매칭 기준
    }
```

### Record Modes
- `once`: cassette 없으면 녹화, 있으면 재생 (기본)
- `new_episodes`: 새 요청만 녹화, 기존은 재생
- `none`: 녹화 안 함, cassette만 사용
- `all`: 항상 재녹화

## 트러블슈팅

### Cassette가 재생되지 않음
- 요청 매칭 기준 확인 (`match_on` 설정)
- URL 파라미터 순서가 다를 수 있음
- Body 내용이 달라졌는지 확인

### 테스트가 느림
- Integration 테스트에서 `use_cassette` fixture 누락 확인
- Cassette 파일이 제대로 생성되었는지 확인

### CI 실패
- Cassette 파일이 Git에 커밋되었는지 확인
- `pytest tests/integration/` 경로 확인
