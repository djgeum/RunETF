import os
import json
from google import genai
from google.genai import types
import config
import telegram_logger

# 🔐 깃허브 비밀 금고(Secrets)에서 구글 Gemini API 열쇠를 가져옵니다.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def run_ai_filter(all_jobs):
    """
    수집된 전체 채용 공고(all_jobs)를 Gemini AI에게 보내
    질문자님의 프로필과 매칭되는 알짜 공고만 골라내고 분석을 요청하는 함수입니다.
    """
    # 만약 공고가 하나도 없다면 AI를 깨울 필요 없이 바로 종료합니다.
    if not all_jobs:
        print("ℹ️ [AI 필터] 수집된 공고가 없어 AI 분석을 건너뜁니다.")
        return "금일 수집된 조건에 맞는 채용 공고가 없습니다."

    # 구글 API 키가 설정되어 있는지 확인합니다.
    if not GEMINI_API_KEY:
        print("⚠️ [AI 필터] GEMINI_API_KEY가 설정되지 않았습니다.")
        return "AI API 키 설정 오류로 분석을 진행하지 못했습니다."

    print(f"🤖 Gemini AI에게 {len(all_jobs)}개의 공고 분석을 요청합니다...")

    try:
        # 1. 최신 공식 구글 GenAI 클라이언트를 생성합니다.
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 2. AI에게 넘겨줄 채용공고 리스트를 이쁘게 글자(텍스트)로 변환합니다.
        jobs_json_text = json.dumps(all_jobs, ensure_ascii=False, indent=2)

        # 3. AI 면접관에게 보낼 "역할 대본(프롬프트)"을 작성합니다.
        # config.py에 적어둔 질문자님의 정보들이 여기에 쏙쏙 조립됩니다.
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

        # 4. 가장 똑똑하고 합리적인 가성비를 자랑하는 gemini-2.5-flash 모델을 깨워 대화를 나눕니다.
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )

        # 5. AI가 답변해 준 최종 리포트 텍스트를 배달용으로 반환합니다.
        ai_report = response.text
        print("✅ [AI 필터] 분석 리포트 생성이 완료되었습니다.")
        return ai_report

    except Exception as e:
        # 🚨 실패하면 안전장치(텔레그램 SOS)를 발동시키고 에러 메시지를 보냅니다.
        telegram_logger.log_error("ai_filter.py (Gemini AI 분석 중)", e)
        return f"❌ AI 분석 중 에러가 발생했습니다: {e}"

if __name__ == "__main__":
    # 임시 테스트용 가짜 데이터 주머니
    sample_jobs = [
        {"site": "피플앤잡", "company": "가상화장품기업", "title": "해외영업 주니어 채용 (영어 필수)", "url": "https://example.com", "location": "서울", "experience": "경력무관"}
    ]
    # 이 파일만 따로 실행했을 때 AI가 잘 작동하는지 확인하는 용도입니다.
    # (실제 구동을 위해선 GEMINI_API_KEY가 환경변수에 들어있어야 합니다.)
    print(run_ai_filter(sample_jobs))
