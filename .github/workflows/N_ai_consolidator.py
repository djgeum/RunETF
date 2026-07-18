import os
import sys
import json
import datetime
import google.generativeai as genai

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import config
    import telegram_logger
except ModuleNotFoundError as e:
    print(f"❌ 부품 누락: {e}")
    sys.exit(1)

def load_and_merge_data():
    files = ["saramin_raw.json", "jobkorea_raw.json", "peoplenjob_raw.json"]
    all_jobs = []
    for file_name in files:
        file_path = os.path.join(current_dir, file_name)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    all_jobs.extend(json.load(f))
            except Exception: pass
    return all_jobs

def deduplicate_jobs(jobs):
    seen = set()
    unique_jobs = []
    for job in jobs:
        identifier = f"{job['company']}_{job['title']}".replace(" ", "")
        if identifier not in seen:
            seen.add(identifier)
            unique_jobs.append(job)
    return unique_jobs

def generate_ai_report(jobs, api_key):
    print("🧠 [Gemini AI 정밀 필터] 신입/인턴/1년 미만 경력 및 직무 연관성 최종 검증 시작...")
    if not api_key: return "⚠️ GEMINI_API_KEY 누락"
        
    genai.configure(api_key=api_key)
    try: model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception: model = genai.GenerativeModel('gemini-pro')

    jobs_context = ""
    for i, job in enumerate(jobs, 1):
        jobs_context += f"[{i}] 출처: {job['site']} | 회사명: {job['company']} | 제목: {job['title']} | 링크: {job['url']} | 상세안내: {job['info']}\n"

    # 🔥 [지시 사항 반영] AI가 연차와 키워드 연관성만 집중 타격하도록 프롬프트 전면 보정
    prompt = (
        f"당신은 구직자를 위한 인공지능(AI) 채용 검증 비서입니다.\n"
        f"수집된 채용 공고 목록을 읽고, 구직자가 지정한 '스펙 및 연차 철칙'에 완벽히 부합하는 공고만 엄선해 리포트를 작성하세요.\n\n"
        f"[🎯 구직자 핵심 타겟 프로필]\n"
        f"1. 필수 연차 범위: 신입, 인턴, 또는 경력 1년 이하(1년 미만 포함)만 지원 가능한 포지션\n"
        f"2. 연관 직무 키워드: 마케팅, 해외영업, 공채, 글로벌, marketing, MD, 브랜드\n\n"
        f"[채용 공고 목록]\n"
        f"{jobs_context}\n\n"
        f"[🚨 AI 최종 판단 및 배제 규칙 - 필수 준수]\n"
        f"1. 통이미지/특수 양식 공고: 본문 상세안내에 '통이미지 공고' 혹은 '특수 양식' 마크가 붙은 공고는 AI가 내용을 읽을 수 없으므로, 탈락시키지 말고 '🖼️ [수동 확인 필요 공고]' 섹션에 제목과 링크를 그대로 살려두세요.\n"
        f"2. 경력/연차 조건 검증 (최우선): 본문 텍스트가 있는 공고의 경우, '경력 2년 이상', '경력 3년 이상', '대리/과장급' 등 신입이나 1년 차 이하가 지원할 수 없는 고연차 공고는 예외 없이 탈락(배제)시키세요.\n"
        f"3. 직무 연관성 검증: 공고의 핵심 업무가 8대 키워드(해외영업, 마케팅, MD, 브랜드, 글로벌 등)와 뚜렷하게 연관된 포지션인 경우에만 통과시키세요. 무관한 직무는 버리세요.\n"
        f"4. ❌ 배제 단어 차단: 관련 직무와 신입 조건에 맞더라도 제목이나 내용에 '어시스턴트', '계약직', 'assist', 'assistant' 단어가 들어가 있다면 무조건 탈락시키세요.\n\n"
        f"[리포트 작성 양식]\n"
        f"- 텔레그램 메신저로 읽기 편하게 명확한 줄바꿈과 깔끔한 이모지를 사용하세요.\n"
        f"- 통과된 공고는 [출처 / 회사명 / 공고 제목 / 바로가기 링크]를 표기하고, AI가 연차와 키워드 연관성을 만족한다고 판단한 이유(예: 신입 지원 가능 확인, 마케팅 직무 연관)를 아주 간결하게 한 줄로 요약해 주십시오."
    )

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ AI 리포트 생성 실패: {e}"

def main():
    print(f"\n⏰ [AI 통합 거름망 가동] - {datetime.datetime.now()}")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    logger = telegram_logger.TelegramLogger(token=telegram_token, chat_id=chat_id)
    raw_jobs = load_and_merge_data()
    
    if not raw_jobs:
        logger.log("📭 오늘 조건에 매칭되는 채용 공고를 단 1건도 찾지 못했습니다.")
        return

    unique_jobs = deduplicate_jobs(raw_jobs)
    final_report = generate_ai_report(unique_jobs, api_key=gemini_key)
    logger.send_report(final_report, filename="오늘의_맞춤_채용_리포트.txt")
    print("🎉 전 시스템 정밀 필터링 및 발송 완료!")

if __name__ == "__main__":
    main()
