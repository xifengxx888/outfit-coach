import { useEffect, useRef, useState } from "react";
import { fetchSetup } from "./api.js";
import { AddPage } from "./pages/AddPage.jsx";
import { ClosetPage } from "./pages/ClosetPage.jsx";
import { OutfitsPage } from "./pages/OutfitsPage.jsx";
import { TodayPage } from "./pages/TodayPage.jsx";
import { GapsPage } from "./pages/GapsPage.jsx";
import { ItemDetailPage } from "./pages/ItemDetailPage.jsx";
import { EditPage } from "./pages/EditPage.jsx";
import { AnchorPage } from "./pages/AnchorPage.jsx";
import { SetupPage } from "./pages/SetupPage.jsx";
import { SettingsPage } from "./pages/SettingsPage.jsx";
import { TheoryPage } from "./pages/TheoryPage.jsx";

const TABS = [
  { path: "/closet", label: "衣库" },
  { path: "/outfits", label: "组合" },
  { path: "/today", label: "今日" },
  { path: "/settings", label: "我的" },
];

const STATIC_ROUTES = [
  "/closet",
  "/add",
  "/outfits",
  "/today",
  "/gaps",
  "/setup",
  "/settings",
  "/theory",
];

function currentRoute() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (STATIC_ROUTES.includes(path)) return path;
  // 动态路由只认数字 id；其余未知路径仍回衣库
  if (/^\/item\/\d+(\/edit)?$/.test(path)) return path;
  if (/^\/anchor\/\d+$/.test(path)) return path;
  return "/closet";
}

function HangerIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10 2.4a2 2 0 0 1 2 2c0 .84-.52 1.56-1.25 1.86L10 6.9" />
      <path d="M10 6.9 3.2 11.6c-.9.6-.48 2 .6 2h12.4c1.08 0 1.5-1.4.6-2L10 6.9Z" />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="11" y="3" width="6" height="6" rx="1" />
      <rect x="3" y="11" width="6" height="6" rx="1" />
      <rect x="11" y="11" width="6" height="6" rx="1" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 2.2v1.8M10 16v1.8M2.2 10H4M16 10h1.8M4.5 4.5l1.3 1.3M14.2 14.2l1.3 1.3M15.5 4.5l-1.3 1.3M5.8 14.2l-1.3 1.3" />
    </svg>
  );
}

function PersonIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="10" cy="6.6" r="3" />
      <path d="M4.2 16.6c.7-2.9 3-4.4 5.8-4.4s5.1 1.5 5.8 4.4" />
    </svg>
  );
}

const ICONS = {
  "/closet": HangerIcon,
  "/outfits": GridIcon,
  "/today": SunIcon,
  "/settings": PersonIcon,
};

const TITLES = {
  "/closet": "衣库",
  "/add": "加一件",
  "/outfits": "组合",
  "/today": "今日",
  "/gaps": "缺口",
  "/setup": "首次设置",
  "/settings": "我的",
  "/theory": "搭配原理",
};

function routeTitle(route) {
  if (/^\/item\/\d+\/edit$/.test(route)) return "编辑";
  if (/^\/item\/\d+$/.test(route)) return "单品";
  if (/^\/anchor\/\d+$/.test(route)) return "锚定搭配";
  return TITLES[route] ?? "衣库";
}

export function App() {
  const [route, setRoute] = useState(currentRoute);
  // 单品详情记下是从哪一页点进来的，返回按钮才能回到来路
  const itemOrigins = useRef({});

  useEffect(() => {
    const onPop = () => setRoute(currentRoute());
    window.addEventListener("popstate", onPop);
    // 从 / 进来时把地址栏换成 /closet，刷新后停在同一个 tab
    if (window.location.pathname === "/") {
      window.history.replaceState(null, "", "/closet");
    }

    // 只在从 /closet 首次进入时引导；深链（/today、/item/:id）不劫持
    let active = true;
    const path = window.location.pathname.replace(/\/+$/, "") || "/";
    if (path === "/closet") {
      fetchSetup()
        .then((info) => {
          if (!active || !info.needs_setup) return;
          const now = window.location.pathname.replace(/\/+$/, "") || "/";
          if (now !== "/closet") return;
          window.history.replaceState(null, "", "/setup");
          setRoute("/setup");
        })
        .catch(() => {
          // 读不到设置状态就按正常首页走，不拦住用户
        });
    }

    return () => {
      active = false;
      window.removeEventListener("popstate", onPop);
    };
  }, []);

  useEffect(() => {
    document.title = `${routeTitle(route)} · 个人穿搭助手`;
  }, [route]);

  const go = (path) => {
    if (path === route) return;
    window.history.pushState(null, "", path);
    setRoute(path);
    window.scrollTo(0, 0);
  };

  const detailMatch = route.match(/^\/item\/(\d+)$/);
  const editMatch = route.match(/^\/item\/(\d+)\/edit$/);
  const anchorMatch = route.match(/^\/anchor\/(\d+)$/);
  const openItem = (id) => {
    itemOrigins.current[id] = route;
    go(`/item/${id}`);
  };

  const BACK_LABELS = {
    "/closet": "衣库",
    "/outfits": "组合",
    "/today": "今日",
  };
  const detailOrigin = detailMatch
    ? itemOrigins.current[detailMatch[1]] ?? "/closet"
    : "/closet";

  let page = <ClosetPage onAdd={() => go("/add")} onOpenItem={openItem} />;
  if (route === "/outfits") {
    page = (
      <OutfitsPage
        onGaps={() => go("/gaps")}
        onOpenItem={openItem}
        onSettings={() => go("/settings")}
      />
    );
  }
  if (route === "/today") {
    page = (
      <TodayPage
        onOpenItem={openItem}
        onSettings={() => go("/settings")}
        onGaps={() => go("/gaps")}
        onCloset={() => go("/closet")}
      />
    );
  }
  if (route === "/settings") {
    page = <SettingsPage onTheory={() => go("/theory")} />;
  }
  if (route === "/theory") {
    page = <TheoryPage onBack={() => go("/settings")} />;
  }
  if (route === "/setup") {
    page = (
      <SetupPage
        onDone={() => go("/closet")}
        onToday={() => go("/today")}
        onSettings={() => go("/settings")}
      />
    );
  }
  if (route === "/gaps") {
    page = (
      <GapsPage
        onBack={() => go("/outfits")}
        onAdd={() => go("/add")}
      />
    );
  }
  if (route === "/add") {
    page = <AddPage onBack={() => go("/closet")} onCloset={() => go("/closet")} />;
  }
  if (detailMatch) {
    page = (
      <ItemDetailPage
        itemId={Number(detailMatch[1])}
        onBack={() => go(detailOrigin)}
        backLabel={BACK_LABELS[detailOrigin] ?? "衣库"}
        onEdit={(id) => go(`/item/${id}/edit`)}
        onAnchor={(id) => go(`/anchor/${id}`)}
      />
    );
  }
  if (editMatch) {
    const id = Number(editMatch[1]);
    page = (
      <EditPage
        itemId={id}
        onBack={() => go(`/item/${id}`)}
        onSaved={() => go(`/item/${id}`)}
      />
    );
  }
  if (anchorMatch) {
    const id = Number(anchorMatch[1]);
    page = (
      <AnchorPage
        itemId={id}
        onBack={() => go(`/item/${id}`)}
        onEdit={(itemId) => go(`/item/${itemId}/edit`)}
        onGaps={() => go("/gaps")}
        onSettings={() => go("/settings")}
      />
    );
  }

  return (
    <div className={`app${route === "/setup" ? " app-no-tab" : ""}`}>
      {page}

      {route !== "/setup" && (
        <nav className="tabbar" aria-label="主导航">
          {TABS.map((tab) => {
            const Icon = ICONS[tab.path];
            const active = route === tab.path;
            return (
              <button
                key={tab.path}
                type="button"
                className={`tab${active ? " is-active" : ""}`}
                aria-current={active ? "page" : undefined}
                onClick={() => go(tab.path)}
              >
                <Icon />
                {tab.label}
              </button>
            );
          })}
        </nav>
      )}
    </div>
  );
}
