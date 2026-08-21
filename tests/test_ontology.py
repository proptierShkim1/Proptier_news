import ontology


def test_aligned_policy_categories_known_news_category():
    assert ontology.aligned_policy_categories("정책") == ["규제·법령", "지원·사업"]


def test_aligned_policy_categories_unknown_returns_empty():
    assert ontology.aligned_policy_categories("해외") == []


def test_aligned_news_categories_known_policy_category():
    assert ontology.aligned_news_categories("지원·사업") == ["정책", "매물"]


def test_aligned_news_categories_unknown_returns_empty():
    assert ontology.aligned_news_categories("조직·인사") == []
