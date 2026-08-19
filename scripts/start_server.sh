#!/usr/bin/env bash
set -eu
ROOT="${HANA_ROOT:-$HOME/hana_p}"
PORT="${HANA_PORT:-7000}"
cd "$ROOT"

# 기존 프로세스 종료 — 그냥 신호만 보내고 곧장 다음 단계로 넘어가면, 이전 프로세스가
# 아직 완전히 죽지 않은 채로 새 프로세스가 뜰 수 있다. 그러면 스케줄러 백그라운드
# 스레드가 두 프로세스에서 동시에 돌면서 같은 예정 시각의 배치(특히 벡터화처럼 쓰기가
# 많은 작업)를 중복 실행해 DB 쓰기가 몰리는 사고로 이어진 적이 있다(2026-08-18) — 포트가
# 실제로 비는 것을 확인할 때까지 기다린다.
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
else
  for pid in $(ss -tlnp 2>/dev/null | grep ":${PORT}" | sed -n 's/.*pid=\([0-9]*\).*/\1/p'); do
    kill -9 "$pid" 2>/dev/null || true
  done
fi
for _ in $(seq 1 20); do
  ss -tlnp 2>/dev/null | grep -q ":${PORT}" || break
  sleep 0.5
done

source "$ROOT/venv/bin/activate"

echo "START app.py (port $PORT)"
nohup python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.headless true \
  >>"$ROOT/streamlit.log" 2>&1 &

sleep 4
ss -tlnp 2>/dev/null | grep ":${PORT}" || { echo NOT_LISTENING; exit 1; }
echo "OK"
