import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './tailwind.css'
import App from './App.tsx'
import { DEMO_MODE, installDemoTransport } from './demo/transport'

installDemoTransport(DEMO_MODE)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
