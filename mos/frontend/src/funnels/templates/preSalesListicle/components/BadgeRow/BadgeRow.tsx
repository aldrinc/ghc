import type { Badge } from '../../types'
import { resolveAssetSrc } from '../../utils/assetUtils'
import styles from './BadgeRow.module.css'

export function BadgeRow({ badges }: { badges: Badge[] }) {
  return (
    <div className={styles.row}>
      {badges.map((b) => (
        <div key={`${b.label}-${b.value ?? ''}`} className={styles.badge}>
          <div className={styles.iconFrame}>
            <img
              className={styles.icon}
              src={resolveAssetSrc(b.iconAssetPublicId, b.iconSrc)}
              alt={b.iconAlt}
              loading="eager"
              decoding="async"
            />
          </div>
          <div className={styles.text}>
            {b.value ? <span className={styles.value}>{b.value}</span> : null}
            <span className={styles.label}>{b.label}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
