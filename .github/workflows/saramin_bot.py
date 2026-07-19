# -*- coding: utf-8 -*-
"""
saramin_bot.py
사람인(Saramin) 통합검색 수집 봇  (구조는 jobkorea_bot.py 와 동일)

기능 요약
  - 8개 키워드를 순서대로 하나씩 검색하고, 뒤 페이지까지 전부 수집.
  - 검색조건 필터(기업형태 8종 / 지역 5곳)를 URL로 서버에서 적용.
  - 검색결과 목록에서만 수집(상세페이지 미방문 → 빠름).
  - 공고 고유번호(rec_idx)가 같으면 동일 공고로 보고, '처음 걸린 키워드 / 처음 데이터'만 1줄로 기록.
  - 사람인은 목록에 실제 등록일/수정일이 있어 그대로 저장. 등록일(없으면 수정일) 기준 최근 1개월만 남김.
  - 재실행 시 기존 파일에 신규 공고만 누적 + 수집 60일 지난 공고는 자동 삭제.

필요 라이브러리:
    pip install requests beautifulsoup4 lxml

주의:
  * 개인/연구 목적의 소량 수집을 전제로 하며 요청 사이 지연을 둡니다.
  * 사람인 이용약관 및 robots 정책을 확인하고 과도한 트래픽을 유발하지 마세요.
  * 사이트 구조(HTML)는 수시로 바뀝니다. 파싱이 비면 parse_page()의 추출부를 조정하세요.
"""

import os
import csv
import re
import time
import random
from datetime import datetime, date, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# ===========================================================================
# 1) 설정 -- 여기만 바꾸면 됩니다
# ===========================================================================

# 검색 키워드 (이 순서가 중복 공고의 '첫 키워드' 우선순위가 됩니다)
KEYWORDS = ["마케팅", "해외영업", "신입", "공채", "글로벌", "marketing", "MD", "브랜드"]

# 검색조건 필터 (searchword, recruitPage 제외한 나머지 전부)
#  loc_mcd      -> 지역: 인천(108000)·서울(101000)·세종(118000)·경기(102000)·대전(105000)
#  company_type -> 기업형태 8종(대기업/외국계/코스닥/중견/공사공기업/코스피/중소/외부감사법인)
#  company_cd   -> 추가 선택 코드(URL 값 그대로)
EXTRA_PARAMS = (
    "searchType=search"
    "&company_cd=0,1,2,3,4,5,6,7,9,10"
    "&loc_mcd=108000,101000,118000,102000,105000"
    "&company_type=scale001,foreign,kosdaq,scale002,public,kospi,scale003,incorporated"
    "&panel_type=&search_optional_item=y&search_done=y&panel_count=y&preview=y"
)

# 최근 N일 이내 등록(없으면 수정)된 공고만 저장  (1개월 = 31)
RECENT_DAYS = 31

# 메인 데이터 파일 (재실행 시 신규 공고만 여기에 누적)
MAIN_CSV = "saramin_list.csv"

# 안전장치: 키워드당 최대 페이지 수 (0 = 무제한, 신규 공고 없을 때까지)
MAX_PAGES = 0

# 수집일(수집일시) 기준 이 일수를 넘은 공고는 저장 시 자동 삭제
RETENTION_DAYS = 60

# 요청 사이 지연(초). 차단/서버부담 방지를 위해 반드시 유지하세요.
DELAY_RANGE = (1.2, 2.5)

BASE = "https://www.saramin.co.kr"
SEARCH_URL = BASE + "/zf_user/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": BASE + "/",
}

# CSV 컬럼 순서
FIELDS = [
    "rec_idx", "키워드", "수집일시", "등록일", "날짜구분",
    "기업명", "공고제목", "직무카테고리", "근무지역",
    "경력", "학력", "고용형태", "마감일", "공고링크",
]

# 파싱용 정규식
REC_IDX_RE = re.compile(r"rec_idx=(\d+)")
REGION_RE = re.compile(
    r"^(서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|전국|해외)"
)
CAREER_RE = re.compile(r"(신입·경력|경력무관|신입|경력\s*\d+~?\d*년?[↑\s]*|경력)")
EDU_RE = re.compile(r"(학력무관|고졸|초대졸|대졸|대학원|석사|박사)