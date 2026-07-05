import os
import json
import google.generativeai as genai  # 가장 안정적인 라이브러리로 교체합니다.
import config
import telegram_logger

# 🔐 깃허브 비밀 금고(Secrets)에서 구글 Gemini API 열쇠를 가져옵니다.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def run_ai_filter(all_jobs):
    """
    수집된 전체 채용 공고(all_jobs)를 Gemini AI에게 보내
    질문자님의 프로필과 매칭되는 알짜 공고만 골라내고 분석을 요청하는 함수입니다.
    """
    if not all_jobs:
        print("ℹ️ [AI 필터] 수집된 공고가 없어 AI 분석을 건너뜁니다.")
        return "금일 수집된 조건에 맞는 채용 공고가 없습니다."

    if not GEMINI_API_KEY:
        print("⚠️ [AI 필터] GEMINI_API_KEY가 설정되지 않았습니다.")
        return "AI API 키 설정 오류로 분석을 진행하지 못했습니다."

    print(f"🤖 Gemini AI에게 {len(all_jobs)}개의 공고 분석을 요청합니다...")

    try:
        # 구버전 라이브러리의 안정적인 세팅 방식입니다.
        genai.configure(api_key=GEMINI_API_KEY)

        # 텍스트 데이터 변환
        jobs_json_text = json.dumps(all_jobs, ensure_ascii=False, indent=2)

        # AI 면접관 뼈대 대본
        prompt = f"""
당신은 최고의 헤드헌터이자 커리어 컨설턴트 AI입니다.
아래 제공된 [채용 공고 리스트]를 꼼꼼히 읽고, [구직자 프로필] 및 [희망 기업 조건]과 가장 잘 어울리는 알짜 공고를 선별하여 리포트를 작성해 주세요.

[구직자 프로필]
{config.MY_PROFILE}

[희망 기업 및 수집 조건]
- 타겟 기업 형태: {config.CHOSEN_COMPANY_TYPE}
- 특별 지시사항: {config.AI_SPECIAL_INSTRUCTIONS}

[채용 공고 리스트]
{jobs_json_text}

--------------------------------------------------
⚙️ [작성 규칙 및 출력 양식]
1. 위 공고 리스트 중 구직자의 경력(화장품, 해외영업 1년차 주니어), 어학(원어민 영어 능력), 캐나다 시민권자 등의 강점이 잘 발휘될 수 있고 {config.CHOSEN_COMPANY_TYPE} 조건에 부합하는 공고를 최대 5개 이내로 엄선해 주세요.
2. 매칭 점수는 100점 만점 기준으로 구직자 스펙과의 적정성을 냉정하게 평가해 주세요.
3. 텔레그램 메시지로 가독성 있게 볼 수 있도록, <b> 및 <i> 등의 HTML 태그를 적절히 활용하여 예쁘게 꾸며주세요.
4. 아래 [출력 서식]을 반드시 그대로 지켜서 응답해 주세요.

[출력 서식 예시]
📢 <b>[AI 추천 대기업/외국계 채용 레포트]</b>

🔥 <b>1. [추천] 회사명 - 공고 타이틀</b>
• <b>출처 / 지역:</b> 사람인 / 서울
• <b>매칭 점수:</b> 95점 / 100점
• <b>추천 이유:</b> 화장품 산업군 대기업 공고이며, 영어 원어민 우대 조건이 질문자님의 OPIc AL 및 캐나다 시민권 스펙과 찰떡궁합입니다. 주니어 경력직으로 지원하기 아주 좋습니다.
• <b>공고 링크:</b> <a href="공고URL">여기를 클릭하여 공고 보기</a>

(추천할 만한 공고들을 위 양식으로 이어서 작성해 주시고, 만약 정말 매칭되는 게 없다면 "조건에 맞는 추천 공고가 없습니다."라고 정중히 적어주세요.)
"""

        # 호환성이 가장 높고 똑똑한 gemini-2.5-flash 모델을 명시하여 호출합니다.
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)

        ai_report = response.text
        print("✅ [AI 필터] 분석 리포트 생성이 완료되었습니다.")
        return ai_report

    except Exception as e:
        telegram_logger.log_error("ai_filter.py (Gemini AI 분석 중)", e)
        return f"❌ AI 분석 중 에러가 발생했습니다: {e}"
