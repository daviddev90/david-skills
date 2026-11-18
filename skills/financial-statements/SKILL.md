---
name: financial-statements
description: 한국 DART와 미국 SEC EDGAR에서 기업 공시, 재무제표와 주석을 찾아 분석한다. 회사 별칭으로 요청한 공시 목록, 실적 비교, 재무비율, 부문별 매출, 수주, 지분, 이사회, 자본 변동과 해당 회사 주가 조회에 사용한다. OpenDART API 키 등록과 변경에도 사용한다.
---

# 기업 공시와 재무제표

## 첫 사용

스킬을 읽으면 공시 검색 전에 아래 명령부터 AI가 실행한다.

`SKILL_DIR`를 지금 읽은 SKILL.md가 설치된 폴더 절대 경로로 설정한다. 기본 위치는 Codex에서 `"$HOME/.codex/skills/financial-statements"`, Claude Code에서 `"$HOME/.claude/skills/financial-statements"`다. 현재 프로젝트 기준 상대 경로를 쓰지 않는다. 아래 `python3`는 Windows에서 사용 가능한 Python 3 명령인 `py -3` 또는 `python`으로 바꾼다.

- 같은 컴퓨터: `python3 "$SKILL_DIR/scripts/dart_key.py" first-use`를 곧바로 실행한다. 설정이 필요하면 페이지 링크가 즉시 반환된다. `DART_SETUP_URL`을 받으면 같은 첫 답변에서 아래 선택 기준을 먼저 설명하고 Markdown 설정 링크를 전달한다. 저장하거나 공개 조회를 선택한 뒤 ‘계속’이라고 입력하도록 안내한 후 턴을 마친다. 다음 턴에서 `first-use`로 저장된 선택을 확인하고 원래 요청을 수행한다.
- 원격 기기나 클라우드: `python3 "$SKILL_DIR/scripts/dart_key.py" status`로 확인한다. 사용자에게 loopback 링크를 보내지 않는다.

첫 설정 링크 앞에서 API 키 없이도 공개 DART에서 같은 공시와 주석을 읽으며, 보고서 몇 건이나 우발부채 같은 주석 분석에는 공개 조회로 충분하다고 안내한다. 여러 회사와 기간에 걸쳐 매출이나 영업이익을 모을 때는 API에서 항목별 수치를 받아 AI가 필요한 항목만 읽어 AI 사용량이 줄어들 수 있다고 설명한다. 주석 분석에서는 두 경로 모두 같은 원문 주석을 AI가 읽는다고 설명한다.

DART 조회에는 `DART_KEY_READY`이면 API를, `DART_KEY_PUBLIC`이면 공개 뷰어를 쓴다. 로컬 설정이 끝나면 해당 결과에 따라 원래 요청을 계속한다. `DART_SETUP_UNAVAILABLE`을 받거나 원격 환경에서 키를 사용할 수 없으면 공개 DART로 진행한다. 키나 공개 조회 선택이 저장돼 있으면 설정을 반복하지 않는다. 공개 조회 선택이 저장돼 있어도 사용자가 키 등록이나 변경을 원하면 표현에 관계없이 요청을 이해해 `python3 "$SKILL_DIR/scripts/dart_key.py" setup`을 실행하고, 반환된 링크를 전달해 등록 요청을 마친다. 사용자에게 터미널 작업이나 채팅으로 키 전달을 요청하지 않는다.

API는 `python3 "$SKILL_DIR/scripts/dart_key.py" fetch company.json corp_code=...`처럼 호출한다. 이 명령으로 환경변수, OS 보안 저장소와 기존 `with-secret`에서 키를 확인하고 공식 DART 응답을 표준 출력으로 받는다. JSON은 해석하고 ZIP은 파일로 저장해 읽는다. 키를 인수, URL 출력이나 오류 추적에 노출하지 않는다. 외부에서 설정한 키를 보존한다.

## 회사 확인

AI가 별칭, 줄임말, 옛 이름, 영문명과 문맥으로 회사를 해석하고 공식 자료로 확인한다. 정확한 문자열 일치나 유사도 점수로 회사를 결정하지 않는다. 후보가 여럿이면 사업 설명으로 좁히고, 회사 선택에 사용자 판단이 필요할 때만 확인한다.

한국 회사는 기본적으로 KOSPI와 KOSDAQ 상장사에서 찾는다. [KRX KIND](https://kind.krx.co.kr/)와 DART 회사 정보로 법인명, 시장, 종목코드와 고유번호를 확인한다. KIND에서 `/corpgeneral/corpList.do?method=download&marketType=stockMkt`로 KOSPI 목록을 받고, 같은 경로에서 `marketType=kosdaqMkt`로 KOSDAQ 목록을 받는다. 응답은 EUC-KR HTML로 읽는다. 사용자가 다른 시장이나 비상장사를 지정하면 그 범위를 따른다.

사용자가 ‘우리은행’으로 조회하면 우리금융지주로 연결하고 답변에 조회 기준을 쓴다. 요청한 시장에서 공식 발행사 자료로 관계를 확인한다. DART에서는 회사 정보와 공시를, EDGAR에서는 해당 발행사 6-K와 첨부자료를 확인한다. 사용자가 우리은행 자체 별도 재무제표를 명시하면 그 요청을 따른다.

미국 회사는 SEC 공식 티커 자료 `https://www.sec.gov/files/company_tickers_exchange.json`과 공시 표지로 법인명, 거래소, 티커와 CIK를 확인한다. 모회사와 자회사, 보통주와 ADR을 구분한다.

## 공식 자료

[DART](https://dart.fss.or.kr/) 공개 뷰어를 이용하며, 키가 준비됐으면 [OpenDART](https://opendart.fss.or.kr/)를 `fetch`로 호출한다.

- `corpCode.xml`, `company.json`: 회사 식별.
- `list.json`: 제출 목록. 페이지와 정정 공시를 확인한다.
- `document.xml`, 공개 뷰어: 본문, 주석과 첨부자료. 직접 열람할 때 목차에서 얻은 `rcpNo`, `dcmNo`, `eleId`, `offset`, `length`, `dtd`를 `/report/viewer.do`에 전달할 수 있다.
- `fnlttSinglAcnt.json`, `fnlttSinglAcntAll.json`, `fnlttMultiAcnt.json`: 재무 항목. 보고서 코드는 사업 `11011`, 반기 `11012`, 1분기 `11013`, 3분기 `11014`이며 연결은 `CFS`, 별도는 `OFS`다.

[SEC EDGAR](https://www.sec.gov/edgar/search/)에서는 아래 경로를 쓴다. CIK는 데이터 API에서 10자리로 맞춘다. HTTP 요청에는 식별 가능한 User-Agent를 쓰고 SEC Fair Access 정책을 따른다.

- `https://data.sec.gov/submissions/CIK##########.json`: 제출 목록. 과거 자료는 응답에 연결된 추가 submissions 파일도 읽는다.
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`: 회사 전체 기준 표준 재무 항목. 태그, 단위, 기간, 제출일과 accession number를 확인한다.
- `https://www.sec.gov/Archives/edgar/data/`: 해당 accession 원문과 첨부자료. 주석, 부문, 지역과 회사별 확장 태그는 원문 또는 Inline XBRL에서 확인한다.

미국 국내 발행사는 10-K와 10-Q, 외국 민간 발행사는 20-F와 6-K 등 실제 제출 형식을 따른다. 6-K는 재무자료가 포함된 첨부까지 읽는다. API 수치는 원문 표 제목, 열 제목과 단위로 확인한다.

## 기간과 항목

‘최신’은 조회 시점까지 제출된 관련 보고서를 뜻한다. 정기보고서 주석 요청에는 해당 주석이 포함된 최신 정기보고서를 선택한다. 대상 기간과 제출일을 구분하고 정정 범위를 확인한다.

기본은 연결 기준이다. 전년동기는 같은 전년도 기준일 또는 같은 길이 회계기간으로 맞춘다. 잔액은 기준일, 매출과 이익은 기간으로 비교하며 당분기와 누적을 구분한다. 분기나 반기 전년동기를 비교할 때 현재 보고서에 전년 말 잔액만 있으면 전년도 같은 분기나 반기 보고서를 추가 조회한다. 다른 날짜나 별도 수치로 대체하지 않는다. 통화, 단위, 연결 범위와 재작성 여부를 확인하고 당시 공시 기준 요청에는 당시 공개 수치를 쓴다.

요청한 공시 목록, 본문, 재무제표, 비율, 부문별 또는 지역별 매출, 수주와 수주잔고, 지분, 이사회, 실적, 자본 변동에 필요한 원문과 주석을 조회한다. 비율은 분자와 분모 및 기간을 맞추고 필요하면 평균 잔액을 구한다. 부문 매출은 내부 거래와 연결 조정을, 수주는 회사가 공시한 정의를 확인한다.

우발사항과 약정은 관련 주석 전체를 읽는다. 소송 청구액, 지급보증, 충당부채, 구매 약정과 기타 약정을 구분한다. 합계가 필요하면 같은 기준으로 공시된 금액에서 중복을 확인한 뒤 합산한다. 청구액을 예상 손실로, 약정 전액을 충당부채로 표시하지 않는다.

주가는 같은 회사 식별 절차를 거친 뒤 공식 거래소 시세에서 조회한다. 통화, 기준 시각과 시간대, 종가 또는 장중 가격을 간결하게 표시한다.

## 답변

질문에 먼저 답하고 수치 비교는 표로 쓴다. 실제 기준일 또는 기간, 단위와 연결 범위를 표시한다. 공시값과 직접 계산한 증감이나 비율을 구분한다. 근거에는 발행사, 보고서명, 제출일, 관련 절이나 주석명과 사용자가 열 수 있는 공식 원문 링크를 붙인다. 요청에 필요한 사실과 계산으로 변화를 설명한다.
