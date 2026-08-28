"""
hana_p — Teams Webhook으로 오늘의 브리핑(news_feed.build_briefing_archive_content)을
Adaptive Card 형태로 발송한다. AiAxRadar 프로젝트의 pipeline/notify.py를 이식.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

import db
import news_feed
import utils

load_dotenv(Path(__file__).resolve().parent / ".env")

_LOCAL_SITE_URL_DEFAULT = "http://localhost:8501"

_TOP_N = 3
_MEDALS = ["🥇", "🥈", "🥉"]
# views/briefings.py._render_sections와 동일한 섹션 구성 — "브리핑 아카이브 화면과
# 똑같이 보내달라"는 요청에 따라 제목·TOP3 제한·항목 표시 방식을 그대로 맞춘다.
_SECTIONS = [
    ("own_brand_news", "🏠 프롭티어 관련 뉴스 TOP3", "자사 관련 소식 상위 3건입니다."),
    ("competitor_news", "⚔️ 경쟁사 동향 TOP3", "경쟁사 관련 소식 상위 3건입니다."),
    ("market_news", "🌐 시장 동향 TOP3", "AI·프롭테크 등 시장 전반 소식 상위 3건입니다."),
]


def _wrap(card: dict) -> dict:
    """Teams Workflows(Power Automate) 웹훅이 기대하는 발송 포맷으로 감싼다 — 구버전
    O365 커넥터의 MessageCard(@type)는 마이크로소프트가 퇴역시켰으므로 쓰지 않는다."""
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }


def _rank(i: int) -> str:
    return _MEDALS[i] if i < len(_MEDALS) else str(i + 1)


def _site_url() -> str:
    """"더보기" 버튼이 가리킬 이 앱의 주소. DEPLOY_HOST가 있으면(=배포 대상 정보를 아는
    로컬/관리자 머신) 로컬 자신으로, 없으면(=배포된 서버 자신 — DEPLOY_HOST는 배포 시
    제외됨, views/settings.py._filtered_env_content 참고) 배포 시 미리 심어둔 SITE_URL로
    연결한다."""
    if os.getenv("DEPLOY_HOST", ""):
        return os.getenv("LOCAL_SITE_URL", _LOCAL_SITE_URL_DEFAULT)
    return os.getenv("SITE_URL", "")


_TILE_ROW_SIZE = 4


def _metric_tile(label: str, value: int) -> dict:
    return {
        "type": "Column", "width": "stretch",
        "items": [{
            "type": "Container", "style": "emphasis",
            "items": [
                {"type": "TextBlock", "text": f"{value:,}", "size": "ExtraLarge", "weight": "Bolder",
                 "horizontalAlignment": "Center", "spacing": "None", "wrap": True},
                {"type": "TextBlock", "text": label, "isSubtle": True, "size": "Small",
                 "horizontalAlignment": "Center", "spacing": "None", "wrap": True},
            ],
        }],
    }


def _channel_count_tiles(total_count: int, channel_counts: dict) -> list:
    """채널별 집계를 한 줄 텍스트 대신 강조(emphasis) 배경의 타일로 보여준다 — 가독성
    피드백에 따라 views/briefings.py의 metric-box 타일 구성을 Adaptive Card로 옮긴 것."""
    ranked = sorted(channel_counts.items(), key=lambda kv: -kv[1])
    metrics = [("전체", total_count)] + ranked
    blocks: list = []
    for i in range(0, len(metrics), _TILE_ROW_SIZE):
        row = metrics[i:i + _TILE_ROW_SIZE]
        blocks.append({
            "type": "ColumnSet", "spacing": "Medium",
            "columns": [_metric_tile(label, value) for label, value in row],
        })
    return blocks


_MD_BLOCK_LEAD = re.compile(r"^(#{1,6}|[-*+]|>)(\s|$)")


def _md_safe(text: str) -> str:
    """제목/요약은 원문 스크랩 텍스트를 그대로 옮겨오는데, 문단 앞에 '#'을 쓰는
    사이트(예: thescoop.co.kr)의 글이 오면 Adaptive Card가 이를 헤딩으로 렌더링해
    글자가 커지는 사고가 있었다. 맨 앞의 마크다운 블록 기호만 이스케이프한다."""
    if not text:
        return text
    return _MD_BLOCK_LEAD.sub(lambda m: "\\" + m.group(1) + m.group(2), text, count=1)


def _news_item_card(it: dict, rank: str) -> dict:
    title = _md_safe(it["title"])
    content = [
        {"type": "TextBlock", "text": f"[{title}]({it['url']})", "weight": "Bolder", "wrap": True},
    ]
    if it.get("desc"):
        content.append({"type": "TextBlock", "text": _md_safe(it["desc"]), "size": "Small",
                         "isSubtle": True, "spacing": "Small", "wrap": True})
    meta = " · ".join(v for v in (it.get("brand"), it.get("channel"), it.get("posted_at")) if v)
    if meta:
        content.append({"type": "TextBlock", "text": meta, "size": "Small",
                         "isSubtle": True, "spacing": "Small", "wrap": True})
    return {
        "type": "Container", "style": "emphasis", "spacing": "Small",
        "items": [{
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "auto", "verticalContentAlignment": "Center", "items": [
                    {"type": "TextBlock", "text": f"{it.get('signal', '')}\n{rank}", "weight": "Bolder",
                     "horizontalAlignment": "Center", "wrap": True},
                ]},
                {"type": "Column", "width": "stretch", "items": content},
            ],
        }],
    }


def _news_section(title: str, note: str, items: list[dict]) -> list:
    if not items:
        return []
    blocks: list = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "spacing": "Medium", "wrap": True},
        {"type": "TextBlock", "text": note, "isSubtle": True, "size": "Small", "spacing": "None", "wrap": True},
    ]
    for i, it in enumerate(items[:_TOP_N]):
        blocks.append(_news_item_card(it, _rank(i)))
    return blocks


def build_adaptive_card(content: dict, report_date: str) -> dict:
    """news_feed.build_briefing_archive_content()가 만든 브리핑 내용을 views/briefings.py의
    브리핑 아카이브 화면과 동일한 구성(채널별 수집 현황 + 자사/경쟁사/시장 TOP3)으로
    Teams Adaptive Card 발송 페이로드를 만든다."""
    body: list = [
        {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
         "text": f"📝 브리핑 아카이브 {report_date}", "wrap": True},
    ]

    if not content.get("total_count"):
        body.append({"type": "TextBlock", "text": "❎ 오늘 선별된 기사가 없습니다.", "wrap": True})
    else:
        body += _channel_count_tiles(content["total_count"], content.get("channel_counts", {}))
        for key, title, note in _SECTIONS:
            body += _news_section(title, note, content.get(key, []))

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.2",
        "body": body,
    }
    site_url = _site_url()
    if site_url:
        card["actions"] = [
            {"type": "Action.OpenUrl", "title": "🔗 더보기", "url": f"{site_url.rstrip('/')}/briefings"},
        ]
    return _wrap(card)


def build_test_card() -> dict:
    """설정 화면에서 웹훅 연결을 수동으로 확인할 때 보내는 최소 테스트 카드."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return _wrap({
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.2",
        "body": [
            {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
             "text": "✅ hana_p 연결 테스트", "wrap": True},
            {"type": "TextBlock", "text": "Teams Webhook 설정이 정상적으로 연결됐습니다.", "wrap": True},
            {"type": "TextBlock", "size": "Small", "isSubtle": True, "text": f"시각: {now_str}", "wrap": True},
        ],
    })


def send_webhook(payload: dict, url: str, retries: int = 3, sleep_fn=time.sleep) -> tuple[bool, str]:
    last_error = ""
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return True, f"연결 성공 (HTTP {resp.status_code})"
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                sleep_fn(2 ** attempt)
    return False, last_error


def send_test_webhook(url: str) -> tuple[bool, str]:
    """설정 화면 전용 테스트 발송 — 재시도 없이 1회만 시도해 버튼 클릭 즉시 결과를 보여준다."""
    return send_webhook(build_test_card(), url, retries=0)


def build_daily_report_content() -> tuple[str, dict]:
    """오늘 수집된 mentions로 브리핑 내용을 만든다 — views/briefings.py의 "오늘" 탭이
    쓰는 것과 동일한 데이터."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    mentions = db.get_mentions_by_collected_date(today_str)
    content = news_feed.build_briefing_archive_content(
        mentions, news_feed.own_brand_names(), news_feed.competitor_brand_names(), news_feed.market_brand_names(),
    )
    return today_str, content


def send_daily_report(trigger: str) -> dict:
    """오늘의 브리핑을 켜져 있는 모든 웹훅에 발송하고, 실행 결과를 webhook_send_logs에
    한 줄 남긴다."""
    report_date, content = build_daily_report_content()
    payload = build_adaptive_card(content, report_date)
    webhooks = [w for w in utils.load_webhooks() if w.get("enabled")]
    ran_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not webhooks:
        db.insert_webhook_send_log({
            "ran_at": ran_at, "trigger": trigger, "targets": 0, "sent": 0, "ok": 0,
            "message": "등록된 웹훅 없음",
        })
        return {"targets": 0, "sent": 0}

    sent = 0
    for wh in webhooks:
        ok, _ = send_webhook(payload, wh["url"])
        if ok:
            sent += 1

    db.insert_webhook_send_log({
        "ran_at": ran_at, "trigger": trigger, "targets": len(webhooks), "sent": sent,
        "ok": 1 if sent == len(webhooks) else 0,
        "message": f"{sent}/{len(webhooks)}개 웹훅 발송 성공 · 기사 {content['total_count']}건",
    })
    return {"targets": len(webhooks), "sent": sent}
