from views.settings import _escape_html_attr, _filtered_env_content, _sftp_upload_dir, _DATA_UPLOAD_SKIP


class _FakeSFTP:
    """실제 SSH 없이 _sftp_upload_dir의 스킵 로직만 검증하기 위한 최소 스텁."""

    def __init__(self):
        self.put_calls = []
        self._known_dirs = set()

    def stat(self, path):
        if path not in self._known_dirs:
            raise OSError("no such directory")

    def mkdir(self, path):
        self._known_dirs.add(path)

    def put(self, local_path, remote_path):
        self.put_calls.append((local_path, remote_path))


def test_sftp_upload_dir_skips_stale_wal_shm_sidecars(tmp_path, monkeypatch):
    """로컬 개발용 data/news.db-wal·news.db-shm이 배포로 서버에 그대로 올라가면, 서버의
    실제 news.db와 짝이 안 맞는 WAL을 SQLite가 재생(replay)하면서 그 자리에서 DB를
    손상시킨다(2026-08-20 실측 재현: 배포 직후 서버 news.db가 다시 malformed됨) —
    news.db와 마찬가지로 -wal/-shm 사이드카도 반드시 스킵돼야 한다."""
    import views.settings as settings_module
    monkeypatch.setattr(settings_module, "ROOT", tmp_path)
    local_dir = tmp_path / "data"
    local_dir.mkdir()
    (local_dir / "news.db-wal").write_bytes(b"stale-wal-from-local-dev")
    (local_dir / "news.db-shm").write_bytes(b"stale-shm-from-local-dev")
    (local_dir / "collector_state.py").write_text("# not actually skip-listed, just uploadable")

    fake = _FakeSFTP()
    _sftp_upload_dir(fake, local_dir, "/remote/data", log=lambda *_: None, skip_names=_DATA_UPLOAD_SKIP)

    uploaded_names = {remote.rsplit("/", 1)[-1] for _, remote in fake.put_calls}
    assert "news.db-wal" not in uploaded_names
    assert "news.db-shm" not in uploaded_names
    assert "collector_state.py" in uploaded_names


def test_filtered_env_content_strips_deploy_keys(tmp_path):
    """배포 대상 서버 자신의 .env에는 DEPLOY_HOST 등이 없어야 한다 — 있으면 그 서버의
    설정 화면에도 "배포" 탭이 살아나 자기 자신에게 재배포를 실행할 수 있게 된다."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEYS=abc,def\n"
        "DEPLOY_HOST=192.168.10.169\n"
        "DEPLOY_USER=admin\n"
        "DEPLOY_PASS=secret\n"
        "NAVER_CLIENT_ID=xyz\n",
        encoding="utf-8",
    )

    result = _filtered_env_content(env_file)

    assert "GEMINI_API_KEYS=abc,def" in result
    assert "NAVER_CLIENT_ID=xyz" in result
    assert "DEPLOY_HOST" not in result
    assert "DEPLOY_USER" not in result
    assert "DEPLOY_PASS" not in result


def test_filtered_env_content_injects_site_url_from_deploy_host_and_port(tmp_path):
    """배포된 서버가 Teams 웹훅 카드 '더보기' 버튼에 쓸 자기 자신의 주소를 알 수 있도록,
    DEPLOY_HOST/DEPLOY_APP_PORT로 계산한 SITE_URL을 서버 .env에 대신 심어준다 —
    DEPLOY_HOST 자체는 배포 시 제외되므로(위 테스트) 서버는 이 값이 아니면 자기 주소를
    알 방법이 없다."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEYS=abc\nDEPLOY_HOST=192.168.10.169\nDEPLOY_APP_PORT=7000\n",
        encoding="utf-8",
    )

    result = _filtered_env_content(env_file)

    assert "SITE_URL=http://192.168.10.169:7000" in result


def test_filtered_env_content_defaults_site_url_port_when_deploy_app_port_missing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEPLOY_HOST=192.168.10.169\n", encoding="utf-8")

    result = _filtered_env_content(env_file)

    assert "SITE_URL=http://192.168.10.169:7000" in result


def test_filtered_env_content_does_not_inject_site_url_when_no_deploy_host(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEYS=abc\n", encoding="utf-8")

    result = _filtered_env_content(env_file)

    assert "SITE_URL" not in result


def test_filtered_env_content_keeps_lines_when_no_deploy_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEYS=abc\n", encoding="utf-8")

    result = _filtered_env_content(env_file)

    assert result == "GEMINI_API_KEYS=abc\n"


def test_escape_html_attr_escapes_double_quotes():
    assert _escape_html_attr('제목 "인용문" 포함') == "제목 &quot;인용문&quot; 포함"


def test_escape_html_attr_escapes_angle_brackets():
    assert _escape_html_attr("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_escape_html_attr_escapes_ampersand_before_other_entities():
    assert _escape_html_attr("A & B < C") == "A &amp; B &lt; C"


def test_escape_html_attr_escapes_raw_ampersand_in_entity_like_text():
    """입력은 이미 이스케이프된 HTML이 아니라 순수 텍스트로 취급한다 — '&lt;'라는 문자열
    자체가 원문에 있었다면 '&'만 이스케이프해서 '&amp;lt;'가 되는 게 맞다."""
    assert _escape_html_attr("&lt;") == "&amp;lt;"
