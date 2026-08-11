/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f6f7f9', 100: '#ebedf1', 200: '#d3d8e0', 300: '#adb6c4',
          400: '#808fa3', 500: '#617288', 600: '#4d5b70', 700: '#404a5b',
          800: '#37404d', 900: '#313843', 950: '#1d222b',
        },
      },
    },
  },
  plugins: [],
}
