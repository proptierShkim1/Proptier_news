import streamlit as st
import json
import os
import re
import datetime
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

import cached_db
import collector
import db
import theme
import vectorizer
from access_control import load_config, save_config, name_for_ip
from utils import (
    ALL_MENTION_CHANNELS,
    load_channel_visibility,
    load_collection_schedule,
    load_keywords,
    load_mk_news_collection_schedule,
    load_naver_news_collection_schedule,
    load_policy_collection_schedule,
    load_vector_collection_schedule,
    save_channel_visibility,
    save_collection_schedule,
    save_keywords,
    save_mk_news_collection_schedule,
    save_naver_news_collection_schedule,
    save_policy_collection_schedule,
    save_vector_collection_schedule,
)

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DEPLOY_LOG_PATH = ROOT / "data" / "deploy_log.jsonl"

_DEPLOY_HOST     = os.getenv("DEPLOY_HOST", "")
_DEPLOY_SSH_PORT = int(os.getenv("DEPLOY_SSH_PORT", "22"))
_DEPLOY_USER     = os.getenv("DEPLOY_USER", "")
_DEPLOY_PASS     = os.getenv("DEPLOY_PASS", "")
_DEPLOY_REMOTE   = os.getenv("DEPLOY_REMOTE_PATH", f"/home/{os.getenv('DEPLOY_USER','')}/hana_p")
_DEPLOY_APP_PORT = int(os.getenv("DEPLOY_APP_PORT", "7000"))

_UPLOAD_SUFFIXES = {".py", ".toml", ".txt", ".md", ".sh"}
_UPLOAD_DIRS     = {"views", "crawlers", ".streamlit", "data", "scripts"}
_UPLOAD_ROOT_EXTRAS = {".env"}
_SFTP_SKIP       = {"__pycache__", ".git", "venv"}
# 원격 서버가 자체적으로 쌓아온 수집 데이터/운영 상태를 로컬 배포가 덮어쓰지 않도록
# 제외한다 — .gitignore의 data/ 항목과 동일한 목록. 예전엔 news.db만 제외해서, 로컬의
# scheduler.log/vector_backups 등이 배포 때마다 서버 것을 덮어쓰고 있었다(로컬 pytest
# 실행 흔적이 서버 로그에 섞여 있던 원인).
_DATA_UPLOAD_SKIP = {
    "news.db", "access_config.json", "keywords.json", "collection_schedule.json",
    "policy_collection_schedule.json", "naver_news_collection_schedule.json",
    "mk_news_collection_schedule.json", "vector_collection_schedule.json",
    "channel_visibility.json", "agent_chat_history.json", "deploy_log.jsonl",
    "scheduler.log", "scheduler_last_fired.json", "vector_backups", "db_backups",
}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _persistent_tabs(labels: list, qp_name: str):
    """F5로 새로고침해도 선택된 탭이 유지되도록, 현재 탭을 쿼리 파라미터(qp_name)에
    기록하고 다음 로드 시 그 값을 기본 탭으로 되돌린다."""
    key = f"_tabs_{qp_name}"
    default = st.query_params.get(qp_name)
    if default not in labels:
        default = None

    def _on_change():
        st.query_params[qp_name] = st.session_state[key]

    return st.tabs(labels, default=default, key=key, on_change=_on_change)


def _render_lazy_tabs(labels: list, qp_name: str, render_fns: list) -> None:
    """_persistent_tabs로 탭 바를 그리되, 실제로 선택된 탭의 렌더 함수만 호출한다.
    st.tabs()는 선택 여부와 무관하게 모든 with tab: 블록의 코드를 매번 실행하는데, 무거운
    탭(예: 데이터 관리의 수천 건짜리 DataFrame 조회)이 섞여 있으면 다른 탭만 보려 해도
    매번 같이 돌아가서 설정 화면 전체가 느려진다.

    선택된 탭은 st.query_params가 아니라 st.tabs(key=...)가 채우는
    st.session_state[key]로 판단한다 — 쿼리 파라미터는 on_change 콜백이 채우는데, 클릭과
    쿼리 파라미터 갱신 사이에 몇 초씩 지연이 생겨(브라우저 주소창 반영 지연으로 추정) 그
    사이 렌더에서는 어떤 탭도 활성 탭과 매치되지 않아 화면 전체가 비어 보이는 버그가
    있었다. 위젯 자신의 session_state 값은 st.tabs() 호출 즉시 갱신되어 이 지연이 없다."""
    tabs = _persistent_tabs(labels, qp_name)
    active = st.session_state.get(f"_tabs_{qp_name}", labels[0])
    for label, tab, render_fn in zip(labels, tabs, render_fns):
        with tab:
            if label == active:
                render_fn()


def _log_deploy(action: str, status: str, detail: str = ""):
    ip = st.session_state.get("_client_ip", "") or ""
    actor = name_for_ip(ip) or ip or "unknown"
    entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "actor": actor,
        "action": action,
        "status": status,
        "detail": detail,
    }
    DEPLOY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEPLOY_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── 서버 배포 ──────────────────────────────────────────────────────────────

def _ssh_connect():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(_DEPLOY_HOST, port=_DEPLOY_SSH_PORT,
                username=_DEPLOY_USER, password=_DEPLOY_PASS, timeout=15)
    return ssh


def _ssh_run(ssh, cmd: str, timeout: int = 120):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    rc = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), rc


def _sftp_mkdir_p(sftp, remote: str):
    parts = remote.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except OSError:
            try:
                sftp.mkdir(cur)
            except OSError:
                pass


_DATA_UPLOAD_SKIP_PREFIXES = ("news.db.corrupted-", "news.db.autofailed-", "news.db.backup-")


def _sftp_upload_dir(sftp, local_dir: Path, remote_dir: str, log, skip_names: set = frozenset()):
    _sftp_mkdir_p(sftp, remote_dir)
    for item in sorted(local_dir.iterdir()):
        if (
            item.name in _SFTP_SKIP or item.suffix == ".pyc" or item.name in skip_names
            or item.name.startswith(_DATA_UPLOAD_SKIP_PREFIXES)
        ):
            continue
        remote_item = f"{remote_dir}/{item.name}"
        if item.is_dir():
            _sftp_upload_dir(sftp, item, remote_item, log, skip_names=skip_names)
        else:
            sftp.put(str(item), remote_item)
            log(f"↑ {item.relative_to(ROOT)}")


def _start_streamlit(ssh, log):
    script = f"{_DEPLOY_REMOTE}/scripts/start_server.sh"
    cmd = (
        f"sed -i 's/\\r$//' {script} 2>/dev/null || true; "
        f"chmod +x {script}; "
        f"HANA_ROOT={_DEPLOY_REMOTE} HANA_PORT={_DEPLOY_APP_PORT} bash {script}"
    )
    out, err, rc = _ssh_run(ssh, cmd, timeout=30)
    text = (out + err).strip()
    if rc == 0 and "NOT_LISTENING" not in text:
        log(f"🟢 Streamlit 기동 완료")
        log(f"접속 주소: http://{_DEPLOY_HOST}:{_DEPLOY_APP_PORT}")
    else:
        log(f"🔴 기동 실패:\n{text[-500:]}")


def _deploy():
    log_box = st.empty()
    lines = []

    def log(msg):
        lines.append(msg)
        log_box.code("\n".join(lines[-50:]), language=None)

    try:
        log(f"SSH 연결 중... {_DEPLOY_USER}@{_DEPLOY_HOST}:{_DEPLOY_SSH_PORT}")
        ssh = _ssh_connect()
        log("✅ SSH 연결 완료")

        out, _, _ = _ssh_run(ssh, f"test -d {_DEPLOY_REMOTE}/venv && echo YES || echo NO")
        first_deploy = out.strip() != "YES"

        sftp = ssh.open_sftp()
        _ssh_run(ssh, f"mkdir -p {_DEPLOY_REMOTE}")

        log("\n--- 코드 업로드 ---")
        for item in sorted(ROOT.iterdir()):
            if item.is_file() and (item.suffix in _UPLOAD_SUFFIXES or item.name in _UPLOAD_ROOT_EXTRAS):
                sftp.put(str(item), f"{_DEPLOY_REMOTE}/{item.name}")
                log(f"↑ {item.name}")
        for dir_name in _UPLOAD_DIRS:
            local_sub = ROOT / dir_name
            if local_sub.exists():
                skip = _DATA_UPLOAD_SKIP if dir_name == "data" else frozenset()
                _sftp_upload_dir(sftp, local_sub, f"{_DEPLOY_REMOTE}/{dir_name}", log, skip_names=skip)
        log("✅ 코드 업로드 완료")
        sftp.close()

        if first_deploy:
            log("\n--- 가상환경 설치 ---")
            out, err, rc = _ssh_run(ssh, f"python3 -m venv {_DEPLOY_REMOTE}/venv", timeout=60)
            log("✅ venv 생성" if rc == 0 else f"❌ venv 실패: {err.strip()}")

        # requirements-server.txt가 배포 이후 바뀔 수 있으므로 venv 존재 여부와 무관하게
        # 매 배포마다 설치를 다시 실행한다 (이미 설치된 패키지는 pip가 건너뛴다).
        log("\n--- 패키지 설치 ---")
        pip = f"{_DEPLOY_REMOTE}/venv/bin/pip"
        req = f"{_DEPLOY_REMOTE}/requirements-server.txt"
        log("패키지 설치 중... (수분 소요)")
        out, err, rc = _ssh_run(ssh, f"{pip} install --upgrade pip && {pip} install -r {req}", timeout=600)
        log("✅ 패키지 설치 완료" if rc == 0 else f"❌ 설치 실패:\n{err.strip()[-400:]}")

        log("\n--- Streamlit 기동 ---")
        _start_streamlit(ssh, log)
        ssh.close()
        _log_deploy("서버 배포", "success", "최초 배포" if first_deploy else "코드 업데이트")

    except Exception as e:
        log(f"\n❌ 배포 오류: {e}")
        _log_deploy("서버 배포", "fail", str(e))


def _render_deploy():
    st.subheader("🚀 서버 배포")

    if not _DEPLOY_HOST:
        st.info(".env에 DEPLOY_HOST 등 배포 설정이 없습니다.")
        return

    st.caption(f"대상: `{_DEPLOY_USER}@{_DEPLOY_HOST}:{_DEPLOY_APP_PORT}` (SSH: {_DEPLOY_SSH_PORT}) → `{_DEPLOY_REMOTE}`")
    st.caption("최초 배포 시 venv 생성 + 패키지 설치까지 자동 수행 / 이후 업데이트는 코드만 전송")

    col_dep, col_svc = st.columns(2)
    with col_dep:
        if st.button("🚀 서버에 배포", type="primary", use_container_width=True):
            _deploy()
    with col_svc:
        if st.button("🔄 Streamlit 재시작", use_container_width=True):
            log_box2 = st.empty()
            try:
                ssh2 = _ssh_connect()
                lines2 = []

                def log2(m):
                    lines2.append(m)
                    log_box2.code("\n".join(lines2), language=None)

                _start_streamlit(ssh2, log2)
                ssh2.close()
                _log_deploy("서비스 재시작", "success")
            except Exception as e:
                st.error(f"오류: {e}")
                _log_deploy("서비스 재시작", "fail", str(e))


# ── 접근 제어 ──────────────────────────────────────────────────────────────

def _render_access_control():
    client_ip = st.session_state.get("_client_ip", "") or ""
    cfg = load_config()
    allowed_ips = cfg.get("allowed_ips", [])
    allowed_ips = [
        entry if isinstance(entry, dict) else {"ip": entry, "name": ""}
        for entry in allowed_ips
    ]

    if not allowed_ips:
        st.warning(
            f"⚠️ 허용 IP가 등록되지 않아 **누구나** 접근할 수 있습니다.  \n"
            f"아래에서 본인 IP(`{client_ip}`)를 등록하세요."
        )

    st.subheader("허용 IP 관리")
    st.caption(f"현재 접속 IP: `{client_ip}`")

    col_name, col_ip = st.columns([2, 3])
    with col_name:
        new_name = st.text_input("이름", placeholder="예: 사무실, 김철수", key="input_name")
    with col_ip:
        new_ip = st.text_input("IP 주소", placeholder="예: 192.168.1.100", key="input_ip")

    new_is_admin = st.checkbox("슈퍼관리자로 등록", key="input_is_admin", help="켜면 설정 메뉴까지 볼 수 있습니다.")

    col_add, col_cur = st.columns(2)
    with col_add:
        submitted = st.button("➕ IP 추가", use_container_width=True)
    with col_cur:
        add_current = st.button("➕ 현재 접속 IP 추가", use_container_width=True)

    if submitted:
        ip_to_add = new_ip.strip()
        if not ip_to_add:
            st.warning("IP 주소를 입력하세요.")
        elif any(e["ip"] == ip_to_add for e in allowed_ips):
            st.warning("이미 등록된 IP입니다.")
        else:
            allowed_ips.append({"ip": ip_to_add, "name": new_name.strip(), "is_admin": new_is_admin})
            save_config({"allowed_ips": allowed_ips})
            st.session_state.input_name = ""
            st.session_state.input_ip = ""
            st.session_state.input_is_admin = False
            st.success(f"`{ip_to_add}` 추가됨")
            st.rerun()

    if add_current:
        if not client_ip:
            st.warning("현재 IP를 확인할 수 없습니다.")
        elif any(e["ip"] == client_ip for e in allowed_ips):
            st.warning("이미 등록된 IP입니다.")
        else:
            allowed_ips.append({"ip": client_ip, "name": new_name.strip(), "is_admin": new_is_admin})
            save_config({"allowed_ips": allowed_ips})
            st.session_state.input_name = ""
            st.session_state.input_ip = ""
            st.session_state.input_is_admin = False
            st.success(f"`{client_ip}` 추가됨")
            st.rerun()

    st.divider()
    if not allowed_ips:
        st.info("등록된 허용 IP가 없습니다. (현재 모든 접속 허용 중)")
    else:
        st.caption(f"등록된 허용 IP — {len(allowed_ips):,}개")
        for i, entry in enumerate(list(allowed_ips)):
            col_n, col_i, col_admin, col_del = st.columns([2.5, 3.5, 1.5, 1])
            col_n.write(entry.get("name") or "—")
            col_i.code(entry["ip"])
            cur_admin = entry.get("is_admin", False)
            new_admin = col_admin.checkbox("관리자", value=cur_admin, key=f"admin_{i}_{entry['ip']}")
            if new_admin != cur_admin:
                entry["is_admin"] = new_admin
                save_config({"allowed_ips": allowed_ips})
                st.rerun()
            if col_del.button("삭제", key=f"del_{i}_{entry['ip']}", use_container_width=True):
                allowed_ips = [e for e in allowed_ips if e["ip"] != entry["ip"]]
                save_config({"allowed_ips": allowed_ips})
                st.rerun()


# ── 데이터 수집 ────────────────────────────────────────────────────────────

def _format_entry_status(entry):
    return (
        f"{entry['fetched']:,}건 조회 (신규 {entry['inserted']:,}, 중복 {entry['skipped']:,})"
        if entry["ok"] else f"실패 - {entry['message']}"
    )


@st.fragment(run_every=2)
def _show_collection_progress(run_id):
    logs = [l for l in db.get_run_logs(limit=500) if l["run_id"] == run_id][::-1]
    if logs:
        lines = [f"[{e['channel']}] {e['brand']}: {_format_entry_status(e)}" for e in logs]
        st.code("\n".join(lines), language=None, height=200)
    if collector.active_run_id() == run_id:
        st.caption(f"🔄 진행 중... ({len(logs):,}건 완료)")
    else:
        ok_count = sum(1 for e in logs if e["ok"])
        st.success(f"수집 완료: {len(logs):,}건 실행, 성공 {ok_count:,}건")


def _render_brand_collection_tab():
    st.subheader("🏷️ 키워드 관리")
    st.caption("네이버·구글·다음·커뮤니티(디시인사이드) 4개 채널에서 수집합니다. API 키 불필요.")
    with st.expander("채널별 수집 방식"):
        st.markdown(
            "- **네이버**: 통합검색 결과 페이지 스크래핑 (블로그·카페)\n"
            "- **구글**: 뉴스 RSS 피드 파싱\n"
            "- **다음**: 뉴스 검색 결과 페이지 스크래핑 (최대 10페이지)\n"
            "- **커뮤니티**: 디시인사이드 통합검색 결과 스크래핑 (갤러리)"
        )
    kw_cfg = load_keywords()

    st.metric("등록 키워드", f"{len(kw_cfg['brands']):,}개")

    by_name = {b["name"]: b for b in kw_cfg["brands"]}
    own_names = [n for n, b in by_name.items() if b.get("role") == "own"]
    competitor_names = [n for n, b in by_name.items() if b.get("role", "competitor") == "competitor"]
    market_names = [n for n, b in by_name.items() if b.get("role") == "market"]

    own_text = st.text_area(
        "우리 브랜드 (쉼표로 구분)", value=", ".join(own_names), height=68,
        placeholder="예: 프롭티어", key="own_brand_text",
    )
    competitor_text = st.text_area(
        "경쟁사 (쉼표로 구분)", value=", ".join(competitor_names), height=100,
        placeholder="예: 직방, 다방", key="competitor_text",
    )
    market_text = st.text_area(
        "시장 키워드 (쉼표로 구분)", value=", ".join(market_names), height=68,
        placeholder="예: AI, 부동산AI, 프롭테크", key="market_keyword_text",
    )

    if st.button("💾 저장", key="save_brand_list"):
        groups = [("competitor", competitor_text), ("market", market_text), ("own", own_text)]
        role_by_name: dict[str, str] = {}
        for role, text in groups:
            for name in [x.strip() for x in text.split(",") if x.strip()]:
                role_by_name[name] = role
        kw_cfg["brands"] = [
            {**by_name.get(name, {"name": name}), "role": role}
            for name, role in role_by_name.items()
        ]
        save_keywords(kw_cfg)
        st.rerun()

    context_words = kw_cfg.get("context") or collector._REAL_ESTATE_CONTEXT_WORDS
    with st.expander(f"필수 포함 키워드 ({len(context_words):,}개, 전체 키워드 공통)"):
        st.caption("제목/스니펫에 이 중 하나라도 없으면 노이즈로 간주해 수집하지 않습니다.")
        context_text = st.text_area(
            "필수 포함 키워드 (쉼표로 구분)", value=", ".join(context_words), height=300, key="context_text",
        )
        if st.button("💾 저장", key="save_context"):
            seen = []
            for word in [x.strip() for x in context_text.split(",") if x.strip()]:
                if word not in seen:
                    seen.append(word)
            kw_cfg["context"] = seen
            save_keywords(kw_cfg)
            st.rerun()

    with st.expander(f"제외 키워드 ({len(kw_cfg.get('exclude', [])):,}개, 전체 키워드 공통)"):
        st.caption("제목/스니펫에 이 단어가 포함된 결과는 수집하지 않습니다.")
        exclude_text = st.text_area(
            "제외 키워드 (쉼표로 구분)", value=", ".join(kw_cfg.get("exclude", [])), height=150, key="exclude_text",
        )
        if st.button("💾 저장", key="save_exclude"):
            seen = []
            for excl in [x.strip() for x in exclude_text.split(",") if x.strip()]:
                if excl not in seen:
                    seen.append(excl)
            kw_cfg["exclude"] = seen
            save_keywords(kw_cfg)
            st.rerun()

    st.divider()
    st.subheader("⏰ 수집 스케줄")
    sched_cfg = load_collection_schedule()
    times_text = st.text_input(
        "수집 시각 (/로 구분)", value="/".join(sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="sched_times_text",
    )
    if st.button("💾 저장", key="sched_save"):
        tokens = [t.strip() for t in times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_collection_schedule({"times": seen})
            st.rerun()
    if sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(sched_cfg['times'])}")
    else:
        st.caption("등록된 수집 시각이 없습니다.")

    st.divider()
    running_run_id = collector.active_run_id()
    if running_run_id is None:
        if st.button("🔄 지금 수집", type="primary", key="collect_now"):
            started_run_id = collector.start_background_collection(trigger="수동")
            if started_run_id:
                db.log_activity(st.session_state.get("_client_ip", ""), "설정 · 데이터 수집", "신규 게시물 수집 실행")
                st.session_state["watched_collection_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 수집이 진행 중입니다.")
    else:
        st.info("🔄 수집이 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_collection_run_id"] = running_run_id

    display_run_id = running_run_id or st.session_state.get("watched_collection_run_id")
    if display_run_id:
        _show_collection_progress(display_run_id)

    st.divider()
    st.subheader("📜 수집 이력")
    batches = db.get_run_batches(limit=50, channels=["네이버", "구글", "다음", "커뮤니티"])
    if batches:
        batch_df = pd.DataFrame(batches)[
            ["ran_at", "trigger", "brands", "channels", "combinations",
             "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(batch_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 수집 이력이 없습니다.")


_POLICY_SOURCE_SECTIONS = [
    ("policy_collect_now", "🏛️ 국토교통부 보도자료", "국토교통부 보도자료를 수집합니다.",
     collector.collect_molit_press_releases),
    ("policy_reb_collect_now", "🏢 한국부동산원 보도자료", "한국부동산원 보도자료(가격동향 등)를 수집합니다.",
     collector.collect_reb_press_releases),
    ("policy_lh_collect_now", "🏗️ LH(한국토지주택공사) 보도자료", "LH 보도자료(공급·보상·사업 진행 등)를 수집합니다.",
     collector.collect_lh_press_releases),
    ("policy_seoul_collect_now", "🏙️ 서울시 정보소통광장 보도자료", "서울시 보도자료 중 주택/도시계획 관련만 수집합니다.",
     collector.collect_seoul_opengov_press_releases),
    ("policy_hf_collect_now", "🏦 HF(한국주택금융공사) 보도자료", "HF 보도자료(주택담보대출·보금자리론 등)를 수집합니다.",
     collector.collect_hf_press_releases),
    ("policy_hug_collect_now", "🛡️ HUG(주택도시보증공사) 보도자료", "HUG 보도자료(전세보증·분양보증 등)를 수집합니다.",
     collector.collect_hug_press_releases),
    ("policy_sh_collect_now", "🏘️ SH(서울주택도시공사) 보도자료", "SH 보도자료(공공주택 공급·정비사업 등)를 수집합니다.",
     collector.collect_sh_press_releases),
]

_POLICY_SOURCE_COUNT = 7


@st.fragment(run_every=2)
def _show_policy_collection_progress(run_id):
    entries = collector.get_policy_progress(run_id)
    if entries:
        st.dataframe(
            pd.DataFrame([
                {"수집처": e["source"], "조회": e["fetched"], "신규": e["inserted"], "중복": e["skipped"]}
                for e in entries
            ]),
            use_container_width=True, hide_index=True,
        )
    if collector.active_policy_run_id() == run_id:
        st.caption(f"🔄 진행 중... ({len(entries)}/{_POLICY_SOURCE_COUNT}곳 완료)")
    else:
        total_fetched = sum(e["fetched"] for e in entries)
        total_inserted = sum(e["inserted"] for e in entries)
        st.success(f"전체 완료 — {total_fetched:,}건 조회, 신규 {total_inserted:,}건")


@st.fragment(run_every=2)
def _show_naver_news_collection_progress(run_id):
    logs = [l for l in db.get_run_logs(limit=500) if l["run_id"] == run_id][::-1]
    if logs:
        lines = [f"{e['brand']}: {_format_entry_status(e)}" for e in logs]
        st.code("\n".join(lines), language=None, height=200)
    if collector.active_naver_news_run_id() == run_id:
        st.caption(f"🔄 진행 중... ({len(logs):,}건 완료)")
    else:
        ok_count = sum(1 for e in logs if e["ok"])
        st.success(f"수집 완료: {len(logs):,}건 실행, 성공 {ok_count:,}건")


def _render_naver_news_collection_tab():
    st.caption(
        "네이버 공식 뉴스 검색 API로 수집합니다. 키워드 관리의 키워드를 그대로 "
        "사용하며, 신규 게시물과 별도의 독립된 스케줄을 가집니다."
    )
    st.caption(
        "⚠️ URL은 채널과 무관하게 전체에서 중복 제거되므로, 구글/다음 채널에서 이미 "
        "수집된 기사와 동일한 URL은 네이버뉴스 탭에서 다시 수집되지 않습니다(반대 "
        "방향도 동일). 신규 건수가 0이어도 오류가 아닐 수 있습니다."
    )
    if not os.getenv("NAVER_CLIENT_ID") or not os.getenv("NAVER_CLIENT_SECRET"):
        st.warning(
            "⚠️ .env에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되어 있지 않습니다. "
            "네이버 개발자센터에서 애플리케이션을 등록해 값을 발급받은 뒤 .env에 "
            "추가해야 수집이 동작합니다."
        )

    st.subheader("⏰ 수집 스케줄")
    naver_news_sched_cfg = load_naver_news_collection_schedule()
    naver_news_times_text = st.text_input(
        "수집 시각 (/로 구분)", value="/".join(naver_news_sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="naver_news_sched_times_text",
    )
    if st.button("💾 저장", key="naver_news_sched_save"):
        tokens = [t.strip() for t in naver_news_times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_naver_news_collection_schedule({"times": seen})
            st.rerun()
    if naver_news_sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(naver_news_sched_cfg['times'])}")
    else:
        st.caption("등록된 수집 시각이 없습니다.")

    st.divider()
    running_naver_news_run_id = collector.active_naver_news_run_id()
    if running_naver_news_run_id is None:
        if st.button("🔄 지금 수집", type="primary", key="naver_news_collect_now"):
            started_run_id = collector.start_background_naver_news_collection(trigger="수동")
            if started_run_id:
                db.log_activity(st.session_state.get("_client_ip", ""), "설정 · 데이터 수집", "네이버뉴스 API 수집 실행")
                st.session_state["watched_naver_news_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 네이버뉴스 수집이 진행 중입니다.")
    else:
        st.info("🔄 수집이 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_naver_news_run_id"] = running_naver_news_run_id

    display_naver_news_run_id = running_naver_news_run_id or st.session_state.get("watched_naver_news_run_id")
    if display_naver_news_run_id:
        _show_naver_news_collection_progress(display_naver_news_run_id)

    st.divider()
    st.subheader("📜 수집 이력")
    naver_news_batches = db.get_run_batches(limit=50, channels=["네이버뉴스API"])
    if naver_news_batches:
        naver_news_batch_df = pd.DataFrame(naver_news_batches)[
            ["ran_at", "trigger", "brands", "combinations", "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(naver_news_batch_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 수집 이력이 없습니다.")


def _render_policy_collection_tab():
    st.caption(
        "국토교통부·한국부동산원·LH·서울시·HF·HUG·SH 7곳 보도자료를 수집합니다. "
        "신규 게시물과 별도의 독립된 스케줄을 가집니다."
    )
    st.subheader("⏰ 수집 스케줄")
    policy_sched_cfg = load_policy_collection_schedule()
    policy_times_text = st.text_input(
        "수집 시각 (/로 구분)", value="/".join(policy_sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="policy_sched_times_text",
    )
    if st.button("💾 저장", key="policy_sched_save"):
        tokens = [t.strip() for t in policy_times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_policy_collection_schedule({"times": seen})
            st.rerun()
    if policy_sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(policy_sched_cfg['times'])}")
    else:
        st.caption("등록된 수집 시각이 없습니다.")
        st.warning(
            "⚠️ 정책 데이터 자동 수집 시각이 설정되어 있지 않습니다. "
            "시각을 등록하기 전까지는 스케줄러가 자동으로 실행되지 않으니, "
            "위 시각을 등록하거나 아래 '지금 수집' 버튼으로 수동 수집하세요."
        )

    st.divider()

    running_policy_run_id = collector.active_policy_run_id()
    if running_policy_run_id is None:
        if st.button("🔄 7곳 전체 지금 수집", key="policy_collect_all_now", type="primary"):
            started_run_id = collector.start_background_policy_collection(days=30)
            if started_run_id:
                db.log_activity(st.session_state.get("_client_ip", ""), "설정 · 데이터 수집", "정책 전체 수집 실행")
                st.session_state["watched_policy_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 정책 수집이 진행 중입니다.")
    else:
        st.info("🔄 정책 수집이 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_policy_run_id"] = running_policy_run_id

    display_policy_run_id = running_policy_run_id or st.session_state.get("watched_policy_run_id")
    if display_policy_run_id:
        _show_policy_collection_progress(display_policy_run_id)

    with st.expander("소스별로 하나씩 수집하기"):
        for i, (key, title, caption, collect_fn) in enumerate(_POLICY_SOURCE_SECTIONS):
            st.markdown(f"#### {title}")
            st.caption(caption)
            if st.button("🔄 지금 수집", key=key):
                result = collect_fn(days=30)
                st.success(
                    f"{result['fetched']:,}건 조회 (신규 {result['inserted']:,}, "
                    f"중복 {result['skipped']:,})"
                )
            if i < len(_POLICY_SOURCE_SECTIONS) - 1:
                st.divider()

    st.divider()
    st.subheader("📜 수집 이력")
    policy_batches = db.get_policy_run_batches(limit=50)
    if policy_batches:
        policy_batch_df = pd.DataFrame(policy_batches)[
            ["ran_at", "trigger", "sources", "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(policy_batch_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 수집 이력이 없습니다.")


@st.fragment(run_every=2)
def _show_mk_news_collection_progress(run_id):
    logs = [l for l in db.get_run_logs(limit=500) if l["run_id"] == run_id][::-1]
    if logs:
        lines = [f"{e['brand']}: {_format_entry_status(e)}" for e in logs]
        st.code("\n".join(lines), language=None, height=200)
    if collector.active_mk_news_run_id() == run_id:
        st.caption(f"🔄 진행 중... ({len(logs):,}건 완료)")
    else:
        ok_count = sum(1 for e in logs if e["ok"])
        st.success(f"수집 완료: {len(logs):,}건 실행, 성공 {ok_count:,}건")


def _render_mk_news_collection_tab():
    st.caption(
        "매일경제 뉴스 검색 API(IP 화이트리스트 인증)로 수집합니다. 키워드 관리의 "
        "키워드를 그대로 사용하며, 다른 채널과 별도의 독립된 스케줄을 가집니다."
    )
    st.caption(
        "⚠️ 이 API는 원문 URL 패턴을 제공하지 않아 링크 없이 제목·본문만 저장됩니다. "
        "URL은 채널과 무관하게 전체에서 중복 제거되므로, 신규 건수가 0이어도 오류가 "
        "아닐 수 있습니다."
    )

    st.subheader("⏰ 수집 스케줄")
    mk_news_sched_cfg = load_mk_news_collection_schedule()
    mk_news_times_text = st.text_input(
        "수집 시각 (/로 구분)", value="/".join(mk_news_sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="mk_news_sched_times_text",
    )
    if st.button("💾 저장", key="mk_news_sched_save"):
        tokens = [t.strip() for t in mk_news_times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_mk_news_collection_schedule({"times": seen})
            st.rerun()
    if mk_news_sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(mk_news_sched_cfg['times'])}")
    else:
        st.caption("등록된 수집 시각이 없습니다.")

    st.divider()
    running_mk_news_run_id = collector.active_mk_news_run_id()
    if running_mk_news_run_id is None:
        if st.button("🔄 지금 수집", type="primary", key="mk_news_collect_now"):
            started_run_id = collector.start_background_mk_news_collection(trigger="수동")
            if started_run_id:
                db.log_activity(st.session_state.get("_client_ip", ""), "설정 · 데이터 수집", "매경 API 수집 실행")
                st.session_state["watched_mk_news_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 매경 API 수집이 진행 중입니다.")
    else:
        st.info("🔄 수집이 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_mk_news_run_id"] = running_mk_news_run_id

    display_mk_news_run_id = running_mk_news_run_id or st.session_state.get("watched_mk_news_run_id")
    if display_mk_news_run_id:
        _show_mk_news_collection_progress(display_mk_news_run_id)

    st.divider()
    st.subheader("📜 수집 이력")
    mk_news_batches = db.get_run_batches(limit=50, channels=["매경API"])
    if mk_news_batches:
        mk_news_batch_df = pd.DataFrame(mk_news_batches)[
            ["ran_at", "trigger", "brands", "combinations", "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(mk_news_batch_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 수집 이력이 없습니다.")


def _render_data_collection():
    _render_lazy_tabs(
        ["📰 신규 게시물", "📡 네이버뉴스 API", "🏛️ 정부 정책", "📈 매경 API"], "dc_tab",
        [_render_brand_collection_tab, _render_naver_news_collection_tab, _render_policy_collection_tab,
         _render_mk_news_collection_tab],
    )


# ── 데이터 관리(조회) ───────────────────────────────────────────────────────

_PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
_ROW_COL_RATIOS = [0.5, 1.0, 1.0, 0.7, 0.6, 0.6, 4.0, 0.6]
_ROW_HEADERS = ["수집일시", "게시일", "브랜드", "채널", "구분", "제목", ""]


def _paginate_df(df: pd.DataFrame, filter_sig: tuple, page_size: int, key_prefix: str):
    """조회 탭(브랜드/정책 공용) 페이지네이션 상태 관리. filter_sig(필터+표시개수 조합)가
    바뀌면 1페이지로 리셋하고, 그렇지 않으면 세션에 저장된 현재 페이지를 유지한다.
    key_prefix가 서로 다르면(예: "lookup" vs "policy_lookup") 세션 키가 겹치지 않는다.
    반환값: (현재 페이지의 df 슬라이스, 현재 페이지 번호, 전체 페이지 수)."""
    total = len(df)
    if st.session_state.get(f"{key_prefix}_filter_sig") != filter_sig:
        st.session_state[f"{key_prefix}_filter_sig"] = filter_sig
        st.session_state[f"{key_prefix}_page"] = 1

    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(st.session_state.get(f"{key_prefix}_page", 1), total_pages)
    st.session_state[f"{key_prefix}_page"] = page
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    return df.iloc[start:end], page, total_pages


def _render_pagination_controls(key_prefix: str, page: int, total_pages: int) -> None:
    """_paginate_df와 짝을 이루는 처음/이전/다음/끝 버튼 행. key_prefix로 세션 키를 구분한다."""
    pc1, pc2, pc3, pc4, pc5 = st.columns([1, 1, 2, 1, 1])
    if pc1.button("◀◀ 처음", disabled=page <= 1, key=f"{key_prefix}_first"):
        st.session_state[f"{key_prefix}_page"] = 1
        st.rerun()
    if pc2.button("◀ 이전", disabled=page <= 1, key=f"{key_prefix}_prev"):
        st.session_state[f"{key_prefix}_page"] -= 1
        st.rerun()
    pc3.markdown(f"<div style='text-align:center;padding-top:6px'>{page} / {total_pages} 페이지</div>", unsafe_allow_html=True)
    if pc4.button("다음 ▶", disabled=page >= total_pages, key=f"{key_prefix}_next"):
        st.session_state[f"{key_prefix}_page"] += 1
        st.rerun()
    if pc5.button("끝 ▶▶", disabled=page >= total_pages, key=f"{key_prefix}_last"):
        st.session_state[f"{key_prefix}_page"] = total_pages
        st.rerun()


def _escape_html_attr(text: str) -> str:
    """조회 목록의 제목(외부에서 크롤링한, 신뢰할 수 없는 텍스트)을 title="..." 같은 HTML
    속성 안에 넣기 전에 이스케이프한다. `&`를 가장 먼저 치환해야 뒤이어 만든 `&lt;` 등의
    엔티티가 다시 이스케이프되지 않는다. 큰따옴표를 이스케이프하지 않으면 제목에 `"`가
    포함된 기사가 속성값을 이탈해 임의 HTML/속성을 주입할 수 있었다."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _match_type(brand: str, search_term: str) -> str:
    if not search_term:
        return "미상"
    return "브랜드" if search_term == brand else "키워드"


@st.dialog("상세 정보", width="large")
def _show_mention_detail(row):
    st.subheader(row["제목"])
    st.write(
        f"브랜드: {row['브랜드']}  |  채널: {row['채널']}  |  "
        f"수집 키워드: {row['수집 키워드']} ({row['구분']})  |  출처: {row['출처']}"
    )
    st.write(f"수집일시: {row['수집일시']}  |  게시일: {row['게시일'] or '-'}")
    st.markdown(f"[원문 링크]({row['URL']})")
    st.divider()
    st.write(row["스니펫"] or "(스니펫 없음)")
    if row["본문"]:
        st.divider()
        st.markdown("**본문**")
        st.write(row["본문"])


def _render_brand_lookup_tab():
    st.subheader("🗃 수집 데이터 조회")

    brands = ["전체"] + [b["name"] for b in load_keywords()["brands"]]
    channels = ["전체", "네이버", "구글", "다음", "커뮤니티", "네이버뉴스API", "매경API"]

    col_brand, col_channel, col_size = st.columns(3)
    with col_brand:
        selected_brand = st.selectbox("브랜드", brands, key="lookup_brand")
    with col_channel:
        selected_channel = st.selectbox("채널", channels, key="lookup_channel")
    with col_size:
        page_size = st.selectbox("표시 개수", _PAGE_SIZE_OPTIONS, key="lookup_page_size")

    title_search = st.text_input("제목 검색", placeholder="검색어 입력...", key="lookup_title_search")

    default_range_start = date.today() - timedelta(days=6)
    default_range_end = date.today()
    col_collect_filter, col_collect_start, col_collect_end = st.columns(3)
    with col_collect_filter:
        filter_by_collected = st.checkbox("수집일로 필터링", key="lookup_filter_by_collected")
    with col_collect_start:
        collected_start = st.date_input(
            "수집일 시작", value=default_range_start,
            key="lookup_collected_start", disabled=not filter_by_collected,
        )
    with col_collect_end:
        collected_end = st.date_input(
            "수집일 종료", value=default_range_end,
            key="lookup_collected_end", disabled=not filter_by_collected,
        )

    mentions = db.get_mentions(
        brand="" if selected_brand == "전체" else selected_brand,
        channel="" if selected_channel == "전체" else selected_channel,
    )
    df = pd.DataFrame(
        mentions,
        columns=[
            "id", "collected_at", "brand", "channel", "search_term",
            "source_detail", "title", "url", "snippet", "posted_at", "content",
        ],
    ).rename(columns={
        "collected_at": "수집일시", "brand": "브랜드", "channel": "채널",
        "search_term": "수집 키워드", "source_detail": "출처", "title": "제목",
        "url": "URL", "snippet": "스니펫", "posted_at": "게시일", "content": "본문",
    })
    df["구분"] = [
        _match_type(brand, term) for brand, term in zip(df["브랜드"], df["수집 키워드"])
    ]

    if title_search:
        df = df[df["제목"].str.contains(title_search, case=False, na=False)]

    if filter_by_collected:
        collected_dates = df["수집일시"].str[:10]
        df = df[
            (collected_dates >= collected_start.isoformat())
            & (collected_dates <= collected_end.isoformat())
        ]

    total = len(df)
    st.markdown(f"#### 조회 결과 ({total:,}건)")

    filter_sig = (selected_brand, selected_channel, page_size, title_search,
                  filter_by_collected, collected_start, collected_end)
    page_df, page, total_pages = _paginate_df(df, filter_sig, page_size, "lookup")
    page_ids = [int(i) for i in page_df["id"].tolist()]

    page_sig = (filter_sig, page)
    if st.session_state.get("lookup_page_sig") != page_sig:
        st.session_state["lookup_page_sig"] = page_sig
        st.session_state["lookup_select_all"] = False

    if page_df.empty:
        st.caption("조회된 데이터가 없습니다.")
    else:
        header_cols = st.columns([0.5] + _ROW_COL_RATIOS[1:])
        select_all = header_cols[0].checkbox("", key="lookup_select_all", label_visibility="collapsed")
        if select_all != st.session_state.get("lookup_select_all_prev"):
            for row_id in page_ids:
                st.session_state[f"lookup_row_select_{row_id}"] = select_all
        st.session_state["lookup_select_all_prev"] = select_all
        for label, col in zip(_ROW_HEADERS, header_cols[1:]):
            col.markdown(f"**{label}**")

        for _, row in page_df.iterrows():
            row_id = int(row["id"])
            cols = st.columns(_ROW_COL_RATIOS)
            cols[0].checkbox("", key=f"lookup_row_select_{row_id}", label_visibility="collapsed")
            cols[1].markdown(str(row["수집일시"]))
            cols[2].markdown(str(row["게시일"]) if row["게시일"] else "-")
            cols[3].markdown(str(row["브랜드"]))
            cols[4].markdown(str(row["채널"]))
            cols[5].markdown(str(row["구분"]))
            title_text = _escape_html_attr(str(row["제목"]))
            cols[6].markdown(
                f'<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
                f'title="{title_text}">{title_text}</div>',
                unsafe_allow_html=True,
            )
            if cols[7].button("보기", key=f"lookup_view_{row_id}", use_container_width=True):
                _show_mention_detail(row)

    selected_ids = [
        row_id for row_id in page_ids
        if st.session_state.get(f"lookup_row_select_{row_id}", False)
    ]

    del_col, count_col = st.columns([1, 5])
    if del_col.button("🗑 선택 삭제", key="lookup_delete_button", disabled=not selected_ids):
        deleted = db.delete_mentions(selected_ids)
        cached_db.clear()
        db.log_activity(
            st.session_state.get("_client_ip", ""), "설정 · 데이터 관리", "뉴스 선택 삭제", f"{deleted}건",
        )
        st.success(f"{deleted:,}건 삭제했습니다.")
        st.rerun()
    count_col.caption(f"선택된 항목: {len(selected_ids):,}건")

    delete_all_confirm = st.checkbox(
        "⚠️ 전체 삭제에 동의합니다 (필터와 무관하게 모든 수집 데이터가 삭제됩니다)",
        key="lookup_delete_all_confirm",
    )
    if st.button("🗑️ 전체 삭제", key="lookup_delete_all_button", disabled=not delete_all_confirm):
        deleted = db.delete_all_mentions()
        cached_db.clear()
        db.log_activity(
            st.session_state.get("_client_ip", ""), "설정 · 데이터 관리", "뉴스 전체 삭제", f"{deleted}건",
        )
        st.success(f"전체 {deleted:,}건을 삭제했습니다.")
        st.rerun()

    st.divider()
    _render_pagination_controls("lookup", page, total_pages)


_POLICY_ROW_COL_RATIOS = [0.3, 0.8, 1.0, 1.0, 4.0, 0.8, 0.6]
_POLICY_ROW_HEADERS = ["수집처", "등록일", "분류", "제목", "조회수", ""]


@st.dialog("정책 상세 정보", width="large")
def _show_policy_event_detail(row):
    st.subheader(row["제목"])
    st.write(
        f"수집처: {row['수집처']}  |  분류: {row['분류']}  |  "
        f"등록일: {row['등록일']}  |  조회수: {row['조회수']}"
    )
    st.markdown(f"[원문 링크]({row['URL']})")


def _render_policy_lookup_tab():
    """정부 정책 탭 전용 필터+표+삭제 UI. policy_events는 브랜드/채널/게시일 개념이
    없어 _render_brand_lookup_tab과 컬럼 구성이 다르지만(등록일/분류/제목/조회수),
    페이지네이션은 _paginate_df/_render_pagination_controls를 공유해 브랜드 탭과
    동일한 처음/이전/다음/끝 방식으로 동작한다(연 단위 스케줄 수집 시 수천 건이
    한 번에 렌더링되는 것을 방지)."""
    departments = ["전체"] + sorted({e["department"] for e in db.get_policy_events() if e["department"]})
    col_dept, col_size = st.columns(2)
    with col_dept:
        selected_department = st.selectbox("분류", departments, key="policy_lookup_department")
    with col_size:
        page_size = st.selectbox("표시 개수", _PAGE_SIZE_OPTIONS, key="policy_lookup_page_size")
    title_search = st.text_input("제목 검색", placeholder="검색어 입력...", key="policy_lookup_title_search")

    default_range_start = date.today() - timedelta(days=29)
    default_range_end = date.today()
    col_date_filter, col_date_start, col_date_end = st.columns(3)
    with col_date_filter:
        filter_by_date = st.checkbox("등록일로 필터링", key="policy_lookup_filter_by_date")
    with col_date_start:
        date_start = st.date_input(
            "등록일 시작", value=default_range_start,
            key="policy_lookup_date_start", disabled=not filter_by_date,
        )
    with col_date_end:
        date_end = st.date_input(
            "등록일 종료", value=default_range_end,
            key="policy_lookup_date_end", disabled=not filter_by_date,
        )

    events = db.get_policy_events(
        department="" if selected_department == "전체" else selected_department,
    )
    df = pd.DataFrame(
        events,
        columns=["id", "source", "title", "url", "department", "announced_at", "view_count"],
    ).rename(columns={
        "source": "수집처", "title": "제목", "url": "URL", "department": "분류",
        "announced_at": "등록일", "view_count": "조회수",
    })

    if title_search:
        df = df[df["제목"].str.contains(title_search, case=False, na=False)]
    if filter_by_date:
        df = df[
            (df["등록일"] >= date_start.isoformat())
            & (df["등록일"] <= date_end.isoformat())
        ]

    total = len(df)
    st.markdown(f"#### 조회 결과 ({total:,}건)")

    filter_sig = (selected_department, page_size, title_search,
                  filter_by_date, date_start, date_end)
    page_df, page, total_pages = _paginate_df(df, filter_sig, page_size, "policy_lookup")
    page_ids = [int(i) for i in page_df["id"].tolist()]

    if page_df.empty:
        st.caption("조회된 데이터가 없습니다.")
    else:
        header_cols = st.columns([0.5] + _POLICY_ROW_COL_RATIOS[1:])
        for label, col in zip(_POLICY_ROW_HEADERS, header_cols[1:]):
            col.markdown(f"**{label}**")

        for _, row in page_df.iterrows():
            row_id = int(row["id"])
            cols = st.columns([0.5] + _POLICY_ROW_COL_RATIOS[1:])
            cols[0].checkbox("", key=f"policy_lookup_row_select_{row_id}", label_visibility="collapsed")
            cols[1].markdown(str(row["수집처"]))
            cols[2].markdown(str(row["등록일"]))
            cols[3].markdown(str(row["분류"]))
            title_text = _escape_html_attr(str(row["제목"]))
            cols[4].markdown(
                f'<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
                f'title="{title_text}">{title_text}</div>',
                unsafe_allow_html=True,
            )
            cols[5].markdown(str(row["조회수"]))
            if cols[6].button("보기", key=f"policy_lookup_view_{row_id}", use_container_width=True):
                _show_policy_event_detail(row)

    selected_ids = [
        row_id for row_id in page_ids
        if st.session_state.get(f"policy_lookup_row_select_{row_id}", False)
    ]

    del_col, count_col = st.columns([1, 5])
    if del_col.button("🗑 선택 삭제", key="policy_lookup_delete_button", disabled=not selected_ids):
        deleted = db.delete_policy_events(selected_ids)
        cached_db.clear()
        db.log_activity(
            st.session_state.get("_client_ip", ""), "설정 · 데이터 관리", "정책 선택 삭제", f"{deleted}건",
        )
        st.success(f"{deleted:,}건 삭제했습니다.")
        st.rerun()
    count_col.caption(f"선택된 항목: {len(selected_ids):,}건")

    delete_all_confirm = st.checkbox(
        "⚠️ 전체 삭제에 동의합니다 (필터와 무관하게 모든 정책 데이터가 삭제됩니다)",
        key="policy_lookup_delete_all_confirm",
    )
    if st.button(
        "🗑️ 전체 삭제", key="policy_lookup_delete_all_button", disabled=not delete_all_confirm,
    ):
        deleted = db.delete_all_policy_events()
        cached_db.clear()
        db.log_activity(
            st.session_state.get("_client_ip", ""), "설정 · 데이터 관리", "정책 전체 삭제", f"{deleted}건",
        )
        st.success(f"전체 {deleted:,}건을 삭제했습니다.")
        st.rerun()

    st.divider()
    _render_pagination_controls("policy_lookup", page, total_pages)


def _render_channel_visibility():
    st.subheader("🔎 화면 표시 채널")
    st.caption(
        "여기서 끈 채널은 오늘의 뉴스·부동산사 동향·브리핑·뉴스 검색·PDF 보고서 5개 화면에서 "
        "제외됩니다 (수집·저장은 그대로 계속되고, 이 설정 화면의 데이터 관리 조회에는 영향 없음)."
    )
    enabled = load_channel_visibility()
    cols = st.columns(len(ALL_MENTION_CHANNELS))
    selected = []
    for col, ch in zip(cols, ALL_MENTION_CHANNELS):
        if col.checkbox(ch, value=ch in enabled, key=f"chvis_{ch}"):
            selected.append(ch)
    if st.button("💾 저장", key="save_channel_visibility"):
        if not selected:
            st.error("최소 1개 채널은 선택되어 있어야 합니다.")
        else:
            save_channel_visibility(selected)
            st.rerun()
    st.divider()


def _render_data_management():
    _render_channel_visibility()
    _render_lazy_tabs(
        ["📰 신규 게시물", "🏛️ 정부 정책"], "dm_tab",
        [_render_brand_lookup_tab, _render_policy_lookup_tab],
    )


# ── 벡터 데이터 ────────────────────────────────────────────────────────────

_VECTORIZE_SOURCE_LABELS = {"mentions": "뉴스", "policy_events": "정책"}
VECTOR_BACKUP_DIR = ROOT / "data" / "vector_backups"


@st.fragment(run_every=2)
def _show_vectorize_progress(run_id):
    """2초마다 자동으로 새로 그려져서, 이 탭을 계속 보고 있어도 진행률이 실시간으로
    올라간다(run_every 없이는 사용자가 뭔가를 클릭해야만 갱신됨). 소스 하나가 최대
    200건까지 순차로 Gemini를 호출해서 몇 분씩 걸릴 수 있어, vector_run_logs에 행이
    쌓이는 소스 완료 시점 이전에도 건별 진행 상황(get_vectorize_progress)을 보여준다."""
    progress = vectorizer.get_vectorize_progress(run_id)
    for source, label in _VECTORIZE_SOURCE_LABELS.items():
        p = progress.get(source)
        if p and p["total"]:
            st.progress(p["done"] / p["total"], text=f"{label} 벡터화: {p['done']:,} / {p['total']:,}건")

    logs = [l for l in db.get_vector_run_logs(limit=50) if l["run_id"] == run_id]
    if logs:
        lines = [f"{e['source']}: 대상 {e['fetched']}건 · 성공 {e['inserted']}건 · 실패 {e['skipped']}건" for e in logs]
        st.code("\n".join(lines), language=None, height=100)
    if vectorizer.active_vectorize_run_id() == run_id:
        st.caption("🔄 벡터화 진행 중...")
    else:
        st.success("벡터화 완료")


def _render_vector_data_tab():
    st.caption(
        "수집된 뉴스(mentions)·정책(policy_events) 텍스트를 Gemini 임베딩으로 벡터화해 DB와 "
        "sqlite-vec 색인(mention_vectors/policy_vectors)에 저장합니다. AI AGENT가 질문을 받으면 "
        "이 색인에서 유사도가 가까운 문서를 찾아 답변 근거로 사용합니다."
    )
    if not vectorizer.has_api_keys():
        st.warning("⚠️ .env에 GEMINI_API_KEYS가 설정되어 있지 않아 벡터화를 실행할 수 없습니다.")

    mentions_pending = db.count_mentions_without_embedding()
    policy_pending = db.count_policy_events_without_embedding()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("뉴스 벡터화 대기", f"{mentions_pending:,}건", f"전체 {db.count_mentions():,}건 중")
    with c2:
        st.metric("정책 벡터화 대기", f"{policy_pending:,}건", f"전체 {db.count_policy_events():,}건 중")
    with c3:
        st.metric("뉴스 색인 완료", f"{db.count_mention_vector_index():,}건")
    with c4:
        st.metric("정책 색인 완료", f"{db.count_policy_vector_index():,}건")

    st.divider()
    st.subheader("⏰ 벡터화 스케줄")
    vector_sched_cfg = load_vector_collection_schedule()
    vector_times_text = st.text_input(
        "벡터화 시각 (/로 구분)", value="/".join(vector_sched_cfg["times"]),
        placeholder="예: 09:00/13:00/17:00", key="vector_sched_times_text",
    )
    if st.button("💾 저장", key="vector_sched_save"):
        tokens = [t.strip() for t in vector_times_text.split("/") if t.strip()]
        invalid = [t for t in tokens if not _TIME_RE.match(t)]
        if invalid:
            st.error(f"HH:MM 형식이 아닌 시각이 있습니다: {', '.join(invalid)}")
        else:
            seen = []
            for t in tokens:
                if t not in seen:
                    seen.append(t)
            save_vector_collection_schedule({"times": seen})
            st.rerun()
    if vector_sched_cfg["times"]:
        st.caption(f"등록된 시각: {', '.join(vector_sched_cfg['times'])}")
    else:
        st.caption("등록된 벡터화 시각이 없습니다 — 아래 '벡터화 진행' 버튼으로 수동 실행만 가능합니다.")

    st.divider()
    running_run_id = vectorizer.active_vectorize_run_id()
    if running_run_id is None:
        limit_per_source = st.number_input(
            "소스당 처리 건수", min_value=1, max_value=20000,
            value=max(mentions_pending, policy_pending, 1), step=100, key="vectorize_limit_per_source",
            help="뉴스·정책 각각 이 건수만큼 처리합니다. 대기 건수보다 크게 잡으면 남은 건 전부 처리됩니다.",
        )
        if st.button("🧬 벡터화 진행", type="primary", key="vectorize_now", disabled=not vectorizer.has_api_keys()):
            started_run_id = vectorizer.start_background_vectorize(
                trigger="수동", limit_per_source=int(limit_per_source),
            )
            if started_run_id:
                db.log_activity(
                    st.session_state.get("_client_ip", ""), "설정 · 벡터 데이터", "벡터화 실행", started_run_id,
                )
                st.session_state["watched_vectorize_run_id"] = started_run_id
                st.rerun()
            else:
                st.warning("이미 다른 벡터화가 진행 중입니다.")
    else:
        st.info("🔄 벡터화가 진행 중입니다. 페이지를 벗어나거나 새로고침해도 계속 진행됩니다.")
        st.session_state["watched_vectorize_run_id"] = running_run_id

    display_run_id = running_run_id or st.session_state.get("watched_vectorize_run_id")
    if display_run_id:
        _show_vectorize_progress(display_run_id)

    st.divider()
    st.subheader("📜 벡터화 이력")
    vector_batches = db.get_vector_run_logs(limit=50)
    if vector_batches:
        vector_df = pd.DataFrame(vector_batches)[
            ["ran_at", "trigger", "source", "fetched", "inserted", "skipped", "ok", "message"]
        ]
        st.dataframe(vector_df, use_container_width=True, hide_index=True)
    else:
        st.caption("아직 벡터화 이력이 없습니다.")

    st.divider()
    _render_vector_backup_restore()


def _format_vector_restore_result(result: dict) -> str:
    return (
        f"복구 완료 — 뉴스 {result['mentions_restored']:,}건 반영"
        f"(이미 있던 값 {result['mentions_already_present']:,}건, "
        f"url을 현재 DB에서 못 찾음 {result['mentions_not_found']:,}건), "
        f"정책 {result['policy_restored']:,}건 반영"
        f"(이미 있던 값 {result['policy_already_present']:,}건, "
        f"url을 현재 DB에서 못 찾음 {result['policy_not_found']:,}건) · "
        f"색인 재생성 {result['index_synced']['mentions']:,}/{result['index_synced']['policy_events']:,}건"
    )


def _run_vector_restore_with_status(backup: dict) -> dict:
    """복구는 보통 몇 초 안에 끝나지만, 그 몇 초 동안 화면이 멈춘 것처럼 보이지 않게
    st.status()로 단계(뉴스 복구 → 정책 복구 → 색인 재생성)를 실시간으로 보여준다."""
    with st.status("벡터 백업 복구 시작...", expanded=True) as status:
        mention_rows = backup.get("mentions", [])
        status.update(label=f"뉴스 임베딩 복구 중... ({len(mention_rows):,}건)")
        mention_result = db.restore_mention_embeddings_by_url(mention_rows)
        st.write(
            f"✅ 뉴스: {mention_result['restored']:,}건 반영 · "
            f"이미 있던 값 {mention_result['already_present']:,}건 · "
            f"못 찾음 {mention_result['not_found']:,}건"
        )

        policy_rows = backup.get("policy_events", [])
        status.update(label=f"정책 임베딩 복구 중... ({len(policy_rows):,}건)")
        policy_result = db.restore_policy_event_embeddings_by_url(policy_rows)
        st.write(
            f"✅ 정책: {policy_result['restored']:,}건 반영 · "
            f"이미 있던 값 {policy_result['already_present']:,}건 · "
            f"못 찾음 {policy_result['not_found']:,}건"
        )

        status.update(label="벡터 색인(sqlite-vec) 재생성 중...")
        index_result = vectorizer.sync_vector_index()
        st.write(f"✅ 색인 재생성: 뉴스 {index_result['mentions']:,}건 · 정책 {index_result['policy_events']:,}건")

        status.update(label="복구 완료", state="complete")

    return {
        "mentions_restored": mention_result["restored"],
        "mentions_already_present": mention_result["already_present"],
        "mentions_not_found": mention_result["not_found"],
        "policy_restored": policy_result["restored"],
        "policy_already_present": policy_result["already_present"],
        "policy_not_found": policy_result["not_found"],
        "index_synced": index_result,
    }


def _render_vector_backup_restore():
    st.subheader("💾 벡터 백업 / 복구")
    st.caption(
        "sqlite-vec 색인(mention_vectors/policy_vectors)은 mentions.embedding/"
        "policy_events.embedding 값으로부터 재생성 가능한 파생 데이터라, 여기서는 그 "
        "원본 임베딩 값(url 키)만 파일로 백업합니다. DB 손상 등으로 색인이나 임베딩이 "
        "날아갔을 때 Gemini API를 다시 호출하지 않고도 복구할 수 있습니다."
    )

    col_backup, col_rebuild = st.columns(2)
    with col_backup:
        if st.button("📦 지금 벡터 백업 만들기", key="vector_backup_create"):
            backup = vectorizer.export_vector_backup()
            VECTOR_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"vector_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            (VECTOR_BACKUP_DIR / fname).write_text(
                json.dumps(backup, ensure_ascii=False), encoding="utf-8",
            )
            db.log_activity(
                st.session_state.get("_client_ip", ""), "설정 · 벡터 데이터", "벡터 백업 생성", fname,
            )
            st.session_state["_vector_backup_just_created"] = fname
            st.success(
                f"백업 완료: 뉴스 {len(backup['mentions']):,}건 · 정책 {len(backup['policy_events']):,}건 "
                f"→ {fname}"
            )
            st.rerun()
    with col_rebuild:
        if st.button("🔁 현재 DB 임베딩으로 색인 재생성", key="vector_index_rebuild"):
            result = vectorizer.sync_vector_index()
            db.log_activity(
                st.session_state.get("_client_ip", ""), "설정 · 벡터 데이터", "벡터 색인 재생성",
                f"뉴스 {result['mentions']}건, 정책 {result['policy_events']}건",
            )
            st.success(f"색인 재생성 완료: 뉴스 {result['mentions']:,}건 · 정책 {result['policy_events']:,}건 반영")

    backup_files = sorted(VECTOR_BACKUP_DIR.glob("vector_backup_*.json"), reverse=True) if VECTOR_BACKUP_DIR.exists() else []
    if backup_files:
        st.caption(f"서버에 저장된 백업 {len(backup_files)}개 (최신순)")
        for f in backup_files[:10]:
            size_kb = f.stat().st_size / 1024
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.caption(f"📄 {f.name} · {size_kb:,.0f} KB")
            with c2:
                st.download_button(
                    "다운로드", data=f.read_bytes(), file_name=f.name, mime="application/json",
                    key=f"vector_backup_dl_{f.name}",
                )
            with c3:
                if st.button("♻️ 복구", key=f"vector_backup_restore_{f.name}"):
                    backup = json.loads(f.read_text(encoding="utf-8"))
                    result = _run_vector_restore_with_status(backup)
                    db.log_activity(
                        st.session_state.get("_client_ip", ""), "설정 · 벡터 데이터", "벡터 백업 복구", f.name,
                    )
                    st.success(_format_vector_restore_result(result))
    else:
        st.caption("아직 생성된 백업이 없습니다.")

    st.divider()
    st.markdown("**파일에서 복구**")
    uploaded = st.file_uploader("백업 JSON 파일 업로드", type="json", key="vector_backup_upload")
    if uploaded is not None and st.button("📥 업로드한 파일로 복구", key="vector_backup_restore_run"):
        try:
            backup = json.loads(uploaded.getvalue().decode("utf-8"))
        except Exception:
            st.error("올바른 JSON 파일이 아닙니다.")
        else:
            result = _run_vector_restore_with_status(backup)
            db.log_activity(
                st.session_state.get("_client_ip", ""), "설정 · 벡터 데이터", "벡터 백업 복구", uploaded.name,
            )
            st.success(_format_vector_restore_result(result))


# ── 로그 ──────────────────────────────────────────────────────────────────

_ACTIVITY_LOG_FETCH_LIMIT = 5000


def _render_activity_log_tab():
    st.caption("전체 화면에서 발생한 접속 IP·행위 기록입니다 — 페이지 방문/검색/AI 채팅/PDF 생성/관리 작업.")

    col_ip, col_search, col_size = st.columns([1, 2, 1])
    with col_ip:
        ips = db.distinct_activity_ips()
        picked_ip = st.selectbox("IP 필터", ["전체"] + ips, key="activity_log_ip_filter")
    with col_search:
        search_text = st.text_input(
            "검색어 (페이지/행위/내용)", key="activity_log_search", placeholder="예: PDF, 검색어, IP 등",
        )
    with col_size:
        page_size = st.selectbox("표시 개수", _PAGE_SIZE_OPTIONS, key="activity_log_page_size")

    logs = db.get_activity_log(
        limit=_ACTIVITY_LOG_FETCH_LIMIT, ip="" if picked_ip == "전체" else picked_ip,
    )
    if search_text:
        needle = search_text.lower()
        logs = [
            l for l in logs
            if needle in f"{l['page']} {l['action']} {l['detail']} {l['ip']}".lower()
        ]
    st.caption(f"총 {db.count_activity_log():,}건 중 조건에 맞는 {len(logs):,}건")

    if not logs:
        st.caption("조건에 맞는 로그가 없습니다.")
        return

    log_df = pd.DataFrame(logs)[["ts", "ip", "page", "action", "detail"]]
    filter_sig = (picked_ip, search_text, page_size)
    page_df, page, total_pages = _paginate_df(log_df, filter_sig, page_size, "activity_log")
    st.dataframe(page_df, use_container_width=True, hide_index=True, height=min(560, 60 + 35 * len(page_df)))
    _render_pagination_controls("activity_log", page, total_pages)


# ── API 사용량 ────────────────────────────────────────────────────────────

_API_USAGE_FEATURE_LABELS = {
    "summarizer": "📄 기사 요약(PDF)",
    "agent_chat": "🤖 AI AGENT 대화",
    "vectorizer": "🧬 벡터화(임베딩)",
}
# Gemini 2.5 Flash 공개 요금(2026-08 기준, USD/100만 토큰) 추정치 — 실제 청구 금액과
# 다를 수 있다. 요금이 바뀌면 이 두 값만 갱신하면 된다.
_PRICE_PER_1M_INPUT_USD = 0.30
_PRICE_PER_1M_OUTPUT_USD = 2.50


def _estimate_cost_usd(prompt_tokens: int, output_tokens: int) -> float:
    return (
        (prompt_tokens / 1_000_000) * _PRICE_PER_1M_INPUT_USD
        + (output_tokens / 1_000_000) * _PRICE_PER_1M_OUTPUT_USD
    )


def _render_api_usage_tab():
    st.caption(
        "Gemini API 호출량과 추정 비용입니다. 실패한 호출도 건수에는 포함되지만 토큰은 "
        "0으로 기록됩니다. 비용은 공개 요금 기준 추정치이며 실제 청구 금액과 다를 수 있습니다."
    )
    days = st.selectbox("조회 기간(일)", [7, 30, 90], index=1, key="api_usage_days")

    summary = db.get_api_usage_summary(days=days)
    total_calls = sum(v["calls"] for v in summary.values())
    total_failed = sum(v["failed"] for v in summary.values())
    total_prompt = sum(v["prompt_tokens"] for v in summary.values())
    total_output = sum(v["output_tokens"] for v in summary.values())
    total_cost = _estimate_cost_usd(total_prompt, total_output)

    theme.metric_row([
        {"icon": "📞", "value": f"{total_calls:,}", "label": f"최근 {days}일 호출"},
        {"icon": "❌", "value": f"{total_failed:,}", "label": "실패 건수"},
        {"icon": "🔢", "value": f"{(total_prompt + total_output):,}", "label": "총 토큰"},
        {"icon": "💵", "value": f"${total_cost:,.2f}", "label": "추정 비용(USD)"},
    ])

    if not summary:
        st.caption("아직 기록된 API 호출이 없습니다.")
        return

    st.divider()
    st.subheader("기능별 사용량")
    rows = []
    for feature, v in summary.items():
        cost = _estimate_cost_usd(v["prompt_tokens"], v["output_tokens"])
        rows.append({
            "기능": _API_USAGE_FEATURE_LABELS.get(feature, feature),
            "호출 수": v["calls"], "실패": v["failed"],
            "입력 토큰": v["prompt_tokens"], "출력 토큰": v["output_tokens"],
            "추정 비용(USD)": round(cost, 4),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    daily = db.get_api_usage_daily(days=days)
    if daily:
        st.divider()
        st.subheader("📈 일자별 호출 추이")
        theme.bar_chart({d["date"]: d["calls"] for d in daily}, height=200)


# ── 메인 진입점 ────────────────────────────────────────────────────────────

def render():
    st.title("⚙️ 설정")
    _render_lazy_tabs(
        ["🔐 접근 제어", "🔄 데이터 수집", "🗃 데이터 관리", "🧬 벡터 데이터", "💳 API 사용량", "📋 로그", "🚀 배포"],
        "main_tab",
        [_render_access_control, _render_data_collection, _render_data_management,
         _render_vector_data_tab, _render_api_usage_tab, _render_activity_log_tab, _render_deploy],
    )
