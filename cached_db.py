"""
hana_p — db.py 조회를 짧은 TTL로 캐싱한다. Streamlit은 위젯 값이 바뀔 때마다(검색어 입력,
필터 변경, 브리핑 날짜 선택 등) 스크립트를 처음부터 다시 실행하는데, 이 앱은 지금까지 그때마다
DB를 다시 조회하고 카테고리 분류·클러스터링까지 처음부터 재계산했다. 캐시가 없으면 동시에
여러 사용자가 접속했을 때도 같은 조회/계산이 그만큼 배로 반복된다.

channels는 리스트라 해시 불가능하므로 tuple로 받는다 — 호출부에서 변환해서 넘겨야 한다.

새 데이터가 수집되거나 관리자가 삭제/설정을 바꾸면 최대 TTL만큼 화면 반영이 늦어질 수 있다 —
이 앱의 자동 수집 주기(몇 시간 단위)에 비하면 무시할 수준이라 60초로 뒀다. 즉시 반영이 필요한
관리자 작업(삭제, 백필 등)은 해당 작업 뒤에 clear()를 호출해 캐시를 바로 비운다.
"""

import streamlit as st

import db


@st.cache_data(ttl=60, show_spinner=False)
def get_mentions(limit: int, channels: tuple | None = None, brand: str = "") -> list[dict]:
    return db.get_mentions(
        limit=limit, channels=list(channels) if channels is not None else None, brand=brand,
    )


@st.cache_data(ttl=60, show_spinner=False)
def get_policy_events(limit: int) -> list[dict]:
    return db.get_policy_events(limit=limit)


@st.cache_data(ttl=30, show_spinner=False)
def count_mentions() -> int:
    return db.count_mentions()


@st.cache_data(ttl=30, show_spinner=False)
def count_policy_events() -> int:
    return db.count_policy_events()


def clear() -> None:
    """관리자가 데이터를 수정한 뒤(삭제·백필·재수집 등) 호출해 캐시를 즉시 무효화한다."""
    get_mentions.clear()
    get_policy_events.clear()
    count_mentions.clear()
    count_policy_events.clear()
