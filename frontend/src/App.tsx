import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Candidates } from "./pages/Candidates";
import { Editor } from "./pages/Editor";
import { Ideas } from "./pages/Ideas";
import { ImportPage } from "./pages/Import";
import { Library } from "./pages/Library";
import { Metrics } from "./pages/Metrics";
import { Overview } from "./pages/Overview";
import { Recordings } from "./pages/Recordings";
import { SettingsPage } from "./pages/Settings";
import { Trends } from "./pages/Trends";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="trends" element={<Trends />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="recordings" element={<Recordings />} />
        <Route path="recordings/:id" element={<Recordings />} />
        <Route path="candidates" element={<Candidates />} />
        <Route path="candidates/:id" element={<Candidates />} />
        <Route path="editor" element={<Editor />} />
        <Route path="editor/:id" element={<Editor />} />
        <Route path="library" element={<Library />} />
        <Route path="ideas" element={<Ideas />} />
        <Route path="metrics" element={<Metrics />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Overview />} />
      </Route>
    </Routes>
  );
}
