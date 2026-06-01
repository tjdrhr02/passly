import { useState, useEffect, useRef, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const authHeader = (): Record<string, string> => ({
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
  'Content-Type': 'application/json',
})

// ── 타입 정의 ────────────────────────────────────────────────────

interface Certification {
  id: string
  name: string
  vendor: string
  exam_code: string
}

interface ChoiceItem {
  id: string
  choice_label: string
  choice_text: string
  order_num: number
}

interface QuestionItem {
  id: string
  question_text: string
  question_type: string
  difficulty: string
  domain_name: string
  choices: ChoiceItem[]
}

interface SessionQuestionsData {
  session_id: string
  questions: QuestionItem[]
  total_questions: number
  time_limit_seconds: number | null
}

interface AnswerMap {
  [question_id: string]: string[]
}

interface DomainScore {
  domain_name: string
  total_questions: number
  correct_count: number
  score_percent: number
}

interface WrongAttempt {
  question_id: string
  question_text: string
  selected_choice_ids: string[]
  correct_choice_ids: string[]
  explanation_text: string | null
}

interface ExamResult {
  session_id: string
  total_questions: number
  correct_count: number
  score_percent: number
  domain_scores: DomainScore[]
  wrong_attempts: WrongAttempt[]
}

type Phase = 'setup' | 'exam' | 'result'

// ── 유틸 ─────────────────────────────────────────────────────────

const formatTime = (seconds: number): string => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── Setup 화면 ───────────────────────────────────────────────────

interface SetupProps {
  onStart: (certId: string, mode: string, count: number, timeLimit: number | null) => void
  loading: boolean
  error: string
}

const SetupPanel = ({ onStart, loading, error }: SetupProps) => {
  const [certifications, setCertifications] = useState<Certification[]>([])
  const [selectedCert, setSelectedCert] = useState<string>('')
  const [count, setCount] = useState<number>(20)
  const [timerOn, setTimerOn] = useState<boolean>(true)
  const [fetchError, setFetchError] = useState<string>('')

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/certifications`, { headers: authHeader() })
        if (!res.ok) throw new Error('자격증 목록을 불러오지 못했습니다.')
        const json = await res.json()
        const list: Certification[] = json.data ?? []
        setCertifications(list)
        if (list.length > 0) setSelectedCert(list[0].id)
      } catch (e) {
        setFetchError(e instanceof Error ? e.message : '오류가 발생했습니다.')
      }
    }
    load()
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCert) return
    // TIMED 모드: count * 90초 기본 타이머
    const timeLimit = timerOn ? count * 90 : null
    onStart(selectedCert, timerOn ? 'TIMED' : 'PRACTICE', count, timeLimit)
  }

  return (
    <div className="max-w-lg mx-auto mt-8 bg-white rounded-2xl shadow p-8">
      <h2 className="text-xl font-semibold text-gray-800 mb-6">시험 설정</h2>

      {(fetchError || error) && (
        <p className="mb-4 text-sm text-red-600">{fetchError || error}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* 자격증 선택 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">자격증</label>
          <select
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            value={selectedCert}
            onChange={(e) => setSelectedCert(e.target.value)}
            required
          >
            {certifications.length === 0 && <option value="">불러오는 중...</option>}
            {certifications.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.exam_code})
              </option>
            ))}
          </select>
        </div>

        {/* 문제 수 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">문제 수</label>
          <div className="flex gap-3">
            {[10, 20, 30, 50].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setCount(n)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  count === n
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:border-indigo-400'
                }`}
              >
                {n}문제
              </button>
            ))}
          </div>
        </div>

        {/* 타이머 ON/OFF */}
        <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50 border border-gray-200">
          <div>
            <p className="text-sm font-medium text-gray-800">타이머</p>
            <p className="text-xs text-gray-500">
              {timerOn ? `${formatTime(count * 90)} 제한 (문제당 90초)` : '제한 없음'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setTimerOn(!timerOn)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              timerOn ? 'bg-indigo-600' : 'bg-gray-300'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                timerOn ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>

        <button
          type="submit"
          disabled={loading || !selectedCert}
          className="w-full py-2.5 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '세션 생성 중...' : '시험 시작'}
        </button>
      </form>
    </div>
  )
}

// ── Exam 화면 ────────────────────────────────────────────────────

interface ExamPanelProps {
  sessionData: SessionQuestionsData
  onSubmit: (answers: AnswerMap, elapsed: number) => void
  submitting: boolean
}

const ExamPanel = ({ sessionData, onSubmit, submitting }: ExamPanelProps) => {
  const { questions, time_limit_seconds } = sessionData
  const [currentIdx, setCurrentIdx] = useState(0)
  const [answers, setAnswers] = useState<AnswerMap>({})
  const [timeLeft, setTimeLeft] = useState<number>(time_limit_seconds ?? 0)
  const startTimeRef = useRef<number>(Date.now())

  // 타이머
  useEffect(() => {
    if (!time_limit_seconds) return
    if (timeLeft <= 0) {
      handleSubmit()
      return
    }
    const id = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(id)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [time_limit_seconds])

  const handleSubmit = useCallback(() => {
    const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000)
    onSubmit(answers, elapsed)
  }, [answers, onSubmit])

  const current = questions[currentIdx]
  const isMultiple = current?.question_type === 'MULTIPLE'
  const selectedForCurrent = answers[current?.id] ?? []
  const answeredCount = Object.keys(answers).length

  const toggleChoice = (choiceId: string) => {
    setAnswers((prev) => {
      const current_q = current.id
      const existing = prev[current_q] ?? []
      if (isMultiple) {
        const next = existing.includes(choiceId)
          ? existing.filter((id) => id !== choiceId)
          : [...existing, choiceId]
        return { ...prev, [current_q]: next }
      } else {
        return { ...prev, [current_q]: [choiceId] }
      }
    })
  }

  const timerColor =
    time_limit_seconds && timeLeft < 60
      ? 'text-red-600'
      : time_limit_seconds && timeLeft < 300
      ? 'text-amber-600'
      : 'text-gray-700'

  return (
    <div className="flex gap-6 max-w-5xl mx-auto">
      {/* 메인 문제 영역 */}
      <div className="flex-1 min-w-0">
        {/* 문제 카드 */}
        <div className="bg-white rounded-2xl shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-semibold text-indigo-600">
              {currentIdx + 1} / {questions.length}
            </span>
            <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
              {current.domain_name}
            </span>
          </div>

          <p className="text-gray-900 font-medium leading-relaxed whitespace-pre-wrap mb-6">
            {current.question_text}
          </p>

          {isMultiple && (
            <p className="text-xs text-indigo-500 mb-3 font-medium">복수 선택 문제입니다.</p>
          )}

          <div className="space-y-2">
            {current.choices.map((choice) => {
              const selected = selectedForCurrent.includes(choice.id)
              return (
                <button
                  key={choice.id}
                  type="button"
                  onClick={() => toggleChoice(choice.id)}
                  className={`w-full text-left flex items-start gap-3 p-3 rounded-lg border text-sm transition-colors ${
                    selected
                      ? 'border-indigo-500 bg-indigo-50'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <span className="font-semibold text-gray-500 shrink-0 w-5">
                    {choice.choice_label}.
                  </span>
                  <span className="text-gray-800">{choice.choice_text}</span>
                </button>
              )
            })}
          </div>

          {/* 이전/다음 네비게이션 */}
          <div className="flex items-center justify-between mt-6">
            <button
              type="button"
              onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
              disabled={currentIdx === 0}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              이전
            </button>
            {currentIdx < questions.length - 1 ? (
              <button
                type="button"
                onClick={() => setCurrentIdx((i) => i + 1)}
                className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                다음
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? '채점 중...' : '시험 제출'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 사이드바 */}
      <div className="w-56 shrink-0">
        <div className="bg-white rounded-2xl shadow p-4 sticky top-6">
          {/* 타이머 */}
          {time_limit_seconds !== null && (
            <div className="mb-4 text-center">
              <p className="text-xs text-gray-500 mb-1">남은 시간</p>
              <p className={`text-2xl font-mono font-bold ${timerColor}`}>
                {formatTime(timeLeft)}
              </p>
            </div>
          )}

          {/* 진행 현황 */}
          <p className="text-xs text-gray-500 mb-2">
            답변 완료: {answeredCount} / {questions.length}
          </p>

          {/* 번호 그리드 */}
          <div className="grid grid-cols-5 gap-1 mb-4">
            {questions.map((q, i) => {
              const answered = q.id in answers
              const isCurrent = i === currentIdx
              return (
                <button
                  key={q.id}
                  type="button"
                  onClick={() => setCurrentIdx(i)}
                  className={`aspect-square rounded text-xs font-medium transition-colors ${
                    isCurrent
                      ? 'bg-indigo-600 text-white'
                      : answered
                      ? 'bg-indigo-100 text-indigo-700'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
                >
                  {i + 1}
                </button>
              )
            })}
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
          >
            {submitting ? '채점 중...' : '시험 제출'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Result 화면 ──────────────────────────────────────────────────

interface ResultPanelProps {
  result: ExamResult
  questions: QuestionItem[]
  onReset: () => void
}

const ResultPanel = ({ result, questions, onReset }: ResultPanelProps) => {
  const [expandedWrong, setExpandedWrong] = useState<Set<string>>(new Set())

  const toggleWrong = (qid: string) => {
    setExpandedWrong((prev) => {
      const next = new Set(prev)
      if (next.has(qid)) next.delete(qid)
      else next.add(qid)
      return next
    })
  }

  const qMap: Record<string, QuestionItem> = {}
  for (const q of questions) qMap[q.id] = q

  const scoreColor =
    result.score_percent >= 70
      ? 'text-green-600'
      : result.score_percent >= 50
      ? 'text-amber-600'
      : 'text-red-600'

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 정답률 카드 */}
      <div className="bg-white rounded-2xl shadow p-8 text-center">
        <p className="text-gray-500 text-sm mb-2">최종 점수</p>
        <p className={`text-6xl font-bold mb-1 ${scoreColor}`}>
          {result.score_percent}%
        </p>
        <p className="text-gray-500 text-sm">
          {result.correct_count} / {result.total_questions} 문제 정답
        </p>
        <button
          type="button"
          onClick={onReset}
          className="mt-6 px-6 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors font-medium"
        >
          다시 시험 보기
        </button>
      </div>

      {/* 영역별 성과 */}
      {result.domain_scores.length > 0 && (
        <div className="bg-white rounded-2xl shadow p-6">
          <h3 className="text-base font-semibold text-gray-800 mb-4">영역별 성과</h3>
          <div className="space-y-3">
            {result.domain_scores.map((ds) => (
              <div key={ds.domain_name}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-700 truncate max-w-xs">{ds.domain_name}</span>
                  <span className="text-gray-500 shrink-0 ml-2">
                    {ds.correct_count}/{ds.total_questions} ({ds.score_percent}%)
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all ${
                      ds.score_percent >= 70 ? 'bg-green-500' : ds.score_percent >= 50 ? 'bg-amber-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${ds.score_percent}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 오답 목록 */}
      {result.wrong_attempts.length > 0 && (
        <div className="bg-white rounded-2xl shadow p-6">
          <h3 className="text-base font-semibold text-gray-800 mb-4">
            오답 목록 ({result.wrong_attempts.length}문제)
          </h3>
          <div className="space-y-4">
            {result.wrong_attempts.map((wa, idx) => {
              const q = qMap[wa.question_id]
              const isExpanded = expandedWrong.has(wa.question_id)
              return (
                <div key={wa.question_id} className="border border-red-100 rounded-xl p-4">
                  <button
                    type="button"
                    onClick={() => toggleWrong(wa.question_id)}
                    className="w-full text-left"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium text-gray-800 line-clamp-2">
                        {idx + 1}. {wa.question_text}
                      </p>
                      <span className="text-xs text-gray-400 shrink-0 mt-0.5">
                        {isExpanded ? '접기 ▲' : '펼치기 ▼'}
                      </span>
                    </div>
                  </button>

                  {isExpanded && q && (
                    <div className="mt-3 space-y-1.5">
                      {q.choices.map((c) => {
                        const isCorrect = wa.correct_choice_ids.includes(c.id)
                        const isSelected = wa.selected_choice_ids.includes(c.id)
                        let style = 'border-gray-200 text-gray-600'
                        if (isCorrect) style = 'border-green-500 bg-green-50 text-green-800'
                        else if (isSelected) style = 'border-red-400 bg-red-50 text-red-700'
                        return (
                          <div
                            key={c.id}
                            className={`flex items-start gap-2 p-2 rounded-lg border text-xs ${style}`}
                          >
                            <span className="font-semibold shrink-0 w-4">{c.choice_label}.</span>
                            <span>{c.choice_text}</span>
                            {isCorrect && (
                              <span className="ml-auto shrink-0 font-semibold">정답</span>
                            )}
                            {isSelected && !isCorrect && (
                              <span className="ml-auto shrink-0 font-semibold">선택</span>
                            )}
                          </div>
                        )
                      })}
                      {wa.explanation_text && (
                        <div className="mt-2 p-3 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-800 whitespace-pre-wrap leading-relaxed">
                          <span className="font-semibold">해설: </span>
                          {wa.explanation_text}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── 메인 페이지 ──────────────────────────────────────────────────

const ExamPage = () => {
  const [phase, setPhase] = useState<Phase>('setup')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)

  const [sessionData, setSessionData] = useState<SessionQuestionsData | null>(null)
  const [sessionId, setSessionId] = useState<string>('')
  const [result, setResult] = useState<ExamResult | null>(null)

  const handleStart = async (
    certId: string,
    mode: string,
    count: number,
    timeLimit: number | null,
  ) => {
    setLoading(true)
    setError('')
    try {
      // 1. 세션 생성
      const createRes = await fetch(`${API_BASE}/api/exam-sessions`, {
        method: 'POST',
        headers: authHeader(),
        body: JSON.stringify({
          certification_id: certId,
          exam_mode: mode,
          question_count: count,
          time_limit_seconds: timeLimit,
        }),
      })
      if (!createRes.ok) {
        const json = await createRes.json()
        throw new Error(json.detail ?? '세션 생성에 실패했습니다.')
      }
      const createJson = await createRes.json()
      const sid: string = createJson.data.session_id
      setSessionId(sid)

      // 2. 문제 조회
      const qRes = await fetch(`${API_BASE}/api/exam-sessions/${sid}/questions`, {
        headers: authHeader(),
      })
      if (!qRes.ok) {
        const json = await qRes.json()
        throw new Error(json.detail ?? '문제를 불러오지 못했습니다.')
      }
      const qJson = await qRes.json()
      setSessionData(qJson.data)
      setPhase('exam')
    } catch (e) {
      setError(e instanceof Error ? e.message : '오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (answers: AnswerMap, elapsed: number) => {
    if (!sessionData) return
    setSubmitting(true)
    setError('')
    try {
      const submitRes = await fetch(
        `${API_BASE}/api/exam-sessions/${sessionId}/submit`,
        {
          method: 'POST',
          headers: authHeader(),
          body: JSON.stringify({
            session_id: sessionId,
            answers: Object.entries(answers).map(([qid, cids]) => ({
              question_id: qid,
              selected_choice_ids: cids,
            })),
            elapsed_seconds: elapsed,
          }),
        },
      )
      if (!submitRes.ok) {
        const json = await submitRes.json()
        throw new Error(json.detail ?? '제출에 실패했습니다.')
      }

      // 결과 조회
      const resultRes = await fetch(
        `${API_BASE}/api/exam-sessions/${sessionId}/result`,
        { headers: authHeader() },
      )
      if (!resultRes.ok) {
        const json = await resultRes.json()
        throw new Error(json.detail ?? '결과를 불러오지 못했습니다.')
      }
      const resultJson = await resultRes.json()
      setResult(resultJson.data)
      setPhase('result')
    } catch (e) {
      setError(e instanceof Error ? e.message : '오류가 발생했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReset = () => {
    setPhase('setup')
    setSessionData(null)
    setSessionId('')
    setResult(null)
    setError('')
  }

  return (
    <div className="p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6 max-w-5xl mx-auto">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">실전 시험</h1>
          <p className="mt-1 text-sm text-gray-500">
            타이머와 셔플이 적용된 실전 모드로 시험을 응시하세요.
          </p>
        </div>
        {phase !== 'setup' && (
          <button
            type="button"
            onClick={handleReset}
            className="text-sm text-indigo-600 hover:underline"
          >
            처음으로
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 max-w-5xl mx-auto">
          {error}
        </div>
      )}

      {phase === 'setup' && (
        <SetupPanel onStart={handleStart} loading={loading} error={error} />
      )}

      {phase === 'exam' && sessionData && (
        <ExamPanel
          sessionData={sessionData}
          onSubmit={handleSubmit}
          submitting={submitting}
        />
      )}

      {phase === 'result' && result && sessionData && (
        <ResultPanel
          result={result}
          questions={sessionData.questions}
          onReset={handleReset}
        />
      )}
    </div>
  )
}

export default ExamPage
