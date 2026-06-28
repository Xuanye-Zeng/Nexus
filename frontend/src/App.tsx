import { Navigate, Route, Routes } from 'react-router-dom'
import { Dashboard } from './pages/Dashboard'
import { ResumePage } from './pages/ResumePage'
import { AgentRunsPage } from './pages/AgentRunsPage'
import { JobsPage } from './pages/JobsPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/jobs" element={<JobsPage />} />
      <Route path="/resume" element={<ResumePage />} />
      <Route path="/agent" element={<AgentRunsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
