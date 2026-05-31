#!/usr/bin/env python3
"""PostToolUse hook — impl 파일 수정 후 .REVIEW_REQUIRED 마커 생성.
.py/.ts/.tsx/.sql 파일이 Write/Edit 되면 review 게이트를 활성화한다.
"""
import sys
import json
import os
import re

IMPL_PATTERN = re.compile(r'\.(py|ts|tsx|sql)$')

# 프로젝트 루트: .claude/hooks/queue-review.py 기준 두 단계 위
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

    try:
        existing = set()
        if os.path.exists(MARKER):
            with open(MARKER) as f:
                existing = {line.strip() for line in f if line.strip()}
        existing.add(file_path)
        with open(MARKER, 'w') as f:
            f.write('\n'.join(sorted(existing)) + '\n')
    except Exception:
        pass


if __name__ == '__main__':
    main()
