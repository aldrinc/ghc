import type { ReactNode } from 'react'
import { useEffect, useRef } from 'react'
import type { UiCopy } from '../../site/types'
import styles from './Modal.module.css'

type Props = {
  open: boolean
  onClose: () => void
  ariaLabel?: string
  copy: UiCopy['modal']
  children: ReactNode
}

export function Modal({ open, onClose, ariaLabel, copy, children }: Props) {
  const closeBtnRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', onKeyDown)

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Focus the close button for keyboard users.
    closeBtnRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className={styles.backdrop} role="presentation" onMouseDown={(e) => {
      if (e.target === e.currentTarget) onClose()
    }}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel ?? copy.dialogAriaLabel}
      >
        <button
          ref={closeBtnRef}
          type="button"
          className={styles.close}
          onClick={onClose}
          aria-label={copy.closeAriaLabel}
        >
          ×
        </button>

        <div className={styles.body}>{children}</div>
      </div>
    </div>
  )
}
