from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> date:
    """한국 시각 기준 오늘 — 운영 서버가 UTC 여도 KST 자정 경계를 보장한다.

    `date.today()`(서버 로컬/UTC) 는 한국 자정~오전 9시 사이에 전날을 반환해
    거래일 기본값·기간 필터 경계가 하루 어긋난다. 그 버그를 막는 공용 헬퍼.
    """
    return datetime.now(KST).date()
