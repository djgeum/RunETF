# -*- coding: utf-8 -*-
"""
ai_filter.py
채용공고 1건이 '내 지원 기준(my_criteria.md)'에 맞는지 Gemini로 판정하는 모듈.

판정 방식 (사이트별)
  - 잡코리아 / 사람인 : Gemini 'URL context' 도구로 링크를 직접 읽어 판단 (이미지 포함).
  - 피플앤잡(JS 렌더링 SPA) : URL로는 못 읽으므로 →
        ① Playwright 로 렌더 후 본문 '텍스트' 추출 (가벼움)
        ② 텍스트가 빈약하면 → 페이지 '스크린샷' 이미지로 폴백 (정확)
    추출한 텍스트/이미지를 Gemini 에 넘겨 판단.

반환
  - 각 공고에 대해 {"decision": "OK"/"NO", "reason": "...", "서류마감일": "..."}
  - 저장/전송은 하지 않는다(판정만). run_daily.py 가 OK 만 모아 txt→텔레그램으로 처리.

필요 라이브러리:
    pip install google-genai playwright
    playwright install chromium
환경변수:
    GEMINI_API_KEY   (GitHub Secrets)

단독 테스트:
    python ai_filter.py         # 샘플 공고 몇 건 판정 (GEMINI_API_KEY 필요)
"""

import os
import re
import json
import time

# ===========================================================================
# 설정
# ===========================================================================
CRITERIA_PATH = "my_criteria.md"          # 내 지원 기준서
MODEL = "gemini-2.5-flash"                 # 판별용 (빠르고 저렴). 정확도↑ 원하면 -pro 로.

TEXT_MIN_CHARS = 400                       # 피플앤잡 본문 텍스트가 이보다 짧으면 스크린샷 폴백
CALL_DELAY_SEC = 1.5                       # Gemini 호출 간 지연(분당 제한 대비)
NAV_TIMEOUT_MS = 30000
RENDER_WAIT_MS = 2000                      # JS 렌더 대기

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# CSV 컬럼(우리 수집 파일 기준)
COL_URL = "공고링크"
COL_TITLE = "공고제목"
COL_COMPANY = "기업명"


# ===========================================================================
# 기준서 / Gemini 클라이언트
# ===========================================================================
def load_criteria(path=CRITERIA_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_client():
    """google-genai 클라이언트. 키는 환경변수 GEMINI_API_KEY 에서."""
    from google import genai
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise SystemExit("[오류] 환경변수 GEMINI_API_KEY 가 설정되지 않았습니다.")
    return genai.Client(api_key=key)


def detect_site(url):
    if "peoplenjob.com" in url:
        return "peoplenjob"
    if "jobkorea.co.kr" in url:
        return "jobkorea"
    if "saramin.co.kr" in url:
        return "saramin"
    return "other"


# ===========================================================================
# 피플앤잡: Playwright 렌더 → 텍스트, 빈약하면 스크린샷 (브라우저 1회 기동 후 재사용)
# ===========================================================================
_PW = None   # (playwright, browser, context)


def _get_page():
    global _PW
    if _PW is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT, locale="ko-KR")
        _PW = (pw, browser, ctx)
    return _PW[2].new_page()


def close_browser():
    """판정이 끝나면 반드시 호출(브라우저 정리)."""
    global _PW
    if _PW is not None:
        pw, browser, ctx = _PW
        try:
            browser.close()
            pw.stop()
        finally:
            _PW = None


def get_peoplenjob_content(url):
    """반환: ('text', 본문텍스트) 또는 ('image', png_bytes)"""
    page = _get_page()
    try:
        page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(RENDER_WAIT_MS)          # JS 렌더 대기
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""
        text = (text or "").strip()
        if len(text) >= TEXT_MIN_CHARS:                # 텍스트 충분 → 텍스트 방식
            return "text", text
        png = page.screenshot(full_page=True)          # 빈약 → 스크린샷 폴백
        return "image", png
    finally:
        page.close()


# ===========================================================================
# 프롬프트 / Gemini 호출 / 응답 파싱
# ===========================================================================
def _job_summary(job):
    fields = [COL_COMPANY, COL_TITLE, "직무카테고리", "근무지역", "경력", "학력", "마감일"]
    return "\n".join(f"- {k}: {job.get(k, '')}" for k in fields if job.get(k))


def build_prompt(criteria, job, mode):
    if mode == "url":
        src = f"아래 URL의 채용공고 전체 내용(본문·이미지 포함)을 읽고 판단해줘.\nURL: {job.get(COL_URL, '')}"
    elif mode == "image":
        src = "첨부한 채용공고 스크린샷 이미지의 내용을 읽고 판단해줘."
    else:  # text
        src = "아래 [공고 본문] 텍스트를 읽고 판단해줘."

    return f"""{criteria}

======================
[판정 지시]
======================
{src}

참고용 공고 요약:
{_job_summary(job)}

위 '내 지원 기준'에 이 공고 한 건이 적합하면 decision 을 "OK", 아니면 "NO" 로 판정해.
- 직무명이 조금 달라도 '실제 업무'를 우선 보고, 업종은 제한하지 마.
- 지원하지 않는 직무(재무/회계/개발/생산/품질/구매/SCM/인사/R&D 등)면 "NO".
- 공고에서 서류 마감일을 찾아 함께 알려줘(없으면 "상시" 또는 "미확인").

반드시 아래 JSON 하나로만, 다른 말 없이 답해:
{{"decision": "OK 또는 NO", "reason": "한 줄 이유(한국어)", "서류마감일": "YYYY-MM-DD 또는 상시/미확인"}}"""


def call_gemini(client, mode, payload, prompt, retries=2):
    """mode: 'url'(url_context) / 'image'(png bytes) / 'text'(본문텍스트)"""
    from google.genai import types
    for attempt in range(1, retries + 1):
        try:
            if mode == "url":
                cfg = types.GenerateContentConfig(
                    tools=[types.Tool(url_context=types.UrlContext())]
                )
                r = client.models.generate_content(model=MODEL, contents=prompt, config=cfg)
            elif mode == "image":
                part = types.Part.from_bytes(data=payload, mime_type="image/png")
                r = client.models.generate_content(model=MODEL, contents=[part, prompt])
            else:  # text
                r = client.models.generate_content(
                    model=MODEL, contents=prompt + "\n\n[공고 본문]\n" + (payload or "")
                )
            return r.text or ""
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def parse_result(text):
    """모델 응답 텍스트에서 JSON 판정 추출(견고). 실패 시 보수적으로 NO."""
    if not text:
        return {"decision": "NO", "reason": "응답 없음", "서류마감일": ""}
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"decision": "NO", "reason": "형식 오류", "서류마감일": ""}
    try:
        d = json.loads(m.group(0))
    except Exception:
        return {"decision": "NO", "reason": "JSON 파싱 실패", "서류마감일": ""}
    dec = "OK" if "OK" in str(d.get("decision", "")).upper() else "NO"
    return {
        "decision": dec,
        "reason": str(d.get("reason", "")).strip(),
        "서류마감일": str(d.get("서류마감일", "")).strip(),
    }


# ===========================================================================
# 공개 함수: 공고 1건 / 여러 건 판정
# ===========================================================================
def judge_job(job, criteria, client):
    url = (job.get(COL_URL) or "").strip()
    try:
        if detect_site(url) == "peoplenjob":
            mode, payload = get_peoplenjob_content(url)     # text 또는 image
        else:
            mode, payload = "url", url                      # 잡코리아/사람인 = URL context
        prompt = build_prompt(criteria, job, mode)
        res = parse_result(call_gemini(client, mode, payload, prompt))
    except Exception as e:
        res = {"decision": "NO", "reason": f"판정 오류: {e}", "서류마감일": ""}
    time.sleep(CALL_DELAY_SEC)
    return res


def judge_jobs(jobs, criteria=None):
    """jobs: dict 리스트. 반환: 각 공고에 판정 결과 컬럼을 붙인 리스트."""
    if criteria is None:
        criteria = load_criteria()
    client = get_client()
    results = []
    try:
        for i, job in enumerate(jobs, 1):
            res = judge_job(job, criteria, client)
            row = dict(job)
            row["AI판정"] = res["decision"]
            row["판정이유"] = res["reason"]
            row["서류마감일_AI"] = res["서류마감일"]
            results.append(row)
            print(f"  [{res['decision']}] ({i}/{len(jobs)}) "
                  f"{job.get(COL_COMPANY, '')} | {str(job.get(COL_TITLE, ''))[:32]} "
                  f"— {res['reason'][:40]}")
    finally:
        close_browser()
    return results


# ===========================================================================
# 단독 테스트
# ===========================================================================
if __name__ == "__main__":
    import sys

    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY 환경변수를 설정한 뒤 실행하세요.")
        raise SystemExit(0)

    # 커맨드로 URL 을 주면 그 공고(들)를 판정, 없으면 샘플 사용
    #   예) python ai_filter.py "https://www.peoplenjob.com/jobs/6242242?..."
    url_args = [a for a in sys.argv[1:] if a.strip()]
    if url_args:
        jobs = [{COL_URL: u} for u in url_args]
    else:
        jobs = [
            {COL_COMPANY: "샘플기업A", COL_TITLE: "글로벌 마케팅 담당자",
             COL_URL: "https://www.jobkorea.co.kr/Recruit/GI_Read/49286743"},
            {COL_COMPANY: "샘플기업B", COL_TITLE: "해외영업 신입",
             COL_URL: "https://www.peoplenjob.com/jobs/6243626"},
        ]

    out = judge_jobs(jobs)
    print("\n=== 결과 요약 ===")
    for r in out:
        print(r["AI판정"], "|", r.get(COL_URL), "|", r.get("서류마감일_AI"), "|", r.get("판정이유"))
