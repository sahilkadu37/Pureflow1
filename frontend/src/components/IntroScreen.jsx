import { useEffect } from 'react'
import { motion } from 'framer-motion'
import './IntroScreen.css'

const reveal = (delay, duration = 0.8) => ({
  initial: { opacity: 0, y: 20, filter: 'blur(7px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  transition: { delay, duration, ease: [0.22, 1, 0.36, 1] },
})

export default function IntroScreen({ onComplete }) {
  useEffect(() => {
    const timer = window.setTimeout(onComplete, 19200)
    return () => window.clearTimeout(timer)
  }, [onComplete])

  return <motion.main
    className="intro-screen"
    aria-label="PureFlow project introduction"
    initial={{ opacity: 1, scale: 1 }}
    animate={{ opacity: 1, scale: 1 }}
    exit={{ opacity: 0, scale: 1.012, transition: { duration: 0.8, ease: [0.7, 0, 0.2, 1] } }}
  >
    <div className="intro-grid" aria-hidden="true" />
    <div className="intro-orbit intro-orbit-one" aria-hidden="true" />
    <div className="intro-orbit intro-orbit-two" aria-hidden="true" />
    <div className="intro-line intro-line-one" aria-hidden="true" />
    <div className="intro-line intro-line-two" aria-hidden="true" />

    <div className="intro-frame">
      <header className="intro-topline">
        <span><i /> PUREFLOW <b>/</b> PROJECT INTRODUCTION</span>
        <span className="intro-duration">DATA ENGINEERING PROJECT <b>·</b> 20 SEC</span>
      </header>

      <section className="intro-content">
        <motion.div className="intro-brand-block" {...reveal(0.2, 1.05)}>
          <span className="intro-overline"><i /> WATER · DATA · SUSTAINABILITY</span>
          <h1>PUREFLOW</h1>
          <span className="intro-brand-rule" />
        </motion.div>

        <motion.p className="intro-project-title" {...reveal(1.5, 0.9)}>
          Water Consumption and Sustainability Analytics Platform
        </motion.p>

        <motion.p className="intro-project-course" {...reveal(4.05, 0.8)}>
          CIA 3 – DATA ENGINEERING PROJECT
        </motion.p>

        <motion.section className="intro-submission" aria-label="Submitted by" {...reveal(5.1, 0.7)}>
          <div className="intro-section-label"><span>01</span><h2>SUBMITTED BY</h2><i /></div>
          <div className="intro-students">
            <motion.article
              initial={{ opacity: 0, y: 24, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: 7, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
            >
              <span className="intro-student-index">STUDENT 01</span>
              <h3>SAHIL</h3>
              <motion.p {...reveal(7.8, 0.7)}><span>Register Number:</span><b>24112509</b></motion.p>
            </motion.article>
            <motion.article
              initial={{ opacity: 0, y: 24, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: 7.25, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
            >
              <span className="intro-student-index">STUDENT 02</span>
              <h3>YASH</h3>
              <motion.p {...reveal(8.05, 0.7)}><span>Register Number:</span><b>24112519</b></motion.p>
            </motion.article>
          </div>
        </motion.section>

        <motion.div className="intro-tagline" {...reveal(14, 0.9)}>
          <span>OUR INTENT</span>
          <p>Smarter Water Insights. <b>Sustainable Tomorrow.</b></p>
        </motion.div>
      </section>

      <footer className="intro-footer">
        <span>PUREFLOW <b>·</b> WATER SUSTAINABILITY ANALYTICS</span>
        <motion.span className="intro-loading-label" {...reveal(17, 0.5)}>PREPARING YOUR WORKSPACE</motion.span>
      </footer>
    </div>
    <div className="intro-progress" aria-hidden="true"><span /></div>
  </motion.main>
}
