import type { Reason } from '../../pages/ListiclePage/types'
import { Container } from '../Container/Container'
import styles from './Reasons.module.css'

type Props = {
  reasons: Reason[]
}

export function Reasons({ reasons }: Props) {
  return (
    <section className={styles.section}>
      <Container>
        <ol className={styles.list}>
          {reasons.map((r) => (
            <li key={r.number} id={`reason-${r.number}`} className={styles.card}>
              <div className={styles.media}>
                <div className={styles.number} aria-hidden="true">
                  {r.number}
                </div>

                {r.image ? (
                  <img
                    className={styles.image}
                    src={r.image.src}
                    alt={r.image.alt}
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <div className={styles.placeholder} aria-hidden="true" />
                )}
              </div>

              <div className={styles.content}>
                <h3 className={styles.title}>{r.title}</h3>
                <p className={styles.body}>{r.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <div id="listicle-end" className={styles.endSentinel} aria-hidden="true" />
      </Container>
    </section>
  )
}
