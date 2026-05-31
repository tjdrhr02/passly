---
name: post-implementation
enabled: true
event: stop
pattern: .*
---

**[post-implementation]** 작업 완료 전 review-agent 호출 확인

> 참고: `.py/.ts/.tsx/.sql` 파일 수정 시 실제 자동화 훅이 `.REVIEW_REQUIRED` 마커를 생성하고,
> 세션 종료(Stop) 훅이 터미널에 경고를 출력한다. (`.claude/hooks/` 참조)
> 마커가 있는 상태에서 다음 구현 파일 수정 시도는 BLOCKED된다.

구현이 완료됐다면 아래 형식으로 review-agent를 호출해야 한다:

```
@review-agent
구현 완료: [작업명]
변경 파일:
  - [파일 경로]
관련 docs:
  - [참조 문서]
특이사항:
  - [있으면 기재, 없으면 "없음"]
```

결과별 처리:
- PASS → `rm .REVIEW_REQUIRED` 후 다음 작업 진행
- CONDITIONAL PASS → WARNING 기록, `rm .REVIEW_REQUIRED` 후 진행 가능
- FAIL → CRITICAL 수정 후 재호출 (마커 유지, 다음 Wave 진행 BLOCKED)
