import { useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const getHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token') || ''}` })

// ─── Types ────────────────────────────────────────────────────────────────────

interface Certification {
  id: string
  name: string
  vendor: string
  exam_code: string
}

interface DocumentOut {
  id: string
  certification_id: string
  title: string
  source_type: string
  original_filename: string
  is_active: boolean
  created_at: string
}

interface PipelineRunOut {
  id: string
  learning_document_id: string
  document_version_id: string | null
  status: string
  total_chunks: number | null
  processed_chunks: number
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

interface PaginationMeta {
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function statusBadge(status: string) {
  const map: Record<string, string> = {
    PENDING: 'bg-yellow-100 text-yellow-700',
    PROCESSING: 'bg-blue-100 text-blue-700',
    COMPLETED: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
  }
  return map[status] ?? 'bg-gray-100 text-gray-600'
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ProgressBar({ run }: { run: PipelineRunOut }) {
  const pct =
    run.total_chunks && run.total_chunks > 0
      ? Math.round((run.processed_chunks / run.total_chunks) * 100)
      : run.status === 'COMPLETED'
        ? 100
        : 0

  return (
    <div className="mt-3 space-y-1">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>
          {run.processed_chunks}
          {run.total_chunks != null ? ` / ${run.total_chunks} 청크` : ' 청크 처리 중'}
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            run.status === 'FAILED' ? 'bg-red-500' : 'bg-blue-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {run.error_message && (
        <p className="text-xs text-red-600">{run.error_message}</p>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const UploadPage = () => {
  // Certifications
  const [certifications, setCertifications] = useState<Certification[]>([])
  const [certLoading, setCertLoading] = useState(true)

  // Inline cert creation state
  const [showCertForm, setShowCertForm] = useState(false)
  const [certName, setCertName] = useState('')
  const [certVendor, setCertVendor] = useState('')
  const [certExamCode, setCertExamCode] = useState('')
  const [certCreating, setCertCreating] = useState(false)
  const [certCreateError, setCertCreateError] = useState('')

  // Form state
  const [selectedCert, setSelectedCert] = useState('')
  const [sourceType, setSourceType] = useState<'OFFICIAL_GUIDE' | 'DUMP'>('OFFICIAL_GUIDE')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Upload state
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [activeRun, setActiveRun] = useState<PipelineRunOut | null>(null)

  // Delete state
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // History
  const [history, setHistory] = useState<DocumentOut[]>([])
  const [historyMeta, setHistoryMeta] = useState<PaginationMeta | null>(null)
  const [historyPage, setHistoryPage] = useState(1)
  const [historyLoading, setHistoryLoading] = useState(false)

  // ── Fetch certifications ─────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API_BASE}/api/upload/certifications`, { headers: getHeaders() })
      .then((r) => r.json())
      .then((json) => {
        setCertifications(json.data ?? [])
        if (json.data?.length) setSelectedCert(json.data[0].id)
      })
      .catch(() => {})
      .finally(() => setCertLoading(false))
  }, [])

  // ── Fetch history ────────────────────────────────────────────────────────
  const fetchHistory = (page: number) => {
    setHistoryLoading(true)
    fetch(`${API_BASE}/api/upload/history?page=${page}&page_size=10`, {
      headers: getHeaders(),
    })
      .then((r) => r.json())
      .then((json) => {
        setHistory(json.data ?? [])
        setHistoryMeta(json.meta ?? null)
      })
      .catch(() => {})
      .finally(() => setHistoryLoading(false))
  }

  useEffect(() => {
    fetchHistory(historyPage)
  }, [historyPage])

  // ── Poll active run ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!activeRun) return
    if (activeRun.status === 'COMPLETED' || activeRun.status === 'FAILED') return

    const interval = setInterval(() => {
      fetch(`${API_BASE}/api/upload/${activeRun.id}/status`, {
        headers: getHeaders(),
      })
        .then((r) => r.json())
        .then((json) => {
          const updated: PipelineRunOut = json.data
          setActiveRun(updated)
          if (updated.status === 'COMPLETED' || updated.status === 'FAILED') {
            clearInterval(interval)
            fetchHistory(1)
            setHistoryPage(1)
          }
        })
        .catch(() => clearInterval(interval))
    }, 2000)

    return () => clearInterval(interval)
  }, [activeRun])

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleDelete = async (docId: string) => {
    if (!window.confirm('이 문서를 삭제하시겠습니까?')) return
    setDeletingId(docId)
    try {
      const res = await fetch(`${API_BASE}/api/upload/${docId}`, {
        method: 'DELETE',
        headers: getHeaders(),
      })
      if (!res.ok) {
        const json = await res.json()
        alert(json.detail ?? '삭제에 실패했습니다.')
        return
      }
      fetchHistory(1)
      setHistoryPage(1)
    } catch {
      alert('네트워크 오류가 발생했습니다.')
    } finally {
      setDeletingId(null)
    }
  }

  const handleCertCreate = async () => {
    setCertCreating(true)
    setCertCreateError('')
    try {
      const res = await fetch(`${API_BASE}/api/certifications`, {
        method: 'POST',
        headers: { ...getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: certName.trim(), vendor: certVendor.trim(), exam_code: certExamCode.trim(), domains: [] }),
      })
      const json = await res.json()
      if (!res.ok) {
        setCertCreateError(json.detail ?? '자격증 등록에 실패했습니다.')
        return
      }
      const created: Certification = json.data
      setCertifications((prev) => [...prev, created])
      setSelectedCert(created.id)
      setCertName('')
      setCertVendor('')
      setCertExamCode('')
      setShowCertForm(false)
    } catch {
      setCertCreateError('네트워크 오류가 발생했습니다.')
    } finally {
      setCertCreating(false)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setFile(f)
    if (f && !title) setTitle(f.name.replace(/\.pdf$/i, ''))
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f?.type === 'application/pdf') {
      setFile(f)
      if (!title) setTitle(f.name.replace(/\.pdf$/i, ''))
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || !selectedCert || !title.trim()) return

    setUploading(true)
    setUploadError('')
    setActiveRun(null)

    const form = new FormData()
    form.append('file', file)
    form.append('certification_id', selectedCert)
    form.append('source_type', sourceType)
    form.append('title', title.trim())

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        headers: getHeaders(),
        body: form,
      })
      const json = await res.json()
      if (!res.ok) {
        setUploadError(json.detail ?? '업로드에 실패했습니다.')
        return
      }
      setActiveRun(json.data.pipeline_run)
      setFile(null)
      setTitle('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      fetchHistory(1)
      setHistoryPage(1)
    } catch {
      setUploadError('네트워크 오류가 발생했습니다.')
    } finally {
      setUploading(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">자료 업로드</h1>
        <p className="mt-1 text-sm text-gray-500">
          PDF 파일을 업로드하고 파이프라인 진행 상태를 확인하세요.
        </p>
      </div>

      {/* 문서 유형 안내 */}
      <div className="rounded-lg border border-blue-100 bg-blue-50 px-5 py-4 text-sm">
        <p className="font-medium text-blue-800 mb-2">문서 유형별 기능 안내</p>
        <div className="space-y-1 text-blue-700">
          <p>📚 <span className="font-medium">공식 가이드 (Official Guide)</span> — AI 질문 탭에서 내용 기반 질문/답변에 사용됩니다.</p>
          <p>📝 <span className="font-medium">덤프 (Dump)</span> — 실전 시험 및 연습 모드의 문제 풀이에 사용됩니다.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* ── Upload Form ── */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-base font-medium text-gray-800">새 파일 업로드</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Certification select */}
            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className="block text-sm font-medium text-gray-700">자격증</label>
                {!certLoading && (
                  <button
                    type="button"
                    onClick={() => setShowCertForm((v) => !v)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    {showCertForm ? '취소' : '+ 새 자격증 추가'}
                  </button>
                )}
              </div>
              {certLoading ? (
                <div className="h-9 animate-pulse rounded-md bg-gray-100" />
              ) : showCertForm || certifications.length === 0 ? (
                <div className="rounded-md border border-blue-200 bg-blue-50 p-3 space-y-2">
                  <p className="text-xs font-medium text-blue-700">새 자격증 등록</p>
                  <input
                    type="text"
                    placeholder="자격증 이름 (예: Azure AI Engineer Associate)"
                    value={certName}
                    onChange={(e) => setCertName(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    type="text"
                    placeholder="벤더 (예: Microsoft)"
                    value={certVendor}
                    onChange={(e) => setCertVendor(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    type="text"
                    placeholder="시험 코드 (예: AI-102)"
                    value={certExamCode}
                    onChange={(e) => setCertExamCode(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {certCreateError && (
                    <p className="text-xs text-red-600">{certCreateError}</p>
                  )}
                  <button
                    type="button"
                    disabled={certCreating || !certName.trim() || !certVendor.trim() || !certExamCode.trim()}
                    onClick={handleCertCreate}
                    className="w-full rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {certCreating ? '등록 중...' : '자격증 등록'}
                  </button>
                </div>
              ) : (
                <select
                  value={selectedCert}
                  onChange={(e) => setSelectedCert(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                >
                  {certifications.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.exam_code})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Source type */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">문서 유형</label>
              <div className="flex gap-3">
                {(['OFFICIAL_GUIDE', 'DUMP'] as const).map((t) => (
                  <label
                    key={t}
                    className={`flex flex-1 cursor-pointer items-center justify-center rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                      sourceType === t
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="source_type"
                      value={t}
                      checked={sourceType === t}
                      onChange={() => setSourceType(t)}
                      className="sr-only"
                    />
                    {t === 'OFFICIAL_GUIDE' ? '공식 가이드' : '덤프'}
                  </label>
                ))}
              </div>
            </div>

            {/* Title */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">문서 제목</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="문서 제목을 입력하세요"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>

            {/* File drop zone */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">PDF 파일</label>
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 transition-colors ${
                  file
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-300 bg-gray-50 hover:border-gray-400'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  onChange={handleFileChange}
                  className="hidden"
                />
                {file ? (
                  <>
                    <p className="text-sm font-medium text-blue-700">{file.name}</p>
                    <p className="mt-1 text-xs text-blue-500">
                      {(file.size / 1024 / 1024).toFixed(1)} MB
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-gray-500">
                      PDF 파일을 드래그하거나 클릭하여 선택
                    </p>
                    <p className="mt-1 text-xs text-gray-400">최대 100MB</p>
                  </>
                )}
              </div>
            </div>

            {uploadError && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{uploadError}</p>
            )}

            <button
              type="submit"
              disabled={uploading || !file || !selectedCert || !title.trim()}
              className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? '업로드 중...' : '업로드'}
            </button>
          </form>
        </div>

        {/* ── Pipeline status ── */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-base font-medium text-gray-800">파이프라인 진행 상태</h2>

          {!activeRun ? (
            <div className="flex h-32 items-center justify-center text-sm text-gray-400">
              업로드 후 진행 상태가 여기에 표시됩니다.
            </div>
          ) : (
            <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-800">
                  Run ID:{' '}
                  <span className="font-mono text-xs text-gray-500">
                    {activeRun.id.slice(0, 8)}…
                  </span>
                </p>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadge(activeRun.status)}`}
                >
                  {activeRun.status}
                </span>
              </div>

              <ProgressBar run={activeRun} />

              {(activeRun.status === 'PROCESSING' || activeRun.status === 'PENDING') && (
                <p className="mt-2 text-xs text-gray-400">2초마다 자동 갱신 중…</p>
              )}
              {activeRun.status === 'COMPLETED' && (
                <p className="mt-2 text-xs text-green-600">파이프라인 처리가 완료되었습니다.</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Upload History ── */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-medium text-gray-800">업로드 이력</h2>

        {historyLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-md bg-gray-100" />
            ))}
          </div>
        ) : history.length === 0 ? (
          <p className="text-sm text-gray-400">업로드된 문서가 없습니다.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase text-gray-400">
                    <th className="pb-2 pr-4">제목</th>
                    <th className="pb-2 pr-4">유형</th>
                    <th className="pb-2 pr-4">파일명</th>
                    <th className="pb-2 pr-4">업로드 일시</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {history.map((doc) => (
                    <tr key={doc.id} className="hover:bg-gray-50">
                      <td className="py-2.5 pr-4 font-medium text-gray-800">{doc.title}</td>
                      <td className="py-2.5 pr-4">
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                          {doc.source_type === 'OFFICIAL_GUIDE' ? '공식 가이드' : '덤프'}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-gray-500">{doc.original_filename}</td>
                      <td className="py-2.5 pr-4 text-gray-500">{formatDate(doc.created_at)}</td>
                      <td className="py-2.5">
                        <button
                          type="button"
                          onClick={() => handleDelete(doc.id)}
                          disabled={deletingId === doc.id}
                          className="text-xs text-red-400 hover:text-red-600 disabled:opacity-40"
                        >
                          {deletingId === doc.id ? '삭제 중...' : '삭제'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {historyMeta && historyMeta.total_pages > 1 && (
              <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
                <span>
                  총 {historyMeta.total}개 · {historyMeta.page} / {historyMeta.total_pages} 페이지
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                    disabled={historyPage <= 1}
                    className="rounded-md border border-gray-200 px-3 py-1 hover:bg-gray-50 disabled:opacity-40"
                  >
                    이전
                  </button>
                  <button
                    onClick={() =>
                      setHistoryPage((p) => Math.min(historyMeta.total_pages, p + 1))
                    }
                    disabled={historyPage >= historyMeta.total_pages}
                    className="rounded-md border border-gray-200 px-3 py-1 hover:bg-gray-50 disabled:opacity-40"
                  >
                    다음
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default UploadPage
