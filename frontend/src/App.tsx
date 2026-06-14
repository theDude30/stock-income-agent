import { Routes, Route, Navigate } from "react-router-dom";

import NavTabs from "./components/NavTabs";
import IncomeOverview from "./pages/IncomeOverview";
import Holdings from "./pages/Holdings";
import Recommendations from "./pages/Recommendations";
import Performance from "./pages/Performance";
import Settings from "./pages/Settings";
import styles from "./styles/components.module.css";

export default function App() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <h1 className={styles.title}>Stock Income Agent</h1>
        <NavTabs />
      </header>
      <main className={styles.main}>
        <Routes>
          <Route path="/" element={<Navigate to="/income" replace />} />
          <Route path="/income" element={<IncomeOverview />} />
          <Route path="/holdings" element={<Holdings />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
