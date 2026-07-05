import os
import sys
import google.generativeai as genai

# =====================================================================
# [경로 보정 및 설정 파일 연동]
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# config.py에서 사용자 스펙 및 키워드 설정을 안전하게 가져옵니다.
try:
    import config
except ImportError:
    class DummyConfig:
        USER_PROFILE = "4년제 대학 졸업(경영학) / 화장품 해외영업 1년 경력 / 캐나다 시민권자 / OPic AL"
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    config = DummyConfig()


def filter_and_summarize(jobs, api_key=None):
    """
    수집된 공고 리스트를 Gemini AI에게 전달하여 
    사용자의 스펙에 가장 적합한 맞춤형 채용 공고를 선별하고 요약 보고서를 작성합니다.
    """
    print("🧠 [Gemini AI 엔진] 분석 및 필터링 가동 시작...")
    
    # 1. API 키 설정 (인증)
    api_key = api_key or config.GEMINI_API_KEY
    if not api_key:
        print("⚠️ GEMINI_API_KEY가 없습니다. AI 분석을 건너뛰고 기본 텍스트 요약을 진행합니다.")
        return _fallback_summary(jobs)
        
    genai.configure(api_key=api_key)
    
    # 2. AI 모델 선택
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        model = genai.GenerativeModel('gemini-pro')

    # 3. 데이터 정제 (공고 리스트를 텍스트로 변환)
    jobs_context = ""
    for i, job in enumerate(jobs, 1):
        jobs_context += f"[{i}] 사이트: {job.get('site')}\n"
        jobs_context += f"회사명: {job.get('company')}\n"
        jobs_context += f"공고제목: {job.get('title')}\n"
        jobs_context += f"상세정보: {job.get('info')}\n"
        jobs_context += f"링크: {job.get('url')}\n"
        jobs_context += "-" * 40 + "\n"

    # 4. 프롬프트 작성 (AI 지시서 - 문자열이 끊기지 않도록 문법 구조 교정)
    prompt = (
        f"당신은 커리어 컨설팅 전문가이자 채용 전문 AI 비서입니다.\n"
        f"아래의 [구직자 프로필]을 기반으로, 오늘 수집된 [채용 공고 목록] 중에서 가장 적합하고 합격 확률이 높은 공고를 선별하여 가독성 좋은 '맞춤형 채용 리포트'를 작성해 주세요.\n\n"
        f"[구직자 프로필]\n"
        f"{str(config.USER_PROFILE)}\n\n"
        f"[채용 공고 목록]\n"
        f"{jobs_context}\n\n"
        f"[요구 사항 및 리포트 작성 양식]\n"
        f"1. 선별 기준:\n"
        f"   - 화장품 산업, 해외영업, 글로벌 마케팅, 외국계 기업 공고에 가산점을 부여하세요.\n"
        f"   - 캐나다 시민권자 및 원어민급 언어(영어) 역량이 강력한 우대 조건이 될 수 있는 공고를 최우선으로 선별하세요.\n"
        f"   - 신입 혹은 1~3년 차 경력 요건에 부합하는지 필터링하세요.\n\n"
        f"2. 리포트 포함 내용:\n"
        f"   - 🌟 오늘의 추천 공고 Top 3~5개 선별 (회사명, 직무, 링크, AI의 추천 사유 포함)\n"
        f"   - 각 추천 공고마다 이 구직자가 '어떤 강점(예: 화장품 경력, 영어 원어민 역량 등)'을 어필하면 합격률이 높을지 한 줄 팁 제공\n"
        f"   - 만약 조건에 맞는 공고가 전혀 없다면, 수집된 전체 공고 중 그나마 연관성이 있는 공고 위주로 간략히 요약하고 '맞춤 공고 없음'을 명시해 주세요.\n\n"
        f"정중하고 깔끔한 한국어 비즈니스 톤으로 리포트를 완성해 주세요. 텔레그램 메신저 파일로 전달될 예정이므로 줄바꿈과 가독성에 신경 써주세요."
    )

    # 5. Gemini AI 호출 및 결과 반환
    try:
        response = model.generate_content(prompt)
        print("✅ Gemini AI 리포트 생성 완료!")
        return response.text
    except Exception as e:
        print(f"❌ Gemini AI 호출 중 오류 발생: {e}")
        return _fallback_summary(jobs)


def _fallback_summary(jobs):
    """AI 호출 실패 시 작동하는 백업용 일반 요약 시스템"""
    summary = "⚠️ [시스템 알림] Gemini AI 분석 오류로 인해 수집된 공고의 기본 목록을 전송합니다.\n\n"
    summary += "📋 오늘의 신규 채용 공고 전체 목록:\n\n"
    for i, job in enumerate(jobs, 1):
        summary += f"{i}. [{job.get('site')}] {job.get('company')} - {job.get('title')}\n"
        summary += f"🔗 링크: {job.get('url')}\n\n"
    return summary
