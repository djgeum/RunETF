# -*- coding: utf-8 -*-
"""
test_peoplenjob.py
Gemini 없이 피플앤잡 경로만 오프라인 테스트.
  - Playwright 로 상세페이지 렌더 → 텍스트 추출
  - 텍스트가 빈약하면 스크린샷(PNG) 저장 → 눈으로 확인

실행:
    py -3.13 test_peoplenjob.py "피플앤잡_공고_URL"
"""

import sys
import ai_filter

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.peoplenjob.com/jobs/6242242"
print(f"[테스트] {url}")

mode, payload = ai_filter.get_peoplenjob_content(url)
ai_filter.close_browser()

print("\n선택된 방식:", mode)
if mode == "text":
    print("텍스트 길이:", len(payload), "자")
    print("----- 본문 미리보기(앞 800자) -----")
    print(payload[:800])
else:
    with open("peoplenjob_test.png", "wb") as f:
        f.write(payload)
    print("스크린샷 저장 완료 → peoplenjob_test.png (파일 열어서 공고 내용이 보이는지 확인)")