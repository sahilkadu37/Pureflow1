import { useEffect } from 'react'
import { motion } from 'framer-motion'
import './IntroScreen.css'

const reveal = (delay, duration = 0.8) => ({
  initial: { opacity: 0, y: 18, filter: 'blur(7px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  transition: { delay, duration, ease: [0.22, 1, 0.36, 1] },
})

export default function IntroScreen({ onComplete }) {
  useEffect(() => {
    const timer = window.setTimeout(onComplete, 11200)
    return () => window.clearTimeout(timer)
  }, [onComplete])

  return <motion.main
    className="intro-screen"
    aria-label="PureFlow project introduction"
    initial={{ opacity: 1, scale: 1 }}
    animate={{ opacity: 1, scale: 1 }}
    exit={{ opacity: 0, scale: 1.015, transition: { duration: 0.8, ease: [0.7, 0, 0.2, 1] } }}
  >
    <div className="intro-grid" aria-hidden="true" />
    <div className="intro-orbit intro-orbit-one" aria-hidden="true" />
    <div className="intro-orbit intro-orbit-two" aria-hidden="true" />
    <div className="intro-line intro-line-one" aria-hidden="true" />
    <div className="intro-line intro-line-two" aria-hidden="true" />

    <div className="intro-frame">
      <header className="intro-topline">
        <span><i /> PUREFLOW <b>/</b> PROJECT INTRODUCTION</span>
        <span className="intro-duration">DATA ENGINEERING PROJECT <b>·</b> 12 SEC</span>
      </header>

      <section className="intro-content">
        <motion.div className="intro-brand-block" {...reveal(0.2, 1.05)}>
          <span className="intro-overline"><i /> WATER · DATA · SUSTAINABILITY</span>
          <h1>PUREFLOW</h1>
          <span className="intro-brand-rule" />
        </motion.div>

        <motion.div className="intro-project" {...reveal(1.75)}>
          <p className="intro-project-title">Water Consumption and Sustainability Analytics Platform</p>
          <p className="intro-project-course">CIA 3 – Data Engineering Project</p>
        </motion.div>

        <motion.section className="intro-submission" aria-label="Submitted by" {...reveal(3.7, 0.75)}>
          <div className="intro-section-label"><span>01</span><h2>Submitted By:</h2><i /></div>
          <div className="intro-students">
            <motion.article {...reveal(4.15, 0.75)}>
              <span className="intro-student-index">STUDENT 01</span>
              <h3>Sahil</h3>
              <p><span>REGISTER NUMBER</span><b>24112509</b></p>
            </motion.article>
            <motion.article {...reveal(4.45, 0.75)}>
              <span className="intro-student-index">STUDENT 02</span>
              <h3>Yash</h3>
              <p><span>REGISTER NUMBER</span><b>24112519</b></p>
            </motion.article>
          </div>
        </motion.section>

        <motion.div className="intro-tagline" {...reveal(7.45, 0.9)}>
          <span>OUR INTENT</span>
          <p>Smarter Water Insights. <b>Sustainable Tomorrow.</b></p>
        </motion.div>
      </section>

      <footer className="intro-footer">
        <span>PUREFLOW <b>·</b> WATER SUSTAINABILITY ANALYTICS</span>
        <span className="intro-loading-label">ENTERING WORKSPACE</span>
      </footer>
    </div>
    <div className="intro-progress" aria-hidden="true"><span /></div>
  </motion.main>
}
