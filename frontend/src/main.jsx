import { StrictMode, useCallback, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AnimatePresence, MotionConfig } from 'framer-motion'
import './index.css'
import App from './App.jsx'
import './redesign.css'
import IntroScreen from './components/IntroScreen.jsx'

function ApplicationEntry() {
  const [showIntro, setShowIntro] = useState(true)
  const completeIntro = useCallback(() => setShowIntro(false), [])

  return <MotionConfig reducedMotion="user"><AnimatePresence mode="wait">
    {showIntro
      ? <IntroScreen key="intro" onComplete={completeIntro} />
      : <App key="application" />}
  </AnimatePresence></MotionConfig>
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ApplicationEntry />
  </StrictMode>,
)
