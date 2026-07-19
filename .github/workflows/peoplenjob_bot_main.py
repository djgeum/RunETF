# -*- coding: utf-8 -*-
"""
peoplenjob_bot_main.py
피플앤잡 수집결과 중 '외국계(외국인투자기업)'로 확인된 공고만 골라내는 스크립트

흐름
  1) peoplenjob_list.csv       : 피플앤잡 봇이 수집한 공고 (입력)
  2) 외국인투자기업정보.xlsx     : 산업통상부 외국인투자기업 목록
                                  A열 기업명(한글) / B열 기업명(영문)  (1행 헤더)
  3) 공고의 기업명을 정규화 매칭 -> 한글명 또는 영문명 중 하나라도 일치하면 '외국계 확인'
  4) peoplenjob_main.csv       : 외국계로 확인된 공고만 저장 (B안)

매칭 규칙 (C안 절충)
  - 정규화: 한글 법인표기(㈜·(주)·주식회사 등) + 영문 접미사(Ltd/Inc/Corp/Co/LLC 등) 제거,
            공백·특수문자 제거, 영문 소문자화.  (단, 'Korea'는 유지 — 외국계 자회사명 핵심)
  - 정규화된 '목록 회사명' 길이 기준:
      * 2글자 이하 -> 완전일치만 (오탐 방지)
      * 3글자 이상 -> 완전일치 또는 '목록명 + 접미사'(목록명으로 시작)면 인정

필요 라이브러리:
    pip install openpyxl
"""

import os
import csv
import re

import openpyxl

# ===========================================================================
# 설정
# ===========================================================================
INPUT_CSV = "peoplenjob_list.csv"            # 피플앤잡 수집 결과 (입력)
FDI_XLSX = "외국인투자기업정보.xlsx"          # 외국인투자기업 목록
OUTPUT_CSV = "peoplenjob_main.csv"           # 외국계 확인 공고만 (출력)

CSV_COMPANY_COL = "기업명"                    # 피플앤잡 CSV의 회사명 컬럼
FDI_COL_KOR = 0                               # A열: 기업명(한글)
FDI_COL_ENG = 1                               # B열: 기업명(영문)

ADD_MATCH_COLUMN = True                       # 끝에 '매칭기업명'(매칭된 공식 외국계명) 추가
MATCH_COLUMN_NAME = "매칭기업명"

# 정규화 시 제거할 한글 법인/조직 표기
LEGAL_TOKENS = [
    "주식회사", "유한회사", "유한책임회사", "재단법인", "사단법인",
    "의료법인", "학교법인", "(주)", "（주）", "㈜", "(유)", "(재)",
    "(사)", "(합)", "(유한)", "(주식회사)",
]
# 정규화 시 제거할 영문 법인 접미사(단어 단위)
ENG_LEGAL_RE = re.compile(
    r"\b(co|company|ltd|limited|inc|incorporated|corp|corporation|llc|llp|"
    r"gmbh|ag|sa|plc|pte|bv|nv|kk|holdings|group)\b"
)


# ===========================================================================
# 회사명 정규화
# ===========================================================================
def normalize(name):
    """법인표기/영문접미사/공백/특수문자 제거 + 소문자화 -> 비교용 문자열."""
    if not name:
        return ""
    s = str(name).lower()
    for tok in LEGAL_TOKENS:
        s = s.replace(tok.lower(), " ")
    # 한글/영문/숫자만 공백으로 분리해 남김
    s = re.sub(r"[^0-9a-z가-힣]+", " ", s)
    # 영문 법인 접미사 단어 제거 (Korea 는 유지)
    s = ENG_LEGAL_RE.sub(" ", s)
    # 공백 제거
    s = re.sub(r"\s+", "", s)
    return s


# ===========================================================================
# 외국인투자기업 목록 로드 (한글 + 영문 둘 다)
# ===========================================================================
def load_fdi(path):
    """반환: {정규화명: 표시명(한글우선)}  (한글·영문 모두 등록, 중복은 첫 등장 우선)"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]

    fdi_map = {}
    for row in ws.iter_rows(min_row=2, values_only=True):   # 1행 헤더 건너뜀
        kor = str(row[FDI_COL_KOR]).strip() if len(row) > FDI_COL_KOR and row[FDI_COL_KOR] else ""
        eng = str(row[FDI_COL_ENG]).strip() if len(row) > FDI_COL_ENG and row[FDI_COL_ENG] else ""
        display = kor or eng
        if not display:
            continue
        for nm in (kor, eng):
            n = normalize(nm)
            if n and n not in fdi_map:
                fdi_map[n] = display
    wb.close()
    print(f"[외국계목록] 정규화 항목 {len(fdi_map)}개 로드 (한글+영문)")
    return fdi_map


# ===========================================================================
# 매칭 (C안 절충)
# ===========================================================================
def match_company(norm_company, fdi_map):
    if not norm_company:
        return None
    if norm_company in fdi_map:                 # 완전일치 (길이 무관)
        return fdi_map[norm_company]
    for L in range(3, len(norm_company)):       # 접두일치 (3글자 이상 목록명)
        prefix = norm_company[:L]
        if prefix in fdi_map:
            return fdi_map[prefix]
    return None


# ===========================================================================
# 메인
# ===========================================================================
def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[오류] 입력 파일 없음: {INPUT_CSV}")
        return
    if not os.path.exists(FDI_XLSX):
        print(f"[오류] 외국계목록 파일 없음: {FDI_XLSX}")
        return

    fdi_map = load_fdi(FDI_XLSX)

    with open(INPUT_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if CSV_COMPANY_COL not in fieldnames:
            print(f"[오류] CSV에 '{CSV_COMPANY_COL}' 컬럼이 없습니다. 컬럼: {fieldnames}")
            return
        rows = list(reader)

    print(f"[입력] {INPUT_CSV}: {len(rows)}건")

    out_fields = fieldnames + ([MATCH_COLUMN_NAME] if ADD_MATCH_COLUMN else [])
    matched = []
    for row in rows:
        company = (row.get(CSV_COMPANY_COL) or "").strip()
        if not company:
            continue
        hit = match_company(normalize(company), fdi_map)
        if hit:                                  # 외국계로 확인된 것만 저장
            if ADD_MATCH_COLUMN:
                row[MATCH_COLUMN_NAME] = hit
            matched.append(row)

    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        for r in matched:
            writer.writerow({k: r.get(k, "") for k in out_fields})

    print(f"[출력] {OUTPUT_CSV}: 외국계 확인 {len(matched)}건 / 전체 {len(rows)}건")
    for r in matched[:10]:
        tag = f"  <- {r.get(MATCH_COLUMN_NAME)}" if ADD_MATCH_COLUMN else ""
        print(f"  · {r.get(CSV_COMPANY_COL)} | {r.get('공고제목', '')}{tag}")


if __name__ == "__main__":
    main()