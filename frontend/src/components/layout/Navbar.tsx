import { NavLink, useNavigate } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: '대시보드' },
  { to: '/upload', label: '자료 업로드' },
  { to: '/exam', label: '실전 시험' },
  { to: '/practice', label: '연습 모드' },
  { to: '/review', label: '오답 노트' },
  { to: '/chat', label: 'AI 질문' },
] as const

const Navbar = () => {
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login', { replace: true })
  }

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <span className="text-xl font-bold text-gray-900">Passly</span>
          <div className="flex items-center gap-6">
            {NAV_ITEMS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  isActive
                    ? 'text-sm font-medium text-blue-600'
                    : 'text-sm font-medium text-gray-600 hover:text-gray-900'
                }
              >
                {label}
              </NavLink>
            ))}
            <button
              onClick={handleLogout}
              className="text-sm font-medium text-gray-400 hover:text-gray-700"
            >
              로그아웃
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}

export default Navbar
