#!/bin/bash
# Stop hook — .REVIEW_REQUIRED 마커가 있으면 터미널에 검토 요청 경고를 출력한다.

# 프로젝트 루트: .claude/hooks/run-review.sh 기준 두 단계 위
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MARKER="$PROJECT_ROOT/.REVIEW_REQUIRED"

[ ! -f "$MARKER" ] && exit 0

FILES=$(cat "$MARKER" | sort -u)

printf '\n\033[1;33m%s\033[0m\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf '\033[1;31m  ⚠  PASSLY REVIEW GATE — 검토 미완료\033[0m\n'
printf '\033[1;33m%s\033[0m\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf '\033[0;33m변경된 구현 파일:\033[0m\n'
echo "$FILES" | while read -r line; do
  [ -n "$line" ] && printf '  \033[0;36m%s\033[0m\n' "$line"
done
printf '\n\033[1;31m→ review-agent PASS 없이 다음 구현 진행 BLOCKED\033[0m\n'
printf '\033[0;37m검토 방법:\033[0m\n'
printf '  \033[0;32m@review-agent 구현 완료: [작업명]\033[0m\n'
printf '  \033[0;32m변경 파일: (위 목록)\033[0m\n'
printf '\033[0;37m검토 완료 후 게이트 해제:\033[0m \033[1;32mrm %s\033[0m\n' "$MARKER"
printf '\033[1;33m%s\033[0m\n\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
