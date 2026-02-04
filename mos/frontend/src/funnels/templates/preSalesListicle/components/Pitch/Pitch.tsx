import type { Pitch as PitchType } from '../../types'
import { resolveImageSrc } from '../../utils/assetUtils'
import { Container } from '../Container/Container'
import { Button } from '../Button/Button'
import { CheckIcon } from '../Icons/CheckIcon'
import styles from './Pitch.module.css'

type Props = {
  pitch: PitchType
}

function renderBold(text: string) {
  const chunks = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean)
  return chunks.map((chunk, idx) => {
    const match = chunk.match(/^\*\*([^*]+)\*\*$/)
    if (match) return <strong key={idx}>{match[1]}</strong>
    return <span key={idx}>{chunk}</span>
  })
}

export function Pitch({ pitch }: Props) {
  return (
    <section className={styles.section}>
      <Container>
        <div className={styles.grid}>
          <div className={styles.content}>
            <h2 className={styles.title}>{pitch.title}</h2>
            <ul className={styles.bullets}>
              {pitch.bullets.map((b) => (
                <li key={b} className={styles.bullet}>
                  <span className={styles.checkWrap} aria-hidden="true">
                    <CheckIcon className={styles.check} />
                  </span>
                  <span className={styles.bulletText}>{renderBold(b)}</span>
                </li>
              ))}
            </ul>

            {pitch.cta ? (
              <Button linkType={pitch.cta.linkType} href={pitch.cta.href} targetPageId={pitch.cta.targetPageId}>
                {pitch.cta.label}
              </Button>
            ) : null}
          </div>

          <div className={styles.mediaFrame}>
            <img
              className={styles.mediaImg}
              src={resolveImageSrc(pitch.image)}
              alt={pitch.image.alt}
              loading="lazy"
              decoding="async"
            />
          </div>
        </div>
      </Container>
    </section>
  )
}
