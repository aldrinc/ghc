import type { ReviewsWall as ReviewsWallType, WallReview } from '../../pages/ListiclePage/types'
import { useMemo, useState } from 'react'
import { CheckIcon } from '../Icons/CheckIcon'
import { Modal } from '../Modal/Modal'
import { formatTemplate } from '../../utils/formatTemplate'
import type { UiCopy } from '../../site/types'
import styles from './ReviewWall.module.css'

type Props = {
  wall: ReviewsWallType
  verifiedLabel: UiCopy['reviewWall']['verifiedLabel']
  starsAriaLabelTemplate: UiCopy['common']['starsAriaLabelTemplate']
  modalCopy: UiCopy['modal']
}

function Stars({ rating = 5, starsAriaLabelTemplate }: { rating?: number; starsAriaLabelTemplate: string }) {
  const safe = Math.max(0, Math.min(5, rating))
  return (
    <div className={styles.stars} aria-label={formatTemplate(starsAriaLabelTemplate, { rating: safe })}>
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={styles.star} aria-hidden="true">
          {i < safe ? '★' : '☆'}
        </span>
      ))}
    </div>
  )
}

function WallCard({
  review,
  verifiedLabel,
  starsAriaLabelTemplate
}: {
  review: WallReview
  verifiedLabel: string
  starsAriaLabelTemplate: string
}) {
  const image = review.image
  const imageTop = (review.imagePosition ?? 'top') === 'top'

  return (
    <article className={styles.card}>
      {image && imageTop ? (
        <img className={styles.cardImage} src={image.src} alt={image.alt} loading="lazy" decoding="async" />
      ) : null}

      <div className={styles.cardBody}>
        <div className={styles.cardHead}>
          <div className={styles.author}>{review.author}</div>
          {review.verified ? (
            <div className={styles.verified}>
              <CheckIcon className={styles.check} />
              <span>{verifiedLabel}</span>
            </div>
          ) : null}
        </div>

        {typeof review.rating === 'number' ? (
          <Stars rating={review.rating} starsAriaLabelTemplate={starsAriaLabelTemplate} />
        ) : null}
        <p className={styles.text}>{review.text}</p>
      </div>

      {image && !imageTop ? (
        <img className={styles.cardImage} src={image.src} alt={image.alt} loading="lazy" decoding="async" />
      ) : null}
    </article>
  )
}

function ReviewGrid({
  columns,
  verifiedLabel,
  starsAriaLabelTemplate,
  ariaHidden = false
}: {
  columns: WallReview[][]
  verifiedLabel: string
  starsAriaLabelTemplate: string
  ariaHidden?: boolean
}) {
  return (
    <div className={styles.grid} aria-hidden={ariaHidden ? 'true' : undefined}>
      {columns.map((col, colIdx) => (
        <div key={colIdx} className={styles.column}>
          {col.map((r, i) => (
            <WallCard
              key={`${colIdx}-${i}-${r.author}`}
              review={r}
              verifiedLabel={verifiedLabel}
              starsAriaLabelTemplate={starsAriaLabelTemplate}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function ReviewWall({ wall, verifiedLabel, starsAriaLabelTemplate, modalCopy }: Props) {
  const [open, setOpen] = useState(false)

  const columns = useMemo(() => wall.columns.filter((c) => c.length > 0), [wall.columns])

  return (
    <section className={styles.section} aria-label={wall.title}>
      <h2 className={styles.title}>{wall.title}</h2>

      <button type="button" className={styles.viewButton} onClick={() => setOpen(true)}>
        {wall.buttonLabel}
      </button>

      <div
        className={styles.preview}
        role="button"
        tabIndex={0}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') setOpen(true)
        }}
      >
        <div className={styles.scroll}>
          <ReviewGrid
            columns={columns}
            verifiedLabel={verifiedLabel}
            starsAriaLabelTemplate={starsAriaLabelTemplate}
          />
          <ReviewGrid
            columns={columns}
            verifiedLabel={verifiedLabel}
            starsAriaLabelTemplate={starsAriaLabelTemplate}
            ariaHidden
          />
        </div>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} ariaLabel={wall.title} copy={modalCopy}>
        <div className={styles.modalWrap}>
          <ReviewGrid
            columns={columns}
            verifiedLabel={verifiedLabel}
            starsAriaLabelTemplate={starsAriaLabelTemplate}
          />
        </div>
      </Modal>
    </section>
  )
}
