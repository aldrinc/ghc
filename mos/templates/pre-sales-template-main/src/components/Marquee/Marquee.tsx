import styles from './Marquee.module.css'

type Props = {
  items: string[]
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

export function Marquee({ items }: Props) {
  return (
    <div className={styles.marquee} role="presentation">
      <div className={styles.viewport}>
        <div className={styles.track}>
          <MarqueeGroup items={items} />
          <MarqueeGroup items={items} />
        </div>
      </div>
    </div>
  )
}
