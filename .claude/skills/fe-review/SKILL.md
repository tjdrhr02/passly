---
name: fe-review
description: React 컴포넌트나 페이지를 작성하거나 검토할 때 사용. pre-component Hook 트리거 시, 또는 review-agent가 프론트엔드 코드를 검토할 때 호출.
version: 1.0.0
---

# Skill: React 컴포넌트 검토

## 사용 시점
- React 컴포넌트/페이지 작성/검토 시
- pre-component Hook이 이 파일을 지정했을 때
- review-agent가 프론트엔드 코드 검토 시

---

## 컴포넌트 설계 기준

### 1. 파일 구조
```
frontend/src/
├── pages/          # 라우트 페이지 컴포넌트
├── components/     # 재사용 컴포넌트
│   ├── exam/       # 시험 관련
│   ├── practice/   # 연습 관련
│   └── common/     # 공통 (Layout, Navbar 등)
├── hooks/          # 커스텀 훅
├── api/            # API 클라이언트 함수
└── types/          # TypeScript 타입 정의
```

### 2. 타입 정의 패턴
```typescript
// types/exam.types.ts
export interface ExamSession {
  id: string;
  certificationId: string;
  examMode: 'TIMED' | 'PRACTICE' | 'REVIEW';
  totalQuestions: number;
  correctCount: number;
  isCompleted: boolean;
  startedAt: string;
}

export interface Question {
  id: string;
  questionText: string;
  questionType: 'SINGLE' | 'MULTIPLE' | 'SCENARIO';
  difficulty: 'BASIC' | 'INTERMEDIATE' | 'ADVANCED';
  choices: Choice[];
}
```

### 3. API 클라이언트 분리
```typescript
// api/examApi.ts
const API_BASE = import.meta.env.VITE_API_URL;

export const examApi = {
  createSession: async (certificationId: string, mode: string) => {
    const res = await fetch(`${API_BASE}/api/exam-sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ certification_id: certificationId, exam_mode: mode })
    });
    if (!res.ok) throw new Error('Failed to create session');
    return res.json();
  }
};
```

### 4. 커스텀 훅 패턴
```typescript
// hooks/useExamSession.ts
export function useExamSession(sessionId: string) {
  const [session, setSession] = useState<ExamSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    examApi.getSession(sessionId)
      .then(setSession)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  return { session, loading, error };
}
```

---

## 체크리스트
- [ ] TypeScript any 사용 없음
- [ ] 타입이 types/ 폴더에 분리 정의되어 있음
- [ ] API 호출이 api/ 폴더로 분리되어 있음
- [ ] 컴포넌트가 단일 책임을 지키는가?
- [ ] 로딩/에러 상태가 처리되어 있는가?
- [ ] 환경변수가 import.meta.env.VITE_* 로 사용되는가?
- [ ] shadcn/ui 컴포넌트를 활용하고 있는가?
