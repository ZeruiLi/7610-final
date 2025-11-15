import { HomePage } from './pages/Home'
import './App.css'

export function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <span className="brand-badge">Tango</span>
          <h1 className="brand-title">餐厅推荐助手</h1>
        </div>
        <p className="brand-subtitle">
          自然语言描述需求，结合 Geoapify 与 LLM 实时生成可信赖的推荐。
        </p>
      </header>
      <main className="app-main">
        <HomePage />
      </main>
      <footer className="app-footer">
        <span>Geoapify Maps © • 推荐数据仅供参考，请以官方信息为准。</span>
      </footer>
    </div>
  )
}

export default App
