import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        veil: {
          50: '#f0f2ff',
          100: '#dde1ff',
          200: '#bac0ff',
          300: '#9AA5FF',   // Glow
          400: '#7C8BF5',   // Accent
          500: '#5B6BC0',   // Blue (primary brand)
          600: '#4A5090',   // Indigo
          700: '#3A4080',
          800: '#1A1F36',   // Navy
          900: '#111527',   // Deep
          950: '#0B0E17',   // Midnight
        },
      },
      fontFamily: {
        display: ['Outfit', 'sans-serif'],
        body: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
export default config
