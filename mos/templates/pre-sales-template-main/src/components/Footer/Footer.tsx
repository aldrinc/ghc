import type { Footer as FooterType } from '../../pages/ListiclePage/types'
import { Container } from '../Container/Container'
import styles from './Footer.module.css'

type Props = {
  footer: FooterType
}

export function Footer({ footer }: Props) {
  return (
    <footer className={styles.footer}>
      <Container>
        <div className={styles.inner}>
          <img className={styles.logo} src={footer.logo.src} alt={footer.logo.alt} loading="lazy" decoding="async" />
        </div>
      </Container>
    </footer>
  )
}
