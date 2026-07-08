import os
import sys
import google.generativeai as genai

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import config
except ImportError:
    class DummyConfig:
        USER_PROFILE = "4년제 대학 졸업(경영학) / 화장품 해외영업 1년 경력 / 캐나다 시민권자 / OPic AL"
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    config = DummyConfig()

def filter_and_summarize(jobs, api_key=None):
    print("🧠 [Gemini AI 엔진] 맞춤형 및 타겟 기업 분석 시작...")
    
    api_key = api_key or config.GEMINI_API_KEY
    if not api_key:
        print("⚠️ GEMINI_API_KEY가 없습니다. 기본 요약을 진행합니다.")
        return _fallback_summary(jobs)
        
    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        model = genai.GenerativeModel('gemini-pro')

    jobs_context = ""
    for i, job in enumerate(jobs, 1):
        jobs_context += f"[{i}] 사이트: {job.get('site')}\n"
        jobs_context += f"회사명: {job.get('company')}\n"
        jobs_context += f"공고제목: {job.get('title')}\n"
        jobs_context += f"상세정보: {job.get('info')}\n"
        jobs_context += f"링크: {job.get('url')}\n"
        jobs_context += "-" * 40 + "\n"

    # 🔥 프롬프트 업그레이드: [★타겟기업] 마크가 붙은 공고는 무조건 보고서 최상단 배치 지시
    prompt = (
        f"당신은 구직자를 위한 커리어 컨설팅 전문가이자 스마트 채용 비서입니다.\n"
        f"제공된 [채용 공고 목록]을 분석하여 리포트를 작성하되, 다음 지시사항을 철저히 따라주세요.\n\n"
        f"[구직자 프로필]\n"
        f"{str(config.USER_PROFILE)}\n\n"
        f"[채용 공고 목록]\n"
        f"{jobs_context}\n\n"
        f"[🚨 중요 - 리포트 작성규칙]\n"
        f"1. 최우선 순위 반영: '상세정보' 칸에 [★타겟기업] 표시가 되어 있는 공고가 있다면, 구직자의 연차 적합도와 상관없이 리포트 맨 첫 번째 파트인 '🔥 [원픽 타겟 기업 채용 소식]' 영역에 무조건 무삭제로 포함시켜 주세요.\n"
        f"2. 직무/역량 매칭 선별: 그 외 일반 공고 중에서는 화장품 산업, 해외영업, 마케팅 직무 위주로 선별하고, 영어 원어민 우대(캐나다 시민권자 스펙 활용) 공고에 높은 점수를 주어 Top 3를 뽑아주세요.\n"
        f"3. 가독성 중심 작성: 메신저 텍스트 파일로 읽기 편하게 명확한 구조와 줄바꿈을 적용해 주세요.\n\n"
        f"정중하고 확실한 비즈니스 한국어 어조로 알찬 요약 보고서를 완성해 주세요."
    )

    try:
        response = model.generate_content(prompt)
        print("✅ Gemini AI 맞춤형 리포트 생성 완료!")
        return response.text
    except Exception as e:
        print(f"❌ Gemini AI 호출 중 오류 발생: {e}")
        return _fallback_summary(jobs)

def _fallback_summary(jobs):
    summary = "⚠️ [시스템 알림] Gemini AI 요약 오류로 수집된 로우 데이터를 전송합니다.\n\n"
    for i, job in enumerate(jobs, 1):
        summary += f"{i}. {job.get('company')} - {job.get('title')}\n🔗 {job.get('url')}\n"
        summary += f"ℹ️ {job.get('info')}\n\n"
    return summary
