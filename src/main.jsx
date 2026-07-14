import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppPolished'
import './styles.css'
import './motion.css'
import './interaction.css'
import './auth-upload.css'
import './polish.css'

createRoot(document.getElementById('root')).render(
  <StrictMode><App /></StrictMode>,
)
