from enum import Enum

from app.core.exceptions import CustomException, ErrorCode
from app.domain.account.enum import AccountType
from app.domain.category.enum import CategoryKind
from app.domain.portfolio.enum import PortfolioTxType
from app.domain.transaction.enum import TxType

# enum 이름(URL path) → 클래스 매핑
# 새 enum 노출 = 한 줄 추가
_DISPATCH: dict[str, type[Enum]] = {
    "account-type": AccountType,
    "category-kind": CategoryKind,
    "tx-type": TxType,
    "portfolio-tx-type": PortfolioTxType,
}


def get_enum_values(name: str) -> list[str]:
    """enum 의 모든 값 반환 (정의 순서 보장).

    프론트 셀렉션/필터 칩 옵션 생성용.
    """
    enum_cls = _DISPATCH.get(name)
    if not enum_cls:
        raise CustomException(ErrorCode.NOT_FOUND)
    return [e.value for e in enum_cls]
