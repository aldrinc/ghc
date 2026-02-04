import type { ReactNode } from 'react'
import { ArrowRightIcon } from '../Icons/ArrowRightIcon'
import styles from './Button.module.css'

type ButtonSize = 'lg' | 'sm'

type Props = {
  href: string
  children: ReactNode
  size?: ButtonSize
  className?: string
}

export function Button({ href, children, size = 'lg', className }: Props) {
  return (
    <a className={`${styles.shell} ${styles[size]} ${className ?? ''}`} href={href}>
      <span className={styles.inner}>
        <span className={styles.label}>{children}</span>
        <span className={styles.circle} aria-hidden="true">
          <ArrowRightIcon className={styles.icon} />
        </span>
      </span>
    </a>
  )
}
