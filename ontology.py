"""
hana_p — 뉴스카테고리/정책카테고리처럼 서로 다른 분류 체계 사이의 정적 관계(온톨로지)를
선언한다. 브랜드 role(own/competitor/market)은 이미 keywords.json에 있으므로 여기서
다시 선언하지 않는다. 관계 수가 적어(수십 개 수준) DB 테이블이 아니라 사람이 직접
읽고 고칠 수 있는 이 파일로 선언한다.
"""

CATEGORY_ALIGNMENT: dict[str, list[str]] = {
    "정책": ["규제·법령", "지원·사업"],
    "매물": ["지원·사업"],
    "시세·감정": ["통계·조사"],
}


def aligned_policy_categories(news_category: str) -> list[str]:
    """뉴스카테고리에 대응되는 정책카테고리 목록. 대응이 없으면 빈 리스트."""
    return CATEGORY_ALIGNMENT.get(news_category, [])


def aligned_news_categories(policy_category: str) -> list[str]:
    """정책카테고리에 대응되는 뉴스카테고리 목록(CATEGORY_ALIGNMENT을 역방향으로 조회).
    대응이 없으면 빈 리스트."""
    return [
        news_category
        for news_category, policy_categories in CATEGORY_ALIGNMENT.items()
        if policy_category in policy_categories
    ]
