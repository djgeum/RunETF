import os
import sys

# =====================================================================
# [경로 보정] 모든 파일이 .github/workflows 안에 있으므로 현재 경로를 우선 추가
# =====================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# =====================================================================
# 🔍 1. 채용 공고 수집 설정
# =====================================================================
# ⚠️ 각 키워드는 '따로따로' 검색됩니다 (합쳐서 AND 검색이 아님).
#    단어를 늘릴수록 결과가 줄어드는 게 아니라, 오히려 각각 더 많이 수집됩니다.
KEYWORDS = ["해외영업", "마케팅","신입","공채","브랜드","글로벌","MD"]

# 구직자 핵심 스펙 (AI 필터링용 참고 데이터)
USER_PROFILE = {
    "education": "4년제 대학 졸업 (경영학과)",
    "experience": "코스닥 상장 기업 해외영업 경력 1년 / 글로벌 기업 인턴 / 브랜드 마케팅 / MD",
    "language": "OPic AL",
    "citizenship": "캐나다 시민권자 (캐나다 고등학교 졸업)",
    
}

# =====================================================================
# 🔐 2. 환경 변수 및 외부 서비스 연동 (GitHub Secrets 매핑)
# =====================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SARAMIN_KEY = os.getenv("SARAMIN_KEY")
GOYONG_KEY = os.getenv("GOYONG_KEY")

# =====================================================================
# ⚙️ 3. 시스템 설정 값
# =====================================================================
# 키워드당 최대 수집 공고 수 (하드코딩 대신 이 값을 각 엔진에서 참조)
MAX_JOBS_PER_KEYWORD = 500

# 결과 리포트 기본 파일 이름
DEFAULT_REPORT_FILENAME = "채용_정보_요약_리포트.txt"

# 공용 HTTP 헤더 (봇 차단 완화용)
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
