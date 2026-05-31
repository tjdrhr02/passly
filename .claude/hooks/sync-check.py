#!/usr/bin/env python3
"""Stop hook — AGENTS.md · skills SKILL.md · 실제 파일 3자 동기화 검사.

검사 항목:
  [STALE]   파일은 존재하나 AGENTS.md에 완료(✅) 미표시
  [MISSING] AGENTS.md에 완료 표시됐으나 파일이 없음
  [ORPHAN]  docs/ 에 있으나 AGENTS.md에 미등록 파일
  [SKILL]   skills SKILL.md가 참조하는 docs 문서가 AGENTS.md에 전혀 없음
"""
import os
import re
import glob

ROOT = '/Users/fairytale/dev/passly'
AGENTS_MD = os.path.join(ROOT, 'AGENTS.md')
DOCS_DIR  = os.path.join(ROOT, 'docs')
SKILLS_DIR = os.path.join(ROOT, '.claude', 'skills')

# ANSI 색상
RED    = '\033[0;31m'
YELLOW = '\033[1;33m'
CYAN   = '\033[0;36m'
GREEN  = '\033[0;32m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

# ── 1. AGENTS.md 파싱 ────────────────────────────────────────────────────────

def parse_agents_md():
    """Wave 섹션의 docs 항목을 파싱.
    반환: (entries, all_mentioned)
      entries: list of (doc_rel_path, is_marked_complete)
      all_mentioned: set of doc_rel_path — AGENTS.md 전체 본문에 언급된 경로 (괄호 표기 포함)
    """
    if not os.path.exists(AGENTS_MD):
        return [], set()

    with open(AGENTS_MD, encoding='utf-8') as f:
        content = f.read()

    # Wave 섹션만 추출 (## 8. 워크플로 이후 다음 ## 까지)
    wave_section = re.search(r'## 8\. 워크플로.*?(?=\n## |\Z)', content, re.DOTALL)

    entries = []
    if wave_section:
        wave_text = wave_section.group(0)
        for line in wave_text.splitlines():
            m = re.match(r'\s*-\s*\[([ xX])\]\s*(docs/\S+\.md)(.*)', line)
            if not m:
                continue
            checkbox = m.group(1).strip()
            doc_path = m.group(2).strip()
            rest     = m.group(3)
            is_marked = (checkbox.lower() == 'x') or ('✅' in rest)
            entries.append((doc_path, is_marked))

    # 전체 본문에서 숫자 접두어 docs 경로 수집 (Wave 5 괄호 표기 등 포함)
    all_mentioned = set(re.findall(r'docs/\d[\w\-]+\.md', content))

    return entries, all_mentioned

# ── 2. skills SKILL.md 파싱 ──────────────────────────────────────────────────

def parse_skill_doc_refs():
    """각 SKILL.md에서 docs/NN-*.md 참조를 추출 (숫자 접두어 파일만).
    반환: dict { skill_name: [doc_rel_path, ...] }
    """
    refs = {}
    pattern = os.path.join(SKILLS_DIR, '*', 'SKILL.md')
    for skill_path in glob.glob(pattern):
        skill_name = os.path.basename(os.path.dirname(skill_path))
        with open(skill_path, encoding='utf-8') as f:
            text = f.read()
        # 숫자로 시작하는 실제 문서명만 매칭 (docs/XX-name.md 같은 템플릿 제외)
        found = re.findall(r'docs/\d[\w\-]+\.md', text)
        if found:
            refs[skill_name] = list(dict.fromkeys(found))  # 중복 제거, 순서 유지
    return refs

# ── 3. docs/ 실제 파일 목록 ──────────────────────────────────────────────────

def actual_docs():
    if not os.path.isdir(DOCS_DIR):
        return set()
    return {
        'docs/' + f
        for f in os.listdir(DOCS_DIR)
        if f.endswith('.md')
    }

# ── 4. 검사 실행 ─────────────────────────────────────────────────────────────

def run_checks():
    issues = []

    agents_entries, agents_mentioned = parse_agents_md()
    skill_refs = parse_skill_doc_refs()
    on_disk    = actual_docs()

    agents_listed = {path for path, _ in agents_entries}
    # 체크리스트 항목 + 본문 inline 언급 모두 포함
    agents_known  = agents_listed | agents_mentioned

    # [STALE] 파일 존재 + 미완료 표시
    for doc_path, is_marked in agents_entries:
        full = os.path.join(ROOT, doc_path)
        if os.path.exists(full) and not is_marked:
            issues.append((
                'STALE',
                f'{doc_path} — 파일 존재하나 AGENTS.md에 완료(✅) 미표시'
            ))

    # [MISSING] 완료 표시 + 파일 없음
    for doc_path, is_marked in agents_entries:
        full = os.path.join(ROOT, doc_path)
        if is_marked and not os.path.exists(full):
            issues.append((
                'MISSING',
                f'{doc_path} — AGENTS.md 완료 표시됐으나 파일 없음'
            ))

    # [ORPHAN] docs/ 실제 파일이 AGENTS.md에 미등록
    for doc_path in sorted(on_disk):
        if doc_path not in agents_known:
            issues.append((
                'ORPHAN',
                f'{doc_path} — docs/ 에 존재하나 AGENTS.md 전체에 미언급'
            ))

    # [SKILL] 스킬이 참조하는 docs 문서가 AGENTS.md에 전혀 없는 경우만 경고
    # (Wave 5처럼 미래 문서는 AGENTS.md에 언급만 돼 있어도 정상)
    for skill_name, refs in skill_refs.items():
        for doc_path in refs:
            if doc_path not in agents_known:
                full = os.path.join(ROOT, doc_path)
                status = '파일 없음' if not os.path.exists(full) else '파일 존재'
                issues.append((
                    'SKILL',
                    f'[{skill_name}] SKILL.md 참조 → {doc_path} ({status}, AGENTS.md 미언급)'
                ))

    return issues

# ── 5. 출력 ──────────────────────────────────────────────────────────────────

def main():
    issues = run_checks()

    stale   = [m for t, m in issues if t == 'STALE']
    missing = [m for t, m in issues if t == 'MISSING']
    orphan  = [m for t, m in issues if t == 'ORPHAN']
    skill   = [m for t, m in issues if t == 'SKILL']

    if not issues:
        print(f'{GREEN}✓ 동기화 검사 통과 — AGENTS.md · skills · docs/ 일치{RESET}')
        return

    sep = '━' * 58
    print(f'\n{BOLD}{sep}{RESET}')
    print(f'{BOLD}  동기화 불일치 감지 (sync-check){RESET}')
    print(f'{BOLD}{sep}{RESET}')

    if stale:
        print(f'\n{YELLOW}[STALE] 파일 존재 → AGENTS.md 완료 미표시{RESET}')
        for m in stale:
            print(f'  {YELLOW}⚠{RESET}  {m}')
        print(f'  → AGENTS.md의 해당 항목에 ✅ (완료) 추가 필요')

    if missing:
        print(f'\n{RED}[MISSING] AGENTS.md 완료 표시 → 파일 없음{RESET}')
        for m in missing:
            print(f'  {RED}✗{RESET}  {m}')
        print(f'  → 문서를 생성하거나 AGENTS.md 표시를 수정 필요')

    if orphan:
        print(f'\n{CYAN}[ORPHAN] docs/ 파일 → AGENTS.md 미언급{RESET}')
        for m in orphan:
            print(f'  {CYAN}?{RESET}  {m}')
        print(f'  → AGENTS.md Wave 섹션에 항목 추가 필요')

    if skill:
        print(f'\n{CYAN}[SKILL] SKILL.md 참조 → AGENTS.md 미언급{RESET}')
        for m in skill:
            print(f'  {CYAN}~{RESET}  {m}')
        print(f'  → AGENTS.md에 해당 문서 항목 추가 필요')

    print(f'\n{BOLD}{sep}{RESET}\n')


if __name__ == '__main__':
    main()
