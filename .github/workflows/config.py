import os
import sys

# =====================================================================
# [경로 보정] 시스템
# 모든 파일이 .github/workflows 안에 모여있으므로, 
# 현재 config.py가 실행되는 위치를 파이썬 경로에 추가하여 연동 오류를 방지합니다.
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# =====================================================================
# 🔍 1. 채용 공고 수집 설정 (질문자님 맞춤 필터)
# =====================================================================
# AI 비서가 채용 사이트 및 오픈 API에서 집중 탐색할 핵심 키워드 목록
KEYWORDS = ["해외영업", "화장품", "마케팅"]

# 질문자님의 핵심 스펙 반영 (AI 필터링용 참고 데이터)
USER_PROFILE = {
    "education": "4년제 대학 졸업 (경영학과)",
    "experience": "코스닥 상장 화장품 기업 해외영업 경력 1년 / 글로벌 화장품 기업 인턴",
    "language": "OPic AL",
    "citizenship": "캐나다 시민권자 (캐나다 고등학교 졸업)",
    "preferred_roles": ["화장품 해외영업", "글로벌 마케팅", "외국계 기업 마케팅/영업"]
}

# =====================================================================
# 🔐 2. 환경 변수 및 외부 서비스 연동 설정 (GitHub Secrets 매핑)
# =====================================================================
# 텔레그램 연동 정보
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 인공지능 분석 및 사이트 오픈 API 인증 키 목록
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SARAMIN_KEY = os.getenv("SARAMIN_KEY")
GOYONG_KEY = os.getenv("GOYONG_KEY")

# =====================================================================
# ⚙️ 3. 시스템 설정 값
# =====================================================================
# 각 수집 엔진에서 과도한 트래픽 방지 및 탐색 속도 향상을 위해 제한할 키워드당 최대 공고 수
MAX_JOBS_PER_KEYWORD = 5

# 결과 리포트 기본 파일 이름
DEFAULT_REPORT_FILENAME = "채용_정보_요약_리포트.txt"
