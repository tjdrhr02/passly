import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token') || ''}` })

interface CertificationSummary {
  certification_id: string
  certification_name: string
  total_attempts: number
  correct_count: number
  accuracy_percent: number
}

interface AnalyticsSummary {
  certifications: CertificationSummary[]
  total_sessions: number
  total_questions_answered: number
}

interface RecentSessionItem {
  session_id: string
  certification_name: string
  exam_mode: string
  total_questions: number
  correct_count: number
  score_percent: number
  completed_at: string
}

interface RecentSessions {
  sessions: RecentSessionItem[]
}

interface WeakDomainItem {
  domain_name: string
  certification_name: string
  total_attempts: number
  wrong_count: number
  error_rate_percent: number
}

interface WeakDomains {
  domains: WeakDomainItem[]
}

const DashboardPage = () => {
  const navigate = useNavigate()
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [recentSessions, setRecentSessions] = useState<RecentSessions | null>(null)
  const [weakDomains, setWeakDomains] = useState<WeakDomains | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [summaryRes, sessionsRes, domainsRes] = await Promise.all([
          fetch(`${API_BASE}/api/analytics/summary`, { headers: authHeader() }),
          fetch(`${API_BASE}/api/analytics/recent-sessions?limit=5`, { headers: authHeader() }),
          fetch(`${API_BASE}/api/analytics/weak-domains`, { headers: authHeader() }),
        ])

        if (!summaryRes.ok || !sessionsRes.ok || !domainsRes.ok) {
          throw new Error('데이터를 불러오는 데 실패했습니다.')
        }

        const [summaryJson, sessionsJson, domainsJson] = await Promise.all([
          summaryRes.json(),
          sessionsRes.json(),
          domainsRes.json(),
        ])

        setSummary(summaryJson.data)
        setRecentSessions(sessionsJson.data)
        setWeakDomains(domainsJson.data)
      } catch (err) {
        setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.')
      } finally {
        setLoading(false)
      }
    }

    fetchAll()
  }, [])

  const totalAttempts = summary?.certifications.reduce((acc, c) => acc + c.total_attempts, 0) ?? 0
  const totalCorrect = summary?.certifications.reduce((acc, c) => acc + c.correct_count, 0) ?? 0
  const overallAccuracy = totalAttempts > 0 ? Math.round((totalCorrect / totalAttempts) * 100) : 0
  const latestScore = recentSessions?.sessions[0]?.score_percent ?? null

  const isEmpty =
    !loading &&
    !error &&
    summary?.certifications.length === 0 &&
    recentSessions?.sessions.length === 0

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold text-gray-900">대시보드</h1>
        <div className="mt-8 space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-lg bg-gray-100 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold text-gray-900">대시보드</h1>
        <p className="mt-4 text-red-500">{error}</p>
      </div>
    )
  }

  if (isEmpty) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-semibold text-gray-900">대시보드</h1>
        <div className="mt-12 flex flex-col items-center text-center">
          <p className="text-gray-500 text-lg">아직 학습 기록이 없습니다. 시험을 시작해보세요!</p>
          <div className="mt-6 flex gap-4">
            <button
              onClick={() => navigate('/exam')}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              실전 시험 시작
            </button>
            <button
              onClick={() => navigate('/practice')}
              className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors"
            >
              연습 모드 시작
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-8">
      <h1 className="text-2xl font-semibold text-gray-900">대시보드</h1>

      {/* 지표 카드 */}
      <div className="flex flex-row gap-4">
        <div className="flex-1 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">전체 정답률</p>
          <p className="mt-1 text-3xl font-bold text-blue-600">{overallAccuracy}%</p>
          <p className="mt-1 text-xs text-gray-400">{totalAttempts}문제 중 {totalCorrect}개 정답</p>
        </div>
        <div className="flex-1 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">총 풀이 수</p>
          <p className="mt-1 text-3xl font-bold text-gray-800">{totalAttempts}</p>
          <p className="mt-1 text-xs text-gray-400">세션 {summary?.total_sessions ?? 0}회 완료</p>
        </div>
        <div className="flex-1 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-500">최근 시험 점수</p>
          <p className="mt-1 text-3xl font-bold text-green-600">
            {latestScore !== null ? `${latestScore}%` : '-'}
          </p>
          <p className="mt-1 text-xs text-gray-400">
            {recentSessions?.sessions[0]?.certification_name ?? '기록 없음'}
          </p>
        </div>
      </div>

      {/* 최근 5회 시험 결과 */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-4">
          <h2 className="text-base font-semibold text-gray-800">최근 시험 결과</h2>
        </div>
        {recentSessions && recentSessions.sessions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-5 py-3 text-left">날짜</th>
                  <th className="px-5 py-3 text-left">자격증</th>
                  <th className="px-5 py-3 text-left">점수</th>
                  <th className="px-5 py-3 text-left">문제 수</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentSessions.sessions.map((session) => (
                  <tr key={session.session_id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-5 py-3 text-gray-600">
                      {new Date(session.completed_at).toLocaleDateString('ko-KR')}
                    </td>
                    <td className="px-5 py-3 text-gray-800 font-medium">
                      {session.certification_name}
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`font-semibold ${
                          session.score_percent >= 70 ? 'text-green-600' : 'text-red-500'
                        }`}
                      >
                        {session.score_percent}%
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-600">{session.total_questions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="px-5 py-6 text-gray-400 text-sm">완료된 시험 기록이 없습니다.</p>
        )}
      </div>

      {/* 영역별 오답률 Top 3 */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-4">
          <h2 className="text-base font-semibold text-gray-800">취약 영역 Top 3</h2>
        </div>
        <div className="px-5 py-4 space-y-4">
          {weakDomains && weakDomains.domains.length > 0 ? (
            weakDomains.domains.map((domain, idx) => (
              <div key={`${domain.domain_name}-${idx}`}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium text-gray-800">{domain.domain_name}</span>
                  <span className="text-gray-500 text-xs">{domain.certification_name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className="h-2 rounded-full bg-red-400 transition-all"
                      style={{ width: `${Math.min(domain.error_rate_percent, 100)}%` }}
                    />
                  </div>
                  <span className="text-sm font-semibold text-red-500 w-12 text-right">
                    {domain.error_rate_percent}%
                  </span>
                </div>
              </div>
            ))
          ) : (
            <p className="text-gray-400 text-sm">취약 영역 데이터가 없습니다.</p>
          )}
        </div>
      </div>

      {/* 빠른 시작 버튼 */}
      <div className="flex justify-end gap-4">
        <button
          onClick={() => navigate('/exam')}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
        >
          실전 시험 시작
        </button>
        <button
          onClick={() => navigate('/practice')}
          className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors font-medium"
        >
          연습 모드 시작
        </button>
      </div>
    </div>
  )
}

export default DashboardPage
