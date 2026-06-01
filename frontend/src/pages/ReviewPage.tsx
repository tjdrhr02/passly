import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token') || ''}` })

// ─── 타입 정의 ────────────────────────────────────────────────────────────────

interface SessionListItem {
  session_id: string
  certification_name: string
  exam_mode: string
  total_questions: number
  correct_count: number
  score_percent: number
  started_at: string
  completed_at: string | null
}

interface ChoiceInAttempt {
  id: string
  choice_label: string
  choice_text: string
  is_correct: boolean
}

interface AttemptDetail {
  attempt_id: string
  question_id: string
  question_text: string
  question_type: string
  selected_choice_ids: string[]
  is_correct: boolean
  choices: ChoiceInAttempt[]
  explanation_text: string | null
}

interface SessionAttemptsResponse {
  session_id: string
  certification_name: string
  exam_mode: string
  attempts: AttemptDetail[]
  total_questions: number
  correct_count: number
}

interface SuccessResponse<T> {
  data: T
  message: string
}

// ─── 문제 카드 ────────────────────────────────────────────────────────────────

function AttemptCard({ attempt }: { attempt: AttemptDetail }) {
  const [showExplanation, setShowExplanation] = useState(false)

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-3">
      <div className="flex items-start gap-2 mb-3">
        <span
          className={`inline-block text-xs font-semibold px-2 py-0.5 rounded shrink-0 ${
            attempt.is_correct ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}
        >
          {attempt.is_correct ? '정답' : '오답'}
        </span>
        <p className="text-sm text-gray-800 flex-1">{attempt.question_text}</p>
      </div>

      <ul className="space-y-1 mb-3">
        {attempt.choices.map((choice) => {
          const isSelected = attempt.selected_choice_ids.includes(choice.id)
          let itemClass = 'text-gray-700 bg-gray-50'
          if (choice.is_correct) itemClass = 'text-green-700 bg-green-50 font-semibold'
          else if (isSelected && !choice.is_correct) itemClass = 'text-red-700 bg-red-50'

          return (
            <li
              key={choice.id}
              className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm ${itemClass}`}
            >
              <span className="w-5 shrink-0 font-medium">{choice.choice_label}.</span>
              <span className="flex-1">{choice.choice_text}</span>
              {isSelected && (
                <span className="ml-auto text-xs opacity-70">내 선택</span>
              )}
            </li>
          )
        })}
      </ul>

      {attempt.explanation_text && (
        <div>
          <button
            onClick={() => setShowExplanation((v) => !v)}
            className="text-xs text-blue-600 hover:underline"
          >
            {showExplanation ? '해설 닫기' : '해설 보기'}
          </button>
          {showExplanation && (
            <p className="mt-2 text-xs text-gray-600 bg-blue-50 rounded p-3 leading-relaxed">
              {attempt.explanation_text}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── 세션 행 (아코디언) ───────────────────────────────────────────────────────

function SessionRow({ session }: { session: SessionListItem }) {
  const [open, setOpen] = useState(false)
  const [wrongOnly, setWrongOnly] = useState(false)
  const [attemptsData, setAttemptsData] = useState<SessionAttemptsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const fetchAttempts = async (sessionId: string, wrongOnlyFlag: boolean) => {
    setLoading(true)
    setFetchError(null)
    try {
      const path = wrongOnlyFlag
        ? `${API_BASE}/api/exam-sessions/${sessionId}/wrong-attempts`
        : `${API_BASE}/api/exam-sessions/${sessionId}/attempts`
      const res = await fetch(path, { headers: authHeader() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json: SuccessResponse<SessionAttemptsResponse> = await res.json()
      setAttemptsData(json.data)
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : '불러오기 실패')
    } finally {
      setLoading(false)
    }
  }

  const handleRowClick = () => {
    if (!open) {
      setOpen(true)
      fetchAttempts(session.session_id, wrongOnly)
    } else {
      setOpen(false)
    }
  }

  const handleWrongOnlyToggle = () => {
    const next = !wrongOnly
    setWrongOnly(next)
    fetchAttempts(session.session_id, next)
  }

  return (
    <div className="border border-gray-200 rounded-lg mb-2 overflow-hidden">
      {/* 헤더 행 */}
      <button
        onClick={handleRowClick}
        className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
      >
        <span className="text-sm text-gray-500 w-36 shrink-0">
          {new Date(session.started_at).toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
        <span className="flex-1 text-sm font-medium text-gray-800 truncate">
          {session.certification_name}
        </span>
        <span className="text-sm text-gray-600 w-16 text-center">
          {session.score_percent.toFixed(1)}%
        </span>
        <span className="text-sm text-gray-500 w-16 text-center">
          {session.correct_count}/{session.total_questions}
        </span>
        <span className="text-gray-400 text-xs ml-2">{open ? '▲' : '▼'}</span>
      </button>

      {/* 아코디언 콘텐츠 */}
      {open && (
        <div className="border-t border-gray-200 px-4 py-4">
          {/* 오답만 보기 토글 */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm text-gray-700">오답만 보기</span>
            <button
              onClick={handleWrongOnlyToggle}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                wrongOnly ? 'bg-blue-600' : 'bg-gray-300'
              }`}
              aria-pressed={wrongOnly}
            >
              <span
                className={`inline-block h-3 w-3 transform rounded-full bg-white shadow transition-transform ${
                  wrongOnly ? 'translate-x-5' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {loading && (
            <p className="text-sm text-gray-400 py-4 text-center">불러오는 중...</p>
          )}
          {fetchError && (
            <p className="text-sm text-red-500 py-4 text-center">오류: {fetchError}</p>
          )}
          {attemptsData && !loading && (
            <>
              {attemptsData.attempts.length === 0 ? (
                <p className="text-sm text-gray-400 py-4 text-center">
                  {wrongOnly ? '오답이 없습니다.' : '풀이 기록이 없습니다.'}
                </p>
              ) : (
                attemptsData.attempts.map((attempt) => (
                  <AttemptCard key={attempt.attempt_id} attempt={attempt} />
                ))
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── 메인 페이지 ──────────────────────────────────────────────────────────────

const ReviewPage = () => {
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState<string | null>(null)

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/exam-sessions`, {
          headers: authHeader(),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json: SuccessResponse<{ sessions: SessionListItem[]; total: number }> =
          await res.json()
        setSessions(json.data.sessions)
      } catch (e) {
        setPageError(e instanceof Error ? e.message : '불러오기 실패')
      } finally {
        setLoading(false)
      }
    }

    fetchSessions()
  }, [])

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-semibold text-gray-900">오답 노트</h1>
      <p className="mt-1 mb-6 text-gray-500">시험 세션별 풀이 이력을 확인하세요.</p>

      {/* 테이블 헤더 */}
      <div className="flex items-center gap-4 px-4 py-2 bg-gray-50 rounded-t border border-b-0 border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wide">
        <span className="w-36 shrink-0">날짜</span>
        <span className="flex-1">자격증</span>
        <span className="w-16 text-center">점수</span>
        <span className="w-16 text-center">문제 수</span>
        <span className="w-6" />
      </div>

      {loading && (
        <div className="border border-gray-200 rounded-b px-4 py-8 text-center text-sm text-gray-400">
          불러오는 중...
        </div>
      )}

      {pageError && (
        <div className="border border-red-200 rounded-b px-4 py-8 text-center text-sm text-red-500">
          오류: {pageError}
        </div>
      )}

      {!loading && !pageError && sessions.length === 0 && (
        <div className="border border-gray-200 rounded-b px-4 py-8 text-center text-sm text-gray-400">
          시험 세션이 없습니다.
        </div>
      )}

      {!loading && !pageError && sessions.length > 0 && (
        <div className="border border-gray-200 rounded-b p-2">
          {sessions.map((session) => (
            <SessionRow key={session.session_id} session={session} />
          ))}
        </div>
      )}
    </div>
  )
}

export default ReviewPage
