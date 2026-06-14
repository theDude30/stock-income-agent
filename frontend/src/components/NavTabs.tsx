import { NavLink } from "react-router-dom";
import styles from "../styles/components.module.css";

const TABS = [
  { to: "/income", label: "Income" },
  { to: "/holdings", label: "Holdings" },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/performance", label: "Performance" },
  { to: "/settings", label: "Settings" },
];

export default function NavTabs() {
  return (
    <nav className={styles.nav}>
      {TABS.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          className={({ isActive }) => (isActive ? `${styles.tab} ${styles.active}` : styles.tab)}
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
