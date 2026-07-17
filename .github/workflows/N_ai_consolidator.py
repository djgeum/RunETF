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
    """3개의 수집 로봇이 남겨둔 json 바구니를 모두 읽어와 하나로 합칩니다."""
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
            print(f"ℹ️ {file_name} 파일이 없습니다. (해당 봇이 공고를 못 찾았거나 에러)")
            
    return all_jobs

def deduplicate_jobs(jobs):
    """(회사명 + 공고제목)이 완전히 똑같은 중복 데이터를 제거합니다."""
    seen = set()
    unique_jobs = []
    
    for job in jobs:
        # 중복 판단의 기준: 회사명과 제목을 합친 문자열 (공백 제거하여 정확도 상승)
        identifier = f"{job['company']}_{job['title']}".replace(" ", "")
        
        if identifier not in seen:
            seen.add(identifier)
            unique_jobs.append(job)
            
    print(f"✂️ 중복 제거 완료: 총 {len(jobs)}건 ➔ {len(unique_jobs)}건으로 압축됨")
    return unique_jobs

def generate_ai_report(jobs, api_key):
    """정제된 데이터를 Gemini AI에게 넘겨 최종 분석 리포트를 작성합니다."""
    print("🧠 [Gemini AI 거름망] 분석 및 필터링 가동 시작...")
    if not api_key:
        return "⚠️ GEMINI_API_KEY가 없어 AI 분석을 건너뛰고 기본 목록을 출력합니다.\n\n" + str(jobs)
        
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        model = genai.GenerativeModel('gemini-pro')

    # AI가 읽을 수 있도록 데이터를 텍스트로 변환
    jobs_context = ""
    for i, job in enumerate(jobs, 1):
        jobs_context += f"[{i}] 출처: {job['site']} | 회사명: {job['company']} | 제목: {job['title']} | 링크: {job['url']} | 정보: {job['info']}\n"

    prompt = (
        f"당신은 구직자를 위한 커리어 컨설팅 전문가이자 스마트 채용 비서입니다.\n"
        f"제공된 [채용 공고 목록]을 분석하여 리포트를 작성하되, 다음 지시사항을 철저히 따라주세요.\n\n"
        f"[구직자 프로필]\n"
        f"{str(config.USER_PROFILE)}\n\n"
        f"[채용 공고 목록]\n"
        f"{jobs_context}\n\n"
        f"[🚨 중요 - 리포트 작성규칙]\n"
        f"1. 최우선 순위 반영: '상세정보' 칸에 [★타겟기업] 표시가 되어 있는 공고가 있다면, 구직자의 연차 적합도와 상관없이 리포트 맨 첫 번째 파트인 '🔥 [원픽 타겟 기업 채용 소식]' 영역에 무조건 무삭제로 포함시켜 주세요.\n"
        f"2. 직무/역량 매칭 선별: 그 외 일반 공고 중에서는 화장품 산업, 해외영업, 마케팅 직무 위주로 선별하고, 영어 원어민 우대(캐나다 시민권자 스펙 활용) 공고에 높은 점수를 주어 Top 3를 뽑아주세요. (맞지 않는 데이터는 과감히 버리세요)\n"
        f"3. 가독성 중심 작성: 텔레그램 메신저로 읽기 편하게 이모지를 적절히 섞어 명확한 구조와 줄바꿈을 적용해 주세요.\n\n"
        f"정중하고 확실한 비즈니스 한국어 어조로 알찬 요약 보고서를 완성해 주세요."
    )

    try:
        response = model.generate_content(prompt)
        print("✅ Gemini AI 맞춤형 리포트 생성 완료!")
        return response.text
    except Exception as e:
        print(f"❌ Gemini AI 호출 중 오류 발생: {e}")
        return "⚠️ AI 분석 중 오류가 발생했습니다. 직접 확인 요망.\n\n" + jobs_context

def main():
    print(f"\n=======================================================")
    print(f"⏰ [AI 통합 거름망] 최종 데이터 정리 및 배달 시작 - {datetime.datetime.now()}")
    print(f"=======================================================")
    
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    logger = telegram_logger.TelegramLogger(token=telegram_token, chat_id=chat_id)
    
    # 1. 3개의 바구니 데이터 모두 모으기
    raw_jobs = load_and_merge_data()
    
    if not raw_jobs:
        logger.log("📭 오늘 사람인, 잡코리아, 피플앤잡에서 수집된 신규 공고가 하나도 없습니다.")
        return

    # 2. 중복 공고 걷어내기
    unique_jobs = deduplicate_jobs(raw_jobs)
    
    # 3. AI 필터링 및 리포트 작성
    final_report = generate_ai_report(unique_jobs, api_key=gemini_key)
    
    # 4. 텔레그램 전송
    print("🚀 완벽하게 정제된 최종 리포트를 텔레그램으로 배달합니다!")
    logger.send_report(final_report, filename="오늘의_외국계_채용_리포트.txt")
    
    print("🎉 대규모 병렬 수집 및 AI 통합 시스템이 성공적으로 종료되었습니다!")

if __name__ == "__main__":
    main()
