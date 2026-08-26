/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Placeholders — trocar pela identidade de marca depois.
        marca: {
          50: "#eef7ff",
          100: "#d9edff",
          500: "#1f7ae0",
          600: "#1662b8",
          900: "#0b2f5c",
        },
      },
    },
  },
  plugins: [],
};
