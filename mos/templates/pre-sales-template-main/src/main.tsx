import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { applySiteConfig } from './site/applySiteConfig'
import { siteConfig } from './site/siteConfig'

import './theme/tokens.css'
import './styles/global.css'

// Apply theme/meta before React renders to minimize layout/flash.
applySiteConfig(siteConfig)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
