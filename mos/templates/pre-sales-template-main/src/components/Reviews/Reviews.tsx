import type { Reviews as ReviewsType } from '../../pages/ListiclePage/types'
import { useEffect, useMemo, useState } from 'react'
import { Container } from '../Container/Container'
import { ArrowRightIcon } from '../Icons/ArrowRightIcon'
import { CheckIcon } from '../Icons/CheckIcon'
import { formatTemplate } from '../../utils/formatTemplate'
import type { UiCopy } from '../../site/types'
import styles from './Reviews.module.css'

type Props = {
  reviews: ReviewsType
  copy: UiCopy['reviews']
  starsAriaLabelTemplate: UiCopy['common']['starsAriaLabelTemplate']
}

type Direction = 'next' | 'prev'

export function Reviews({ reviews, copy, starsAriaLabelTemplate }: Props) {
  const [rawIndex, setRawIndex] = useState(0)
  const [direction, setDirection] = useState<Direction>('next')
  const [paused, setPaused] = useState(false)

  const total = reviews.slides.length

  const index = useMemo(() => {
    if (total === 0) return 0
    const mod = rawIndex % total
    return mod < 0 ? mod + total : mod
  }, [rawIndex, total])

  const active = reviews.slides[index]
  const autoAdvanceMs = reviews.autoAdvanceMs ?? 6500

  useEffect(() => {
    if (paused) return
    if (total <= 1) return

    const id = window.setTimeout(() => {
      setDirection('next')
      setRawIndex((i) => i + 1)
    }, autoAdvanceMs)

    return () => window.clearTimeout(id)
  }, [paused, total, autoAdvanceMs, index])

  if (total === 0) return null

  const images = active.images.slice(0, 3)
  const main = images[0]
  const side = images.slice(1)

  const goPrev = () => {
    setDirection('prev')
    setRawIndex((i) => i - 1)
  }

  const goNext = () => {
    setDirection('next')
    setRawIndex((i) => i + 1)
  }

  return (
    <section
      className={styles.section}
      aria-label={copy.sectionAriaLabel}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <Container>
        <div className={styles.carousel}>
          <button
            type="button"
            className={`${styles.nav} ${styles.prev}`}
            onClick={goPrev}
            aria-label={copy.prevButtonAriaLabel}
          >
            <ArrowRightIcon className={styles.navIcon} />
          </button>

          <div key={`${index}-${direction}`} className={`${styles.grid} ${direction === 'next' ? styles.enterNext : styles.enterPrev}`}>
            <div className={styles.card}>
              <div className={styles.quote} aria-hidden="true">
                “
              </div>

              <div
                className={styles.stars}
                aria-label={formatTemplate(starsAriaLabelTemplate, { rating: active.rating ?? 5 })}
              >
                {Array.from({ length: 5 }).map((_, i) => (
                  <span
                    key={i}
                    className={styles.star}
                    aria-hidden="true"
                    style={{ opacity: i < (active.rating ?? 5) ? 1 : 0.25 }}
                  >
                    ★
                  </span>
                ))}
              </div>

              <p className={styles.text}>{active.text}</p>

              <div className={styles.authorRow}>
                {active.verified ? (
                  <span className={styles.verified}>
                    <CheckIcon className={styles.verifiedIcon} />
                  </span>
                ) : null}
                <span className={styles.author}>{active.author}</span>
              </div>

              <div className={styles.dots} aria-label={copy.dotsAriaLabel}>
                {reviews.slides.map((_, i) => {
                  const isActive = i === index
                  return (
                    <button
                      key={i}
                      type="button"
                      className={`${styles.dot} ${isActive ? styles.dotActive : ''}`}
                      onClick={() => {
                        setDirection(i > index ? 'next' : 'prev')
                        setRawIndex(i)
                      }}
                      aria-label={formatTemplate(copy.goToReviewAriaLabelTemplate, { index: i + 1 })}
                    />
                  )
                })}
              </div>
            </div>

            <div className={styles.media}>
              {main ? (
                <img className={styles.mediaMain} src={main.src} alt={main.alt} loading="lazy" decoding="async" />
              ) : (
                <div className={styles.mediaPlaceholder} aria-hidden="true" />
              )}

              {side.map((img, idx) => (
                <img
                  key={`${img.src}-${idx}`}
                  className={styles.mediaSlim}
                  src={img.src}
                  alt={img.alt}
                  loading="lazy"
                  decoding="async"
                />
              ))}
            </div>
          </div>

          <button
            type="button"
            className={`${styles.nav} ${styles.next}`}
            onClick={goNext}
            aria-label={copy.nextButtonAriaLabel}
          >
            <ArrowRightIcon className={styles.navIcon} />
          </button>
        </div>
      </Container>
    </section>
  )
}
