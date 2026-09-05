import { create } from 'zustand';
import { MetaResponse, RegionBox } from '../types/domain';
import { SavedPolygon, loadSavedPolygons } from '../features/map/savedPolygons';

export const DEFAULT_REGION_BOX: RegionBox = {
  min_lon: 38.3,
  min_lat: 46.8,
  max_lon: 41.3,
  max_lat: 49.3,
};

/**
 * Параметры сервиса на случай, когда бэкенд не поднят. Повторяют ответ
 * GET /meta, чтобы карта, валидация и выбор лет работали и без него:
 * иначе страница анализа без бэкенда мертва целиком.
 */
export const DEFAULT_META: MetaResponse = {
  region_box: DEFAULT_REGION_BOX,
  crop_types: ['озимая пшеница', 'зерновые', 'подсолнечник', 'пастбища/зерновые', 'неизвестно'],
  years: { min: 2010, max: 2025, default: [2016, 2025], min_span: 3 },
  max_area_ha: 5000,
  gee_available: false,
  typical_fetch_seconds: 60,
};

interface AppState {
  geometry: GeoJSON.Geometry | GeoJSON.Feature | null;
  setGeometry: (geom: GeoJSON.Geometry | GeoJSON.Feature | null) => void;

  meta: MetaResponse | null;
  setMeta: (meta: MetaResponse | null) => void;

  isOutsideRegion: boolean;
  setIsOutsideRegion: (val: boolean) => void;

  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  sidebarWide: boolean;
  setSidebarWide: (wide: boolean) => void;
  toggleSidebarWide: () => void;

  highlightPolygon: GeoJSON.Geometry | null;
  setHighlightPolygon: (geom: GeoJSON.Geometry | null) => void;

  /** Свёрнутое левое меню: карта на странице анализа лежит под ним, ширина важна разметке. */
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebarCollapsed: () => void;

  /**
   * Закладки участков и разборов. Лежат в сторе, а не в карте: сохранять
   * готовый разбор умеет панель анализа, а показывает список карта —
   * два владельца одного localStorage разъезжались бы между собой.
   */
  savedPolygons: SavedPolygon[];
  setSavedPolygons: (list: SavedPolygon[]) => void;
}

export const useAppStore = create<AppState>((set) => ({
  geometry: null,
  setGeometry: (geometry) => set({ geometry }),

  meta: null,
  setMeta: (meta) => set({ meta }),

  isOutsideRegion: false,
  setIsOutsideRegion: (isOutsideRegion) => set({ isOutsideRegion }),

  sidebarOpen: true,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  sidebarWide: false,
  setSidebarWide: (sidebarWide) => set({ sidebarWide }),
  toggleSidebarWide: () => set((state) => ({ sidebarWide: !state.sidebarWide })),

  highlightPolygon: null,
  setHighlightPolygon: (highlightPolygon) => set({ highlightPolygon }),

  sidebarCollapsed: false,
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebarCollapsed: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  savedPolygons: loadSavedPolygons(),
  setSavedPolygons: (savedPolygons) => set({ savedPolygons }),
}));
