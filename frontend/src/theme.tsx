import { theme as antdTheme, type ThemeConfig } from "antd";
import { useEffect, useState } from "react";

const DARK_QUERY = "(prefers-color-scheme: dark)";

// Follow the system colour scheme.
export function useDark(): boolean {
  const [dark, setDark] = useState(() => window.matchMedia(DARK_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(DARK_QUERY);
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return dark;
}

export function buildTheme(dark: boolean): ThemeConfig {
  return {
    algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      // Ink blue for actions; red, amber and green are reserved for severity and verdict.
      colorPrimary: dark ? "#8aa2ff" : "#2f54eb",
      colorInfo: dark ? "#8aa2ff" : "#2f54eb",
      colorLink: dark ? "#8aa2ff" : "#2f54eb",
      colorError: dark ? "#ff7a8c" : "#cf1f3d",
      colorWarning: dark ? "#f0b45c" : "#d4820f",
      colorSuccess: dark ? "#6bd0a3" : "#2e8b62",
      // The generated green tint is too grey; set a clean one for tags and "how to fix" blocks.
      colorSuccessBg: dark ? "#14302a" : "#e9f6ef",
      colorSuccessBorder: dark ? "#2b5c4b" : "#a8dcc2",
      colorBgLayout: dark ? "#10141b" : "#f3f5f9",
      colorTextBase: dark ? "#e6e9ef" : "#17223a",
      fontFamily: '"Golos Text", "Segoe UI", system-ui, sans-serif',
      borderRadius: 8,
    },
    components: {
      Layout: { headerBg: dark ? "#171c25" : "#ffffff", headerHeight: 56, headerPadding: "0 20px" },
      Menu: { itemHeight: 44, itemBorderRadius: 8, activeBarBorderWidth: 0 },
    },
  };
}

// Mirror antd tokens into CSS variables so hand-written styles follow the same theme.
export function CssVars({ dark }: { dark: boolean }) {
  const { token } = antdTheme.useToken();
  useEffect(() => {
    const vars: Record<string, string> = {
      "--bg": token.colorBgLayout,
      "--paper": token.colorBgContainer,
      "--ink": token.colorText,
      "--muted": token.colorTextSecondary,
      "--faint": token.colorTextTertiary,
      "--rule": token.colorBorderSecondary,
      "--rule-strong": token.colorBorder,
      "--wash": token.colorFillQuaternary,
      "--wash-strong": token.colorFillTertiary,
      "--primary": token.colorPrimary,
      "--primary-wash": token.colorPrimaryBg,
      "--primary-rule": token.colorPrimaryBorder,
      "--critical": token.colorError,
      "--critical-wash": token.colorErrorBg,
      "--critical-rule": token.colorErrorBorder,
      "--major": token.colorWarning,
      "--major-wash": token.colorWarningBg,
      "--major-rule": token.colorWarningBorder,
      "--ok": token.colorSuccess,
      "--ok-wash": token.colorSuccessBg,
      "--ok-rule": token.colorSuccessBorder,
      "--radius": `${token.borderRadius}px`,
      "--mark": dark ? "#5a4d12" : "#fff1a8",
    };
    const root = document.documentElement;
    for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
    root.style.colorScheme = dark ? "dark" : "light";
  }, [token, dark]);
  return null;
}
