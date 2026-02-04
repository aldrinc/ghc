import type { ReviewsWall as ReviewsWallType, WallReview } from '../../types'
import { useMemo, useState } from 'react'
import { Modal } from '../Modal/Modal'
import type { UiCopy } from '../../siteTypes'
import { resolveImageSrc } from '../../utils/assetUtils'
import styles from './ReviewWall.module.css'

type Props = {
  wall: ReviewsWallType
  modalCopy: UiCopy['modal']
}

function WallCard({ review, onSelect }: { review: WallReview; onSelect?: (review: WallReview) => void }) {
  if (!review.image) {
    return null
  }
  const image = (
    <img
      className={styles.cardImage}
      src={resolveImageSrc(review.image)}
      alt={review.image.alt}
      loading="lazy"
      decoding="async"
    />
  )

  if (onSelect) {
    return (
      <button
        type="button"
        className={`${styles.card} ${styles.cardButton}`}
        onClick={() => onSelect(review)}
      >
        {image}
      </button>
    )
  }

  return (
    <article className={styles.card}>
      {image}
    </article>
  )
}

function ReviewGrid({
  columns,
  ariaHidden = false,
  onSelect
}: {
  columns: WallReview[][]
  ariaHidden?: boolean
  onSelect?: (review: WallReview) => void
}) {
  return (
    <div className={styles.grid} aria-hidden={ariaHidden ? 'true' : undefined}>
      {columns.map((col, colIdx) => (
        <div key={colIdx} className={styles.column}>
          {col.map((r, i) => (
            <WallCard
              key={`${colIdx}-${i}`}
              review={r}
              onSelect={onSelect}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function ReviewWall({ wall, modalCopy }: Props) {
  const [open, setOpen] = useState(false)
  const [activeReview, setActiveReview] = useState<WallReview | null>(null)

  const columns = useMemo(() => wall.columns.filter((c) => c.length > 0), [wall.columns])
  const flatReviews = useMemo(() => columns.flat().filter((r) => r.image), [columns])

  const openReview = (review?: WallReview) => {
    const selected = review ?? flatReviews[0]
    if (!selected) return
    setActiveReview(selected)
    setOpen(true)
  }

  return (
    <section className={styles.section} aria-label={wall.title}>
      <h2 className={styles.title}>{wall.title}</h2>

      <button type="button" className={styles.viewButton} onClick={() => openReview()}>
        {wall.buttonLabel}
      </button>

      <div className={styles.preview}>
        <div className={styles.scroll}>
          <ReviewGrid
            columns={columns}
            onSelect={openReview}
          />
          <ReviewGrid
            columns={columns}
            ariaHidden
            onSelect={openReview}
          />
        </div>
      </div>

      <Modal
        open={open}
        onClose={() => {
          setOpen(false)
          setActiveReview(null)
        }}
        ariaLabel={wall.title}
        copy={modalCopy}
      >
        <div className={styles.modalWrap}>
          {activeReview ? <WallCard review={activeReview} /> : null}
        </div>
      </Modal>
    </section>
  )
}
