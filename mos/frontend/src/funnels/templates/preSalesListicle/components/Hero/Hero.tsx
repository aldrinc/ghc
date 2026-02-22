import type { Badge, HeroMedia } from '../../types'
import { resolveAssetSrc, resolveImageSrc } from '../../utils/assetUtils'
import { BadgeRow } from '../BadgeRow/BadgeRow'
import styles from './Hero.module.css'

type Props = {
  title: string
  subtitle: string
  media?: HeroMedia
  badges: Badge[]
}

export function Hero({ title, subtitle, media, badges }: Props) {
  return (
    <header className={styles.hero}>
      <div className={styles.top}>
        <div className={styles.left}>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>{subtitle}</p>
        </div>

        <div className={styles.right}>
          {media ? (
            media.type === 'video' ? (
              <video
                className={styles.media}
                src={resolveAssetSrc(media.assetPublicId, media.srcMp4)}
                muted
                autoPlay
                loop
                playsInline
                controls={false}
                poster={resolveAssetSrc(media.posterAssetPublicId, media.poster)}
              />
            ) : (
              <img
                className={styles.media}
                src={resolveImageSrc(media)}
                alt={media.alt}
                loading="eager"
                decoding="async"
                fetchPriority="high"
              />
            )
          ) : (
            <div className={styles.mediaPlaceholder} aria-hidden="true" />
          )}
        </div>
      </div>

      <div className={styles.badgesBar}>
        <BadgeRow badges={badges} />
      </div>
    </header>
  )
}
