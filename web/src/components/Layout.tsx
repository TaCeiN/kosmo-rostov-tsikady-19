import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Satellite,
  WifiOff,
  FileSpreadsheet,
  CalendarDays,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { fetchHealth, fetchMeta } from '../api/client';
import { useAppStore } from '../lib/store';

type BackendStatus = 'checking' | 'ok' | 'gee_off' | 'offline';

// Подписи индикатора в подвале. Оффлайн здесь не ошибка:
// демо-режим и метрики целиком работают на статике из data/.
const STATUS_META: Record<BackendStatus, { label: string; dotClass: string; title: string }> = {
  checking: {
    label: 'Проверка сервиса',
    dotClass: 'bg-white/40 animate-pulse',
    title: 'Опрашиваем бэкенд',
  },
  ok: {
    label: 'Сервис онлайн',
    dotClass: 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.9)]',
    title: 'Бэкенд доступен, Earth Engine активен',
  },
  gee_off: {
    label: 'Без Earth Engine',
    dotClass: 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.9)]',
    title: 'Бэкенд поднят, но Earth Engine не настроен: спутниковый анализ недоступен',
  },
  offline: {
    label: 'Оффлайн режим',
    dotClass: 'bg-white/30',
    title: 'Бэкенд не поднят. Демо на 78 полях и метрики работают на статике',
  },
};

export const Layout: React.FC = () => {
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebarCollapsed } = useAppStore();

  // Страница анализа — карта во весь экран, меню лежит поверх неё
  const isMapPage = location.pathname === '/';

  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking');
  const [featureCount, setFeatureCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function checkStatus() {
      try {
        // Опорой служит именно /meta: на 8000 может отвечать посторонний
        // сервис, у которого тоже есть /health, а вот наш формат /meta
        // подделать нечем. Плюс он сразу приносит признак доступности GEE.
        const meta = await fetchMeta();
        if (cancelled) return;
        setBackendStatus(meta.gee_available ? 'ok' : 'gee_off');
      } catch {
        if (!cancelled) setBackendStatus('offline');
        return;
      }

      // Число признаков модели — деталь для подписи, её отсутствие не повод
      // считать сервис лежащим
      try {
        const health = await fetchHealth();
        if (!cancelled && typeof health.features === 'number') {
          setFeatureCount(health.features);
        }
      } catch {
        // остаётся значение по умолчанию
      }
    }

    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const status = STATUS_META[backendStatus];

  const navItems = [
    {
      to: '/',
      label: 'Спутниковый анализ',
      description: 'Карта, поиск полей, расчёт',
      icon: Satellite,
    },
    {
      to: '/demo',
      label: 'Оффлайн режим',
      description: '78 эталонных полей',
      icon: WifiOff,
    },
    {
      to: '/predict',
      label: 'CSV инференс',
      description: 'Пакетная обработка рядов',
      icon: FileSpreadsheet,
    },
    {
      to: '/calendar',
      label: 'Календарь аномалий',
      description: 'Весь регион по месяцам',
      icon: CalendarDays,
    },
  ];

  return (
    <div className="h-screen w-screen overflow-hidden relative bg-black font-sans text-slate-900 select-none">
      {/* Left Sidebar: overlaying on top of map with ~35% transparency (65% opacity) */}
      <aside
        className={`fixed top-0 left-0 bottom-0 z-[500] flex flex-col bg-black/65 backdrop-blur-md border-r border-white/10 text-white shadow-2xl select-text transition-all duration-300 ease-in-out ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        {/* Brand Header & Collapse Toggle */}
        <div
          className={`border-b border-white/10 bg-white/[0.03] transition-all duration-300 ${
            sidebarCollapsed
              ? 'p-3 flex flex-col items-center gap-2'
              : 'p-4 flex items-center justify-between gap-2'
          }`}
        >
          <div className={`flex items-center gap-3 min-w-0 ${sidebarCollapsed ? 'justify-center' : ''}`}>
            <img
              src="/logo.png"
              alt="NDVI Монитор"
              className="w-10 h-10 object-contain shrink-0 drop-shadow-[0_0_10px_rgba(96,165,250,0.35)]"
            />
            {!sidebarCollapsed && (
              <div className="min-w-0 flex-1">
                <div className="font-extrabold text-white text-sm tracking-tight leading-tight truncate">
                  NDVI Монитор
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={toggleSidebarCollapsed}
            className={`p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition-colors shrink-0 ${
              sidebarCollapsed ? 'mt-1' : ''
            }`}
            title={sidebarCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
          >
            {sidebarCollapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Navigation */}
        <div className={`pt-4 pb-2 flex-1 overflow-y-auto ${sidebarCollapsed ? 'px-2' : 'px-3'}`}>
          {!sidebarCollapsed && (
            <div className="text-[10px] font-bold text-white/40 uppercase tracking-widest px-3 mb-2.5">
              Страницы сайта
            </div>
          )}

          <nav className="space-y-1.5">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  title={sidebarCollapsed ? `${item.label} — ${item.description}` : undefined}
                  className={({ isActive }) =>
                    `flex items-center rounded-xl text-xs font-semibold transition-all group ${
                      sidebarCollapsed
                        ? `justify-center p-2.5 ${
                            isActive
                              ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/40 border border-blue-400/40'
                              : 'text-white/70 hover:text-white hover:bg-white/10 border border-transparent'
                          }`
                        : `gap-3 px-3 py-2.5 ${
                            isActive
                              ? 'bg-blue-600/20 text-white border border-blue-500/40 shadow-lg shadow-blue-950/50 backdrop-blur-sm'
                              : 'text-white/70 hover:text-white hover:bg-white/[0.07] border border-transparent'
                          }`
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <div
                        className={`rounded-lg flex items-center justify-center transition-all shrink-0 ${
                          sidebarCollapsed
                            ? 'w-6 h-6'
                            : `w-8 h-8 ${
                                isActive
                                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/40'
                                  : 'bg-white/[0.06] text-white/70 group-hover:text-white group-hover:bg-white/[0.12] border border-white/10'
                              }`
                        }`}
                      >
                        <Icon className={sidebarCollapsed ? 'w-5 h-5' : 'w-4 h-4'} />
                      </div>
                      {!sidebarCollapsed && (
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-xs font-bold leading-tight">
                            {item.label}
                          </div>
                          <div
                            className={`text-[10px] truncate mt-0.5 ${
                              isActive
                                ? 'text-blue-200/90 font-medium'
                                : 'text-white/45 group-hover:text-white/65 font-normal'
                            }`}
                          >
                            {item.description}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Footer: живой статус бэкенда */}
        <div
          className={`border-t border-white/10 bg-black/40 text-[11px] text-white/60 transition-all duration-300 ${
            sidebarCollapsed
              ? 'p-3 flex justify-center'
              : 'p-3.5 flex items-center justify-between'
          }`}
          title={`${status.title}${sidebarCollapsed ? ` • LightGBM ${featureCount ?? 106}` : ''}`}
        >
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full inline-block ${status.dotClass}`} />
            {!sidebarCollapsed && (
              <span className="text-white/80 font-medium">{status.label}</span>
            )}
          </div>
          {!sidebarCollapsed && (
            <span className="font-mono text-[10px] text-white/50 bg-white/5 px-2 py-0.5 rounded border border-white/10">
              LightGBM • {featureCount ?? 106}
            </span>
          )}
        </div>
      </aside>

      {/* Main Area: Renders the active page */}
      <main
        className={`w-full h-full overflow-hidden transition-all duration-300 ${
          isMapPage
            ? 'absolute inset-0 z-0'
            : `relative bg-slate-100 z-10 ${sidebarCollapsed ? 'pl-20' : 'pl-64'}`
        }`}
      >
        <Outlet />
      </main>
    </div>
  );
};
