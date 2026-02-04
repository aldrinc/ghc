import { ListiclePage } from './pages/ListiclePage/ListiclePage'
import { siteConfig } from './site/siteConfig'

export default function App() {
  return <ListiclePage config={siteConfig.page} copy={siteConfig.copy} />
}
