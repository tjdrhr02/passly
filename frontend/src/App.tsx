import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import UploadPage from './pages/UploadPage'
import ExamPage from './pages/ExamPage'
import PracticePage from './pages/PracticePage'
import ReviewPage from './pages/ReviewPage'
import ChatPage from './pages/ChatPage'

const isAuthenticated = () => Boolean(localStorage.getItem('token'))

const PrivateRoute = ({ element }: { element: React.ReactElement }) =>
  isAuthenticated() ? element : <Navigate to="/login" replace />

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Layout />}>
          <Route index element={<PrivateRoute element={<DashboardPage />} />} />
          <Route path="upload" element={<PrivateRoute element={<UploadPage />} />} />
          <Route path="exam" element={<PrivateRoute element={<ExamPage />} />} />
          <Route path="practice" element={<PrivateRoute element={<PracticePage />} />} />
          <Route path="review" element={<PrivateRoute element={<ReviewPage />} />} />
          <Route path="chat" element={<PrivateRoute element={<ChatPage />} />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
