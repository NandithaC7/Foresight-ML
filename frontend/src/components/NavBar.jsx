import { NavLink } from 'react-router-dom'

export default function NavBar() {
  return (
    <nav className="nav">
      <div className="nav-inner">
        <div className="brand">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path d="M12 21C7 21 4 16.5 4 11.5 4 7 7 3 12 3s8 4 8 8.5C20 16.5 17 21 12 21Z" stroke="#2F4A3D" strokeWidth="1.6" />
            <path d="M12 21V9" stroke="#2F4A3D" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          Foresight
        </div>
        <div className="nav-links">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Analyze</NavLink>
          <NavLink to="/history" className={({ isActive }) => isActive ? 'active' : ''}>History</NavLink>
          <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'active' : ''}>Dashboard</NavLink>
          <NavLink to="/about" className={({ isActive }) => isActive ? 'active' : ''}>About</NavLink>
        </div>
      </div>
    </nav>
  )
}
