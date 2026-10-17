import { Routes, Route } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import Analyze from './pages/Analyze.jsx'
import History from './pages/History.jsx'
import Dashboard from './pages/Dashboard.jsx'
import About from './pages/About.jsx'

export default function App() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/" element={<Analyze />} />
        <Route path="/history" element={<History />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/about" element={<About />} />
      </Routes>
      <div className="footer shell">Foresight — a course project prototype for early food-spoilage detection. Not a certified food-safety tool.</div>
    </>
  )
}
