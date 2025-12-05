import { HomePage } from './pages/Home'
import './App.css'

export function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <span className="brand-badge">TastyGo</span>
          <h1 className="brand-title">TastyGo Restaurant Recommender</h1>
        </div>
        <p className="brand-subtitle">
          Describe your needs in natural language. We combine Geoapify and LLM to generate trustworthy recommendations in real-time.
        </p>
      </header>
      <main className="app-main">
        <HomePage />
      </main>
      <footer className="app-footer">
        <span>Geoapify Maps © • Recommendation data for reference only, please refer to official information.</span>
      </footer>
    </div>
  )
}

export default App
