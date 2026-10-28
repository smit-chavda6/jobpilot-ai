/** Design tokens live in src/index.css as CSS variables; Tailwind maps utilities onto them. */
/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: token("surface"),
        muted: token("muted"),
        border: token("border"),
        fg: token("fg"),
        subtle: token("subtle"),
        primary: token("primary"),
        "primary-fg": token("primary-fg"),
        success: token("success"),
        warning: token("warning"),
        danger: token("danger"),
        info: token("info"),
      },
      borderRadius: { sm: "var(--radius-sm)", DEFAULT: "var(--radius)", lg: "var(--radius-lg)" },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"] },
      fontSize: {
        xs: ["0.75rem", "1rem"],
        sm: ["0.875rem", "1.25rem"],
        base: ["1rem", "1.5rem"],
        lg: ["1.125rem", "1.75rem"],
        xl: ["1.25rem", "1.75rem"],
        "2xl": ["1.5rem", "2rem"],
      },
    },
  },
  plugins: [],
};
