import { ConfigProvider } from "antd";
import ruRU from "antd/locale/ru_RU";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { buildTheme, CssVars, useDark } from "./theme";
import "./styles.css";

function Root() {
  const dark = useDark();
  return (
    <ConfigProvider locale={ruRU} theme={buildTheme(dark)}>
      <CssVars dark={dark} />
      <App />
    </ConfigProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
