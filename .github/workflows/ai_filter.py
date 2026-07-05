import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import config
except ImportError:
    class DummyConfig:
        USER_PROFILE = "4년제 대학 졸업(경영학) / 화장품 해외영업 1년 / 캐나다 시민권자 / OPic AL"
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    config = DummyConfig()


def filter_and_summarize(jobs, api_key=None):
    """수집 공고를 Gemini로 필터링/요약. 실패 시 기본 텍스트 요약으로 폴백."""
    print("🧠 [Gemini AI 엔진] 분석 시작...")

    api_key = api_key or config.GEMINI_API_KEY
    if not api_key or genai is None:
        print("⚠️ GEMINI_API_KEY 없음/라이브러리 미설치 → 기본 요약으로 대체")
        return _fallback_summary(jobs)

    genai.configure(api_key=api_key)

    model = None
    for model_name in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"):
        try:
            model = genai.GenerativeModel(model_name)
            break
        except Exception:
            continue
    if model is None:
        print("❌ 사용 가능한 Gemini 모델 없음 → 기본 요약")
        return _fallback_summary(jobs)

    jobs_context = ""
    for i, job in enumerate(jobs, 1):
        jobs_context += f"[{i}] 사이트: {job.get('site')}\n"
        jobs_context += f"회사명: {job.get('company')}\n"
        jobs_context += f"공고제목: {job.get('title')}\n"
        jobs_context += f"상세정보: {job.get('info')}\n"
        jobs_context += f"링크: {job.get('url')}\n"
        jobs_context += "-" * 40 + "\n"

    prompt = (
        "당신은 커리어 컨설팅 전문가이자 채용 전문 AI 비서입니다.\n"
        "아래 [구직자 프로필]을 기반으로, 오늘 수집된 [채용 공고 목록] 중 "
        "가장 적합하고 합격 확률이 높은 공고를 선별해 가독성 좋은 "
        "'맞춤형 채용 리포트'를 작성해 주세요.\n\n"
        f"[구직자 프로필]\n{str(config.USER_PROFILE)}\n\n"
        f"[채용 공고 목록]\n{jobs_context}\n\n"
        "[요구 사항]\n"
        "1. 선별 기준:\n"
        "   - 화장품 산업, 해외영업, 글로벌 마케팅, 외국계 기업에 가산점.\n"
        "   - 캐나다 시민권/영어 원어민급 역량이 우대되는 공고 최우선.\n"
        "   - 신입~3년차 요건 부합 여부 필터링.\n"
        "2. 리포트 내용:\n"
        "   - 🌟 오늘의 추천 Top 3~5 (회사명/직무/링크/추천사유)\n"
        "   - 각 공고마다 어필 강점 한 줄 팁\n"
        "   - 맞는 공고가 없으면 연관 공고 위주 간략 요약 + '맞춤 공고 없음' 명시\n\n"
        "정중한 한국어 비즈니스 톤. 텔레그램 파일로 전달되니 줄바꿈/가독성에 신경 써주세요."
    )

    try:
        response = model.generate_content(prompt)
        print("✅ Gemini 리포트 생성 완료!")
        return response.text
    except Exception as e:
        print(f"❌ Gemini 호출 오류: {e}")
        return _fallback_summary(jobs)


def _fallback_summary(jobs):
    """AI 실패 시 백업 요약."""
    if not jobs:
        return "⚠️ 수집된 공고가 없어 요약할 내용이 없습니다."
    summary = "⚠️ [시스템 알림] AI 분석 없이 수집된 공고 기본 목록을 전송합니다.\n\n"
    summary += "📋 오늘의 신규 채용 공고 전체 목록:\n\n"
    for i, job in enumerate(jobs, 1):
        summary += f"{i}. [{job.get('site')}] {job.get('company')} - {job.get('title')}\n"
        summary += f"🔗 {job.get('url')}\n\n"
    return summary
