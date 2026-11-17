import { motion } from 'framer-motion'

export function OrbitalDecoration({ className = '' }) {
  return <div className={`orbital-art ${className}`} aria-hidden="true">
    <motion.svg viewBox="0 0 360 300" fill="none" xmlns="http://www.w3.org/2000/svg" initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: .65, ease: 'easeOut' }}>
      <circle cx="190" cy="150" r="94" stroke="currentColor" strokeOpacity=".2" />
      <circle cx="190" cy="150" r="126" stroke="currentColor" strokeOpacity=".12" strokeDasharray="2 7" />
      <ellipse cx="190" cy="150" rx="154" ry="59" transform="rotate(-28 190 150)" stroke="currentColor" strokeOpacity=".22" />
      <ellipse cx="190" cy="150" rx="145" ry="48" transform="rotate(42 190 150)" stroke="currentColor" strokeOpacity=".13" />
      <path d="M42 207C97 148 139 238 194 170C240 114 281 128 326 68" stroke="currentColor" strokeOpacity=".28" />
      <circle cx="190" cy="150" r="58" fill="url(#aquaGlow)" />
      <circle cx="294" cy="85" r="5" fill="currentColor" />
      <circle cx="75" cy="96" r="3" fill="currentColor" fillOpacity=".65" />
      <circle cx="112" cy="226" r="4" fill="currentColor" fillOpacity=".45" />
      <circle cx="319" cy="207" r="3" fill="currentColor" fillOpacity=".55" />
      <defs><radialGradient id="aquaGlow"><stop stopColor="currentColor" stopOpacity=".16"/><stop offset="1" stopColor="currentColor" stopOpacity="0"/></radialGradient></defs>
    </motion.svg>
    <motion.span className="orbit-dot orbit-dot-one" animate={{ rotate: 360 }} transition={{ duration: 28, repeat: Infinity, ease: 'linear' }} />
    <span className="orbit-dot orbit-dot-two" />
  </div>
}

export function GeometricBackground() {
  return <div className="geometric-background" aria-hidden="true"><OrbitalDecoration className="hero-orbit"/><div className="hero-dot-grid" /></div>
}
