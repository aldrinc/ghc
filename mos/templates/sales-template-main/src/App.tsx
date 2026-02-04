import { PdpPage } from './pages/PdpPage/PdpPage'
import { siteConfig } from './site/siteConfig'

export default function App() {
  return <PdpPage config={siteConfig.page} copy={siteConfig.copy} />
}
