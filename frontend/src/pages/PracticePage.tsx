import { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const authHeader = (): Record<string, string> => ({
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
  'Content-Type': 'application/json',
})

// ── 타입 정의 ──────────────────────────────────────────────────

interface Certification {
  id: string
  name: string
}

interface Domain {
  id: string
  name: string
  order_num: number
}

interface ChoiceItem {
  id: string
  choice_label: string
  choice_text: string
  is_correct: boolean
  order_num: number
}

interface GeneratedQuestion {
  id: string
  question_text: string
  question_type: string
  difficulty: string
  choices: ChoiceItem[]
  explanation_text: string | null
}

interface SubmitResult {
  is_correct: boolean
  correct_choice_ids: string[]
  explanation_text: string | null
}

// ── 설정 화면 ──────────────────────────────────────────────────

interface SetupPanelProps {
  onStart: (certId: string, domainId: string | null, count: number) => void
  loading: boolean
}

const SetupPanel = ({ onStart, loading }: SetupPanelProps) => {
  const [certifications, setCertifications] = useState<Certification[]>([])
  const [domains, setDomains] = useState<Domain[]>([])
  const [selectedCert, setSelectedCert] = useState<string>('')
  const [selectedDomain, setSelectedDomain] = useState<string>('')
  const [count, setCount] = useState<number>(10)
  const [fetchError, setFetchError] = useState<string>('')

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/certifications`, {
          headers: authHeader(),
        })
        if (!res.ok) throw new Error('자격증 목록을 불러오지 못했습니다.')
        const json = await res.json()
        const list: Certification[] = json.data ?? json
        setCertifications(list)
        if (list.length > 0) setSelectedCert(list[0].id)
      } catch (e) {
        setFetchError(e instanceof Error ? e.message : '오류가 발생했습니다.')
      }
    }
    load()
  }, [])

  useEffect(() => {
    if (!selectedCert) {
      setDomains([])
      setSelectedDomain('')
      return
    }
    const load = async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/certifications/${selectedCert}/domains`,
          { headers: authHeader() },
        )
        if (!res.ok) throw new Error()
        const json = await res.json()
        const list: Domain[] = json.data ?? json
        setDomains(list)
        setSelectedDomain('')
      } catch {
        setDomains([])
      }
    }
    load()
  }, [selectedCert])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCert) return
    onStart(selectedCert, selectedDomain || null, count)
  }

  return (
    <div className="max-w-lg mx-auto mt-8 bg-white rounded-2xl shadow p-8">
      <h2 className="text-xl font-semibold text-gray-800 mb-6">연습 설정</h2>

      {fetchError && (
        <p className="mb-4 text-sm text-red-600">{fetchError}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* 자격증 선택 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            자격증
          </label>
          <select
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={selectedCert}
            onChange={(e) => setSelectedCert(e.target.value)}
            required
          >
            {certifications.length === 0 && (
              <option value="">불러오는 중...</option>
            )}
            {certifications.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {/* 영역 선택 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            영역 (선택)
          </label>
          <select
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={selectedDomain}
            onChange={(e) => setSelectedDomain(e.target.value)}
          >
            <option value="">전체</option>
            {domains.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>

        {/* 문제 수 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            문제 수
          </label>
          <div className="flex gap-3">
            {[5, 10, 20].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setCount(n)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  count === n
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'
                }`}
              >
                {n}문제
              </button>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !selectedCert}
          className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '문제 불러오는 중...' : '문제 생성'}
        </button>
      </form>
    </div>
  )
}

// ── 개별 문제 컴포넌트 ──────────────────────────────────────────

interface QuestionCardProps {
  index: number
  question: GeneratedQuestion
}

const QuestionCard = ({ index, question }: QuestionCardProps) => {
  const [selected, setSelected] = useState<string[]>([])
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string>('')

  const isMultiple = question.question_type === 'MULTIPLE'

  const submitAnswer = async (choiceIds: string[]) => {
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/api/practice/submit`, {
        method: 'POST',
        headers: authHeader(),
        body: JSON.stringify({
          question_id: question.id,
          selected_choice_ids: choiceIds,
        }),
      })
      if (!res.ok) {
        const json = await res.json()
        throw new Error(json.detail ?? '채점 중 오류가 발생했습니다.')
      }
      const json = await res.json()
      setResult(json.data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '채점 중 오류가 발생했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSelect = async (choiceId: string) => {
    if (result) return // 이미 채점됨

    if (isMultiple) {
      // 다중 선택: 토글만 하고 별도 제출 버튼으로 처리
      setSelected((prev) =>
        prev.includes(choiceId)
          ? prev.filter((id) => id !== choiceId)
          : [...prev, choiceId],
      )
      return
    }

    // 단일 선택: 클릭 즉시 제출
    const next = [choiceId]
    setSelected(next)
    await submitAnswer(next)
  }

  const getChoiceStyle = (choice: ChoiceItem): string => {
    const base =
      'w-full text-left flex items-start gap-3 p-3 rounded-lg border transition-colors text-sm'

    if (!result) {
      return `${base} cursor-pointer ${
        selected.includes(choice.id)
          ? 'border-blue-500 bg-blue-50'
          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
      }`
    }

    // 채점 후
    const isCorrect = result.correct_choice_ids.includes(choice.id)
    const isSelected = selected.includes(choice.id)

    if (isCorrect) return `${base} border-green-500 bg-green-50 cursor-default`
    if (isSelected && !isCorrect)
      return `${base} border-red-400 bg-red-50 cursor-default`
    return `${base} border-gray-200 bg-white cursor-default`
  }

  const difficultyLabel: Record<string, string> = {
    BEGINNER: '초급',
    INTERMEDIATE: '중급',
    ADVANCED: '고급',
  }

  return (
    <div className="bg-white rounded-2xl shadow p-6 mb-6">
      {/* 문제 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-gray-500">
          {index + 1}번
        </span>
        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
          {difficultyLabel[question.difficulty] ?? question.difficulty}
        </span>
      </div>

      {/* 문제 텍스트 */}
      <p className="text-gray-900 font-medium mb-4 whitespace-pre-wrap leading-relaxed">
        {question.question_text}
      </p>

      {/* 선택지 */}
      <div className="space-y-2">
        {question.choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            onClick={() => handleSelect(choice.id)}
            disabled={submitting || (result !== null && !isMultiple)}
            className={getChoiceStyle(choice)}
          >
            <span className="font-semibold text-gray-500 shrink-0 w-5">
              {choice.choice_label}.
            </span>
            <span className="text-gray-800">{choice.choice_text}</span>
          </button>
        ))}
      </div>

      {/* 다중 선택 제출 버튼 */}
      {isMultiple && !result && (
        <button
          type="button"
          onClick={() => submitAnswer(selected)}
          disabled={submitting || selected.length === 0}
          className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? '채점 중...' : '제출'}
        </button>
      )}

      {/* 오류 */}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {/* 채점 결과 */}
      {result && (
        <div
          className={`mt-4 rounded-lg p-4 ${
            result.is_correct
              ? 'bg-green-50 border border-green-200'
              : 'bg-red-50 border border-red-200'
          }`}
        >
          <p
            className={`font-semibold text-sm mb-1 ${
              result.is_correct ? 'text-green-700' : 'text-red-700'
            }`}
          >
            {result.is_correct ? '정답입니다!' : '오답입니다.'}
          </p>
          {result.explanation_text && (
            <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {result.explanation_text}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ── 메인 페이지 ────────────────────────────────────────────────

const PracticePage = () => {
  const [questions, setQuestions] = useState<GeneratedQuestion[]>([])
  const [started, setStarted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string>('')
  const [genError, setGenError] = useState<string>('')

  const handleStart = async (
    certId: string,
    domainId: string | null,
    count: number,
  ) => {
    setLoading(true)
    setGenError('')
    setMessage('')
    try {
      const body: Record<string, unknown> = {
        certification_id: certId,
        count,
      }
      if (domainId) body.domain_id = domainId

      const res = await fetch(`${API_BASE}/api/practice/generate`, {
        method: 'POST',
        headers: authHeader(),
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const json = await res.json()
        throw new Error(json.detail ?? '문제 생성에 실패했습니다.')
      }
      const json = await res.json()
      const data = json.data
      setQuestions(data.questions)
      if (json.message && json.message !== 'success') {
        setMessage(json.message)
      }
      setStarted(true)
    } catch (e) {
      setGenError(e instanceof Error ? e.message : '문제 생성에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setStarted(false)
    setQuestions([])
    setMessage('')
    setGenError('')
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">연습 모드</h1>
          <p className="mt-1 text-sm text-gray-500">
            영역을 선택하고 즉시 피드백을 받으세요.
          </p>
        </div>
        {started && (
          <button
            type="button"
            onClick={handleReset}
            className="text-sm text-blue-600 hover:underline"
          >
            다시 설정
          </button>
        )}
      </div>

      {genError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {genError}
        </div>
      )}

      {!started ? (
        <SetupPanel onStart={handleStart} loading={loading} />
      ) : (
        <div>
          {message && (
            <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
              {message}
            </div>
          )}
          {questions.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <p className="text-lg">해당 조건에 맞는 문제가 없습니다.</p>
              <button
                type="button"
                onClick={handleReset}
                className="mt-4 text-sm text-blue-600 hover:underline"
              >
                다시 설정하기
              </button>
            </div>
          ) : (
            <>
              <p className="text-sm text-gray-500 mb-4">
                총 {questions.length}문제 — 선택지를 클릭하면 즉시 채점됩니다.
              </p>
              {questions.map((q, i) => (
                <QuestionCard key={q.id} index={i} question={q} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default PracticePage
