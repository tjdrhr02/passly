#!/usr/bin/env python3
"""PreToolUse hook — impl 파일 쓰기 전 review-agent 완료 여부 확인.
review-agent 검토 미완료 상태에서 impl 파일(.py/.ts/.tsx/.sql) 수정 시도를 BLOCK한다.
"""
import sys
import json
import os
import re

IMPL_PATTERN = re.compile(r'\.(py|ts|tsx|sql)$')

# 프로젝트 루트: .claude/hooks/gate-review.py 기준 두 단계 위
_HOOKS_DIR  = os.path.dirname(os.path.abspath(__file__))
_CLAUDE_DIR = os.path.dirname(_HOOKS_DIR)
PROJECT_ROOT = os.path.dirname(_CLAUDE_DIR)
MARKER = os.path.join(PROJECT_ROOT, '.REVIEW_REQUIRED')


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    if not file_path or not IMPL_PATTERN.search(file_path):
        sys.exit(0)

    if not os.path.exists(MARKER):
        sys.exit(0)

    try:
        with open(MARKER) as f:
            pending = f.read().strip()
    except Exception:
        pending = '(파일 목록 없음)'

    print(
        f'\n{"━" * 50}\n'
        f'[BLOCKED] review-agent 검토 미완료\n'
        f'{"━" * 50}\n'
        f'다음 파일의 검토가 아직 완료되지 않았습니다:\n'
        f'{pending}\n\n'
        f'진행 방법:\n'
        f'  1. @review-agent 를 호출해서 PASS 받기\n'
        f'  2. PASS / CONDITIONAL PASS 확인 후\n'
        f'  3. rm {MARKER}\n'
        f'{"━" * 50}\n',
        file=sys.stderr
    )
    sys.exit(2)


if __name__ == '__main__':
    main()
