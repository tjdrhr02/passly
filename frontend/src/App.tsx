import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import UploadPage from './pages/UploadPage'
import ExamPage from './pages/ExamPage'
import PracticePage from './pages/PracticePage'
import ReviewPage from './pages/ReviewPage'
import ChatPage from './pages/ChatPage'

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="exam" element={<ExamPage />} />
          <Route path="practice" element={<PracticePage />} />
          <Route path="review" element={<ReviewPage />} />
          <Route path="chat" element={<ChatPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
