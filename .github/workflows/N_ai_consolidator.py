import os
import sys
import json
import datetime
import google.generativeai as genai

# =====================================================================
# [환경 세팅] 경로 고정 및 부품 파일 불러오기
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import config
    import telegram_logger
except ModuleNotFoundError as e:
    print(f"❌ 설정 파일 또는 텔레그램 로거를 찾을 수 없습니다: {e}")
    sys.exit(1)

def load_and_merge_data():
    """3개의 초고속 수집 로봇이 남겨둔 json 바구니를 모두 읽어와 하나로 합칩니다."""
    files = ["saramin_raw.json", "jobkorea_raw.json", "peoplenjob_raw.json"]
    all_jobs = []
    
    for file_name in files:
        file_path = os.path.join(current_dir, file_name)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    all_jobs.extend(data)
                    print(f"📥 [{file_name}] 에서 {len(data)}건의 데이터를 가져왔습니다.")
            except Exception as e:
                print(f"⚠️ {file_name} 읽기 실패: {e}")
        else:
            print(f"ℹ️ {file_name} 파일이 존재하지 않습니다.")
            
    return all_jobs

def deduplicate_jobs(jobs):
    """(회사명 + 공고제목)이 완전히 똑같은 중복 데이터를 제거합니다."""
    seen = set()
    unique_jobs = []
    
    for job in jobs:
        identifier = f"{job['company']}_{job['title']}".replace(" ", "")
        if identifier not in seen:
            seen.add(identifier)
            unique_jobs.append(job)
            
    print(f"✂️ 중복 제거 완료: 총 {len(jobs)}건 ➔ {len(unique_jobs)}건으로 압축됨")
    return unique_jobs

def generate_ai_report(jobs, api_key):
    """[산업군 확장 버전] 특정 산업 한정 없이 엄격한 직무/경력 조건으로 리포트를 작성합니다."""
    print("🧠 [Gemini AI 거름망] 전 산업군 대상 직무 정밀 필터링 시작...")
    if not api_key:
        return "⚠️ GEMINI_API_KEY가 없어 AI 분석을 건너뛰고 기본 목록을 출력합니다.\n\n" + str(jobs)
        
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        model = genai.GenerativeModel('gemini-pro')

    # AI가 가독성 높게 읽을 수 있도록 콘텍스트 변환
    jobs_context = ""
    for i, job in enumerate(jobs, 1):
        jobs_context += f"[{i}] 출처: {job['site']} | 회사명: {job['company']} | 제목: {job['title']} | 링크: {job['url']} | 1차 분류 및 본문정보: {job['info']}\n"

    # 🔥 특정 산업군(화장품) 제한을 완전히 빼고, 직무와 스펙 중심으로만 프롬프트 전면 수정
    prompt = (
        f"당신은 구직자를 위한 전문 커리어 컨설팅 비서입니다.\n"
        f"제공된 [채용 공고 목록]을 완벽하게 검증하여 구직자에게 딱 맞는 최종 리포트를 작성해 주세요.\n\n"
        f"[구직자 핵심 직무 프로필]\n"
        f"- 관심 분야: 전 산업군의 해외영업, 글로벌 마케팅, 브랜드 기획, MD, 글로벌 사업개발 등\n"
        f"- 연차 스펙: 신입 혹은 경력 1년 미만\n\n"
        f"[채용 공고 목록]\n"
        f"{jobs_context}\n\n"
        f"[🚨 필터링 및 배제 절대 규칙 - 필수 준수]\n"
        f"1. 통이미지 공고 패스: 본문 정보에 '통이미지 공고'라고 명시되어 있는 항목은 내용 분석이 불가능하므로, 절대로 탈락시키지 말고 '🖼️ [수동 확인 필요 이미지 공고]' 영역에 제목과 링크를 그대로 보존하여 리포트에 포함해 주세요.\n"
        f"2. 직무/경력 엄격 검증: 본문 텍스트 정보가 있는 공고의 경우, 특정 산업군(예: 화장품 등)에 한정 짓지 말고 오직 직무(해외영업, 마케팅, MD, 브랜드 등)와 '신입' 또는 '1년 미만의 경력'인 경우에만 지원 가능한지 철저하게 검증하세요. 이를 벗어나는 고연차 경력직 공고는 과감히 버리세요.\n"
        f"3. ❌ 배제 단어 필터링 (최우선): 관련 직무 조건에 부합하더라도, 공고 제목이나 본문 정보에 '어시스턴트', '계약직', 'assist', 'assistant' 등의 단어가 단 하나라도 포함되어 있다면 예외 없이 '전부 배제(탈락)' 시키고 리포트에서 제외하세요. 구직자는 정규직 신입/경력 트랙만 원합니다.\n\n"
        f"[리포트 작성 양식]\n"
        f"- 메신저(텔레그램)로 읽기 편하게 명확한 줄바꿈과 이모지를 사용해 주세요.\n"
        f"- 규칙을 통과한 추천 공고는 회사명, 공고 제목, 바로가기 링크를 명확히 표기하고 AI가 '신입 지원 가능 여부 판단 이유'를 간략히 덧붙여 주세요.\n"
        f"지시 사항을 완벽히 준수하여 정중하고 깔끔한 한국어 보고서를 출력하세요."
    )

    try:
        response = model.generate_content(prompt)
        print("✅ Gemini AI 전 산업군 필터링 리포트 생성 완료!")
        return response.text
    except Exception as e:
        print(f"❌ Gemini AI 호출 중 오류 발생: {e}")
        return "⚠️ AI 분석 중 오류가 발생했습니다. 직접 확인 요망.\n\n" + jobs_context

def main():
    print(f"\n=======================================================")
    print(f"⏰ [AI 통합 거름망] 전 산업군 확장 엔진 가동 - {datetime.datetime.now()}")
    print(f"=======================================================")
    
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    logger = telegram_logger.TelegramLogger(token=telegram_token, chat_id=chat_id)
    
    # 1. 수집 로봇들의 결과 파일 취합
    raw_jobs = load_and_merge_data()
    
    if not raw_jobs:
        logger.log("📭 오늘 모든 봇이 조건에 부합하는 신규 공고를 찾지 못했습니다.")
        return

    # 2. 중복 공고 정제
    unique_jobs = deduplicate_jobs(raw_jobs)
    
    # 3. AI 맞춤형 엄격 필터링 가동
    final_report = generate_ai_report(unique_jobs, api_key=gemini_key)
    
    # 4. 텔레그램으로 최종 요약본 배달
    print("🚀 전 산업군 조건 통과 완료! 텔레그램으로 리포트를 전송합니다.")
    logger.send_report(final_report, filename="오늘의_맞춤_채용_리포트.txt")
    
    print("🎉 초고속 스마트 자동화 시스템 운영이 완료되었습니다!")

if __name__ == "__main__":
    main()
