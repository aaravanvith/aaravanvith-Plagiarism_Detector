/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#F5F6FA",
          100: "#E7E9F2",
          200: "#C7CCDF",
          400: "#5C6688",
          600: "#2C3557",
          800: "#182142",
          900: "#0F1730",
        },
        seal: {
          400: "#D9AA4E",
          500: "#C9962C",
          600: "#A97A1E",
        },
        risk: {
          high: "#B23A48",
          highBg: "#FBEAEC",
          medium: "#B8862F",
          mediumBg: "#FBF1E0",
          low: "#2F7A5C",
          lowBg: "#E8F4EE",
        },
        paper: "#F7F8FB",
      },
      fontFamily: {
        display: ['"Source Serif 4"', "Georgia", "serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
    },
  },
  plugins: [],
};
