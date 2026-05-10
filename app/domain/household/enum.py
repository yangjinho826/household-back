from enum import StrEnum


class HouseholdRole(StrEnum):
    """가계부 멤버 권한"""

    OWNER = "OWNER"
    MEMBER = "MEMBER"
