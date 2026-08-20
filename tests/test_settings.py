from views.settings import _escape_html_attr, _sftp_upload_dir, _DATA_UPLOAD_SKIP


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
