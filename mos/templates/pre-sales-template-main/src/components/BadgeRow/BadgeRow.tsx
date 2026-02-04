import type { Badge } from '../../pages/ListiclePage/types'
import styles from './BadgeRow.module.css'

export function BadgeRow({ badges }: { badges: Badge[] }) {
  return (
    <div className={styles.row}>
      {badges.map((b) => (
        <div key={`${b.label}-${b.value ?? ''}`} className={styles.badge}>
          <img
            className={styles.icon}
            src={b.iconSrc}
            alt={b.iconAlt}
            loading="eager"
            decoding="async"
          />
          <div className={styles.text}>
            {b.value ? <span className={styles.value}>{b.value}</span> : null}
            <span className={styles.label}>{b.label}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
