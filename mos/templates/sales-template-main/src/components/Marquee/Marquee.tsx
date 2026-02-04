import styles from './Marquee.module.css'

type Props = {
  items: string[]
  /**
   * How many repeated groups to render.
   * Higher numbers help avoid visible gaps on ultra-wide screens.
   */
  repeat?: number
}

function MarqueeGroup({ items }: { items: string[] }) {
  return (
    <div className={styles.group} aria-hidden="true">
      {items.map((it, idx) => (
        <span key={`${it}-${idx}`} className={styles.item}>
          {it}
        </span>
      ))}
    </div>
  )
}

export function Marquee({ items, repeat = 2 }: Props) {
  const count = Math.max(2, Math.floor(repeat))
  return (
    <div className={styles.marquee} role="presentation">
      <div className={styles.viewport}>
        <div className={styles.track}>
          {Array.from({ length: count }).map((_, i) => (
            <MarqueeGroup key={i} items={items} />
          ))}
        </div>
      </div>
    </div>
  )
}
