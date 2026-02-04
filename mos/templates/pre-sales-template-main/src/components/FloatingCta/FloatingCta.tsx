import type { FloatingCta as FloatingCtaType } from '../../pages/ListiclePage/types'
import { useEffect, useState } from 'react'
import { Button } from '../Button/Button'
import styles from './FloatingCta.module.css'

type Props = {
  cta: FloatingCtaType
}

export function FloatingCta({ cta }: Props) {
  const [triggered, setTriggered] = useState(false)

  useEffect(() => {
    const targetId = cta.showAfterId ?? (cta.showAfterReason ? `reason-${cta.showAfterReason}` : null)
    if (!targetId) {
      setTriggered(true)
      return
    }

    const el = document.getElementById(targetId)
    if (!el) return

    const obs = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry) return
        const pastTrigger = entry.isIntersecting || entry.boundingClientRect.top < 0
        setTriggered(pastTrigger)
      },
      {
        threshold: 0
      }
    )

    obs.observe(el)
    return () => obs.disconnect()
  }, [cta.showAfterId, cta.showAfterReason])

  const visible = triggered

  return (
    <div className={`${styles.wrap} ${visible ? styles.visible : ''}`} aria-hidden={!visible}>
      <Button href={cta.href} size="lg" className={styles.button}>
        {cta.label}
      </Button>
    </div>
  )
}
