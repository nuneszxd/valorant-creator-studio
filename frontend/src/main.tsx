import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { JobsProvider } from "./components/JobsContext";
import { ToastProvider } from "./components/Toast";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <JobsProvider>
          <App />
        </JobsProvider>
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
