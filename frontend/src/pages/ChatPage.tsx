import { useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem('token') || ''}` })

interface SourceChunk {
  chunk_id: string
  chunk_text: string
  rrf_score: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: SourceChunk[]
}

interface Certification {
  id: string
  name: string
  exam_code: string
}

interface ChatResponseData {
  answer: string
  sources: SourceChunk[]
}

const ChatPage = () => {
  const [certifications, setCertifications] = useState<Certification[]>([])
  const [selectedCertId, setSelectedCertId] = useState<string>('')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchCertifications = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/certifications`, {
          headers: authHeader(),
        })
        if (res.ok) {
          const json = await res.json()
          const data: Certification[] = json.data ?? []
          setCertifications(data)
          if (data.length > 0) {
            setSelectedCertId(data[0].id)
          }
        }
      } catch {
        // 자격증 목록 로드 실패 시 빈 목록 유지
      }
    }
    fetchCertifications()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    const question = input.trim()
    if (!question || !selectedCertId || loading) return

    const userMessage: Message = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeader(),
        },
        body: JSON.stringify({ question, certification_id: selectedCertId }),
      })

      if (res.ok) {
        const json = await res.json()
        const chatData = json.data as ChatResponseData
        const assistantMessage: Message = {
          role: 'assistant',
          content: chatData.answer,
          sources: chatData.sources,
        }
        setMessages((prev) => [...prev, assistantMessage])
      } else {
        const errorJson = await res.json().catch(() => ({ detail: '오류가 발생했습니다.' }))
        const errorMessage: Message = {
          role: 'assistant',
          content: errorJson.detail ?? '오류가 발생했습니다.',
        }
        setMessages((prev) => [...prev, errorMessage])
      }
    } catch {
      const errorMessage: Message = {
        role: 'assistant',
        content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.',
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const lastSources = [...messages].reverse().find((m) => m.role === 'assistant' && m.sources)?.sources

  return (
    <div className="flex h-[calc(100vh-4rem)] gap-4 p-6">
      {/* 왼쪽: 대화 영역 (2/3) */}
      <div className="flex flex-col flex-[2] min-w-0">
        {/* 자격증 선택 */}
        <div className="mb-4">
          <select
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={selectedCertId}
            onChange={(e) => setSelectedCertId(e.target.value)}
          >
            {certifications.length === 0 && (
              <option value="">자격증 없음</option>
            )}
            {certifications.map((cert) => (
              <option key={cert.id} value={cert.id}>
                {cert.name} ({cert.exam_code})
              </option>
            ))}
          </select>
        </div>

        {/* 대화 히스토리 */}
        <div className="flex-1 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-4">
          {messages.length === 0 && (
            <p className="text-center text-sm text-gray-400 mt-8">
              자격증을 선택하고 질문을 입력하세요.
            </p>
          )}
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                  msg.role === 'user'
                    ? 'bg-blue-500 text-white'
                    : 'bg-white text-gray-800 border border-gray-200'
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-white border border-gray-200 px-4 py-2 text-sm text-gray-400">
                답변 생성 중...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* 입력창 */}
        <div className="mt-4 flex gap-2">
          <textarea
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={3}
            placeholder="질문을 입력하세요 (Enter = 전송, Shift+Enter = 줄바꿈)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            className="self-end rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-600 disabled:opacity-50"
            onClick={sendMessage}
            disabled={loading || !input.trim() || !selectedCertId}
          >
            전송
          </button>
        </div>
      </div>

      {/* 오른쪽: 출처 패널 (1/3) */}
      <div className="flex flex-col flex-[1] min-w-0">
        <h2 className="mb-3 text-sm font-semibold text-gray-700">출처</h2>
        <div className="flex-1 overflow-y-auto rounded-lg border border-gray-200 bg-white p-4 space-y-3">
          {!lastSources || lastSources.length === 0 ? (
            <p className="text-xs text-gray-400">답변을 받으면 출처 청크가 표시됩니다.</p>
          ) : (
            lastSources.map((src, idx) => (
              <div key={src.chunk_id} className="rounded-md border border-gray-100 bg-gray-50 p-3">
                <p className="mb-1 text-xs font-medium text-gray-500">출처 {idx + 1}</p>
                <p className="text-xs text-gray-700">
                  {src.chunk_text.length > 200 ? src.chunk_text.slice(0, 200) + '...' : src.chunk_text}
                </p>
                <p className="mt-1 text-xs text-gray-400">점수: {src.rrf_score.toFixed(4)}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default ChatPage
