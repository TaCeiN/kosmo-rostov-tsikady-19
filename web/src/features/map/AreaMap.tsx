import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  MapContainer,
  TileLayer,
  Polygon,
  useMap,
  useMapEvents,
  ZoomControl,
} from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { RegionBox } from '../../types/domain';
import {
  BarChart3,
  Bookmark,
  Layers,
  Loader2,
  Map,
  MapPin,
  Plus,
  Satellite,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';
import { formatArea } from '../../lib/formatters';
import { useAppStore } from '../../lib/store';
import {
  FarmlandContour,
  FarmlandSearchError,
  findFarmlandContours,
} from './farmland';
import {
  SavedPolygon,
  addSavedPolygon,
  appendSavedPolygons,
  parseGeoJsonUpload,
  removeSavedPolygon,
  sameRing,
  toPolygon,
} from './savedPolygons';
import rostovGeoJson from '../../data/rostov_oblast.json';
import krasnodarGeoJson from '../../data/krasnodar_krai.json';
import volgogradGeoJson from '../../data/volgograd_oblast.json';

// Административные границы в порядке Leaflet [lat, lon]
const rostovPolygon: [number, number][] = (rostovGeoJson.coordinates[0] as [number, number][]).map(
  ([lon, lat]) => [lat, lon]
);

const krasnodarPolygon: [number, number][] = (krasnodarGeoJson.coordinates[0] as [number, number][]).map(
  ([lon, lat]) => [lat, lon]
);

const volgogradPolygon: [number, number][] = (volgogradGeoJson.coordinates[0] as [number, number][]).map(
  ([lon, lat]) => [lat, lon]
);

// Leaflet ищет иконки маркеров по относительному пути, который сборка Vite ломает
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

/** Больше этого числа вершин руками не двигают — такой контур показываем как есть. */
const MAX_EDITABLE_POINTS = 12;

/** Минимум вершин, из которых складывается площадь. */
const MIN_POINTS = 3;

interface AreaMapProps {
  regionBox: RegionBox;
  geometry: GeoJSON.Geometry | GeoJSON.Feature | null;
  onChangeGeometry: (geom: GeoJSON.Geometry | GeoJSON.Feature | null) => void;
  isOutsideRegion?: boolean;
  onPointsCountChange?: (count: number) => void;
  /**
   * Сохранение закладки берёт на себя страница: когда разбор уже посчитан,
   * в закладку кладётся он, а не голый контур.
   */
  onSaveCurrent?: () => void;
  /** Подпись кнопки сохранения: «В список» или «Сохранить разбор». */
  saveLabel?: string;
  /** Клик по закладке в списке: перелёт к участку и восстановление разбора. */
  onPickSaved?: (entry: SavedPolygon) => void;
  /** Клик по периметру на карте: открыть карточку поля на весь экран. */
  onOpenSavedField?: (entry: SavedPolygon) => void;
}

/**
 * Сортирует точки по углу вокруг центра: без этого клики в произвольном
 * порядке дают самопересекающийся контур с неверной площадью.
 */
function orderPointsClockwise(pts: [number, number][]): [number, number][] {
  if (pts.length < 3) return pts;
  const centerLat = pts.reduce((sum, p) => sum + p[0], 0) / pts.length;
  const centerLng = pts.reduce((sum, p) => sum + p[1], 0) / pts.length;

  return [...pts].sort((a, b) => {
    const angleA = Math.atan2(a[0] - centerLat, a[1] - centerLng);
    const angleB = Math.atan2(b[0] - centerLat, b[1] - centerLng);
    return angleA - angleB;
  });
}

function createNumberIcon(num: number) {
  return L.divIcon({
    className: 'custom-point-marker',
    html: `<div style="
      background: #2563eb;
      color: #ffffff;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 13px;
      box-shadow: 0 3px 8px rgba(0,0,0,0.4);
      border: 2.5px solid #ffffff;
      cursor: grab;
      user-select: none;
      line-height: 1;
    ">${num}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

/** Клики по карте, перетаскивание вершин и отрисовка контура из точек. */
const PointPlacementController: React.FC<{
  points: [number, number][];
  setPoints: React.Dispatch<React.SetStateAction<[number, number][]>>;
  onChangeGeometry: (geom: GeoJSON.Geometry | GeoJSON.Feature | null) => void;
  isOutsideRegion?: boolean;
  enabled: boolean;
}> = ({ points, setPoints, onChangeGeometry, isOutsideRegion, enabled }) => {
  const map = useMap();
  const layerGroupRef = useRef<L.LayerGroup>(new L.LayerGroup());

  useEffect(() => {
    const lg = layerGroupRef.current;
    map.addLayer(lg);
    return () => {
      map.removeLayer(lg);
    };
  }, [map]);

  useMapEvents({
    click(e) {
      if (!enabled) return;

      const newLat = e.latlng.lat;
      const newLng = e.latlng.lng;

      setPoints((prev) => {
        // Раньше пятый клик сбрасывал контур: поля прямоугольны далеко не всегда,
        // поэтому набираем произвольное число вершин до разумного предела.
        if (prev.length >= MAX_EDITABLE_POINTS) return prev;
        return [...prev, [newLat, newLng]];
      });
    },
  });

  useEffect(() => {
    const lg = layerGroupRef.current;
    lg.clearLayers();

    if (points.length === 0) return;

    // Вершины: каждую можно перетащить, номер показывает порядок постановки
    points.forEach((pt, idx) => {
      const marker = L.marker(pt, {
        icon: createNumberIcon(idx + 1),
        draggable: true,
      });

      marker.on('drag', (e: any) => {
        const pos = e.target.getLatLng();
        setPoints((curr) => {
          const next = [...curr] as [number, number][];
          next[idx] = [pos.lat, pos.lng];
          return next;
        });
      });

      // Правый клик убирает лишнюю вершину, не сбрасывая весь контур
      marker.on('contextmenu', () => {
        setPoints((curr) => curr.filter((_, i) => i !== idx));
      });

      lg.addLayer(marker);
    });

    if (points.length === 1) return;

    if (points.length === 2) {
      lg.addLayer(
        L.polyline(points, { color: '#2563eb', weight: 3, dashArray: '4, 6' })
      );
      return;
    }

    // От трёх вершин контур уже замкнут и годится для анализа
    const ordered = orderPointsClockwise(points);
    lg.addLayer(
      L.polygon(ordered, {
        color: isOutsideRegion ? '#f59e0b' : '#1d4ed8',
        weight: 3,
        fillColor: isOutsideRegion ? '#f59e0b' : '#2563eb',
        fillOpacity: 0.35,
      })
    );

    const ring: [number, number][] = ordered.map((p) => [p[1], p[0]]); // [lon, lat]
    const first = ordered[0];
    if (first) ring.push([first[1], first[0]]); // замыкаем кольцо

    onChangeGeometry({ type: 'Polygon', coordinates: [ring] } as GeoJSON.Polygon);
  }, [points, isOutsideRegion, onChangeGeometry, setPoints]);

  return null;
};

/**
 * Показывает выбранный контур, который не редактируется точками:
 * загруженный GeoJSON или найденное в OSM поле с десятками вершин.
 */
const StaticGeometryLayer: React.FC<{
  geometry: GeoJSON.Polygon | null;
  isOutsideRegion?: boolean;
}> = ({ geometry, isOutsideRegion }) => {
  const map = useMap();
  const layerRef = useRef<L.GeoJSON | null>(null);

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    if (!geometry) return;

    const layer = L.geoJSON(geometry, {
      style: {
        color: isOutsideRegion ? '#f59e0b' : '#1d4ed8',
        weight: 3,
        fillColor: isOutsideRegion ? '#f59e0b' : '#2563eb',
        fillOpacity: 0.35,
      },
    });
    layer.addTo(map);
    layerRef.current = layer;

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [map, geometry, isOutsideRegion]);

  return null;
};

/** Найденные в OSM контуры: клик по любому делает его выбранным участком. */
const ContourLayer: React.FC<{
  contours: FarmlandContour[];
  onPick: (contour: FarmlandContour) => void;
}> = ({ contours, onPick }) => {
  const map = useMap();
  const groupRef = useRef<L.LayerGroup>(new L.LayerGroup());

  useEffect(() => {
    const lg = groupRef.current;
    map.addLayer(lg);
    return () => {
      map.removeLayer(lg);
    };
  }, [map]);

  useEffect(() => {
    const lg = groupRef.current;
    lg.clearLayers();

    for (const contour of contours) {
      const layer = L.geoJSON(contour.geometry, {
        style: {
          color: '#60a5fa',
          weight: 1.5,
          fillColor: '#3b82f6',
          fillOpacity: 0.12,
        },
      });

      layer.bindTooltip(`${contour.name} • ${formatArea(contour.areaHa)}`, {
        sticky: true,
      });

      layer.on('mouseover', () => layer.setStyle({ fillOpacity: 0.35, weight: 2.5 }));
      layer.on('mouseout', () => layer.setStyle({ fillOpacity: 0.12, weight: 1.5 }));
      layer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        onPick(contour);
      });

      lg.addLayer(layer);
    }
  }, [contours, onPick]);

  return null;
};

/**
 * Периметры всех сохранённых полей. Заливка полупрозрачная и кликабельная:
 * попадать в тонкую линию неудобно, поэтому поле выбирается нажатием в любую
 * его точку. Обратная сторона — обвести новое поле поверх своего же старого
 * мешает эта же заливка, для такого случая слой выключается в легенде.
 */
const SavedFieldsLayer: React.FC<{
  polygons: SavedPolygon[];
  /** Контур, который уже нарисован как активный: второй раз его не обводим. */
  activePolygon: GeoJSON.Polygon | null;
  onOpen: (entry: SavedPolygon) => void;
}> = ({ polygons, activePolygon, onOpen }) => {
  const map = useMap();
  const groupRef = useRef<L.LayerGroup>(new L.LayerGroup());

  useEffect(() => {
    const lg = groupRef.current;
    map.addLayer(lg);
    return () => {
      map.removeLayer(lg);
    };
  }, [map]);

  useEffect(() => {
    const lg = groupRef.current;
    lg.clearLayers();

    for (const entry of polygons) {
      if (activePolygon && sameRing(entry.geometry, activePolygon)) continue;

      // Поле с готовым разбором выделяем: по нему есть что показать сразу
      const hasAnalysis = Boolean(entry.analysis);
      const base: L.PathOptions = {
        color: hasAnalysis ? '#60a5fa' : '#e2e8f0',
        weight: hasAnalysis ? 3 : 2,
        opacity: hasAnalysis ? 0.95 : 0.7,
        dashArray: hasAnalysis ? undefined : '5, 5',
        fill: true,
        fillColor: hasAnalysis ? '#3b82f6' : '#e2e8f0',
        fillOpacity: 0.14,
      };

      const layer = L.geoJSON(entry.geometry, { style: base });

      const tip = entry.analysis
        ? `${entry.name} • ${formatArea(entry.areaHa)} • разбор готов, ` +
          `аномалий: ${entry.analysis.anomalyCount}`
        : `${entry.name} • ${formatArea(entry.areaHa)} • разбора нет`;
      layer.bindTooltip(tip, { sticky: true });

      layer.on('mouseover', () =>
        layer.setStyle({ weight: base.weight! + 2, opacity: 1, fillOpacity: 0.3 })
      );
      layer.on('mouseout', () => layer.setStyle(base));
      layer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        onOpen(entry);
      });

      lg.addLayer(layer);
    }
  }, [polygons, activePolygon, onOpen]);

  return null;
};

/** Пересчитывает размеры карты, когда меняется ширина контейнера или боковой панели. */
const MapResizeController: React.FC = () => {
  const map = useMap();

  useEffect(() => {
    map.invalidateSize();
    const t1 = setTimeout(() => map.invalidateSize(), 150);
    const t2 = setTimeout(() => map.invalidateSize(), 350);

    const container = map.getContainer();
    if (!container) {
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }

    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(container);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      ro.disconnect();
    };
  }, [map]);

  return null;
};

/** Отдаёт экземпляр карты наружу: он нужен для поиска по текущему виду и перелётов. */
const MapRefBridge: React.FC<{ mapRef: React.MutableRefObject<L.Map | null> }> = ({
  mapRef,
}) => {
  const map = useMap();
  useEffect(() => {
    mapRef.current = map;
  }, [map, mapRef]);
  return null;
};

export const AreaMap: React.FC<AreaMapProps> = ({
  regionBox,
  geometry,
  onChangeGeometry,
  isOutsideRegion,
  onPointsCountChange,
  onSaveCurrent,
  saveLabel,
  onPickSaved,
  onOpenSavedField,
}) => {
  // Меню лежит поверх карты, поэтому плавающие панели сдвигаются вместе с ним
  const { sidebarCollapsed, savedPolygons, setSavedPolygons } = useAppStore();
  const sideOffset = sidebarCollapsed ? 'left-24' : 'left-72';

  const [points, setPoints] = useState<[number, number][]>([]);
  const [contours, setContours] = useState<FarmlandContour[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [managerOpen, setManagerOpen] = useState(false);

  // Видимость слоёв с административными границами
  const [showRostovBoundary, setShowRostovBoundary] = useState(true);
  const [showNeighbors, setShowNeighbors] = useState(true);
  const [showSavedFields, setShowSavedFields] = useState(true);

  // Подложка карты: схема OSM или спутниковые снимки Esri
  const [baseLayer, setBaseLayer] = useState<'map' | 'satellite'>('map');

  const mapRef = useRef<L.Map | null>(null);
  const searchAbortRef = useRef<AbortController | null>(null);

  // Геометрия, которую карта отдала наружу сама (обводка точками). Без этой
  // отметки эффект синхронизации реагировал бы на собственную запись и
  // возвращал контур, выбранный из списка или найденный в OSM, обратно к точкам.
  const selfEmittedRef = useRef<GeoJSON.Geometry | GeoJSON.Feature | null>(null);

  // Контур, который показываем целиком, — когда вершин слишком много для ручной правки
  const [lockedGeometry, setLockedGeometry] = useState<GeoJSON.Polygon | null>(null);

  useEffect(() => {
    onPointsCountChange?.(points.length);
  }, [points.length, onPointsCountChange]);

  /** Запись геометрии, построенной из точек на карте. */
  const emitFromPoints = useCallback(
    (geom: GeoJSON.Geometry | GeoJSON.Feature | null) => {
      selfEmittedRef.current = geom;
      onChangeGeometry(geom);
    },
    [onChangeGeometry]
  );

  // Синхронизация с геометрией, пришедшей извне: загрузка файла, выбор участка
  useEffect(() => {
    if (!geometry) {
      setPoints([]);
      setLockedGeometry(null);
      return;
    }

    // Это наша же обводка точками — точки уже актуальны, трогать нечего
    if (geometry === selfEmittedRef.current) return;

    const polygon = toPolygon(geometry);
    if (!polygon) return;

    const ring = polygon.coordinates[0];
    if (!ring) return;

    const first = ring[0];
    const last = ring[ring.length - 1];
    const isClosed =
      ring.length > 3 && first && last && first[0] === last[0] && first[1] === last[1];
    const pts = isClosed ? ring.slice(0, -1) : ring;

    if (pts.length >= MIN_POINTS && pts.length <= MAX_EDITABLE_POINTS) {
      setPoints(pts.map((p) => [p[1], p[0]] as [number, number]));
      setLockedGeometry(null);
    } else {
      // Контур сложнее, чем можно править вершинами: показываем как есть
      setPoints([]);
      setLockedGeometry(polygon);
    }
  }, [geometry]);

  const center: L.LatLngExpression = [
    (regionBox.min_lat + regionBox.max_lat) / 2,
    (regionBox.min_lon + regionBox.max_lon) / 2,
  ];

  const handleResetPoints = () => {
    setPoints([]);
    setLockedGeometry(null);
    onChangeGeometry(null);
  };

  /** Перелёт к контуру без смены выбранного участка. */
  const flyToGeometry = useCallback((polygon: GeoJSON.Polygon) => {
    const bounds = L.geoJSON(polygon).getBounds();
    if (bounds.isValid()) {
      mapRef.current?.flyToBounds(bounds, { padding: [60, 60], maxZoom: 16 });
    }
  }, []);

  /** Перелёт к участку и выбор его текущим. */
  const focusGeometry = useCallback(
    (polygon: GeoJSON.Polygon) => {
      // Ручная обводка больше не активна: иначе её эффект перезапишет выбор
      setPoints([]);
      selfEmittedRef.current = null;
      onChangeGeometry(polygon);
      flyToGeometry(polygon);
    },
    [onChangeGeometry, flyToGeometry]
  );

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string);
        const incoming = parseGeoJsonUpload(parsed);

        if (incoming.length === 0) {
          setSearchMessage('В файле не нашлось ни одного полигона');
          return;
        }

        // Из файла может прийти сразу набор участков: складываем их в список,
        // а первый делаем активным
        setSavedPolygons(appendSavedPolygons(savedPolygons, incoming));
        const firstEntry = incoming[0];
        if (firstEntry) focusGeometry(firstEntry.geometry);
        setManagerOpen(true);
        setSearchMessage(
          incoming.length === 1
            ? 'Участок загружен и добавлен в список'
            : `Загружено участков: ${incoming.length}`
        );
      } catch (err) {
        setSearchMessage('Не удалось разобрать GeoJSON: ' + err);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  /** Ищет сельхоз-контуры в текущих границах карты. */
  const handleFindFarmland = async () => {
    const map = mapRef.current;
    if (!map) return;

    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    setSearching(true);
    setSearchMessage(null);

    const b = map.getBounds();

    try {
      const found = await findFarmlandContours(
        {
          south: b.getSouth(),
          west: b.getWest(),
          north: b.getNorth(),
          east: b.getEast(),
        },
        controller.signal
      );

      setContours(found);
      setSearchMessage(
        found.length === 0
          ? 'В этом районе OpenStreetMap не знает сельхозугодий — обведите поле вручную'
          : `Найдено контуров: ${found.length}. Кликните по любому, чтобы выбрать`
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setSearchMessage(
        err instanceof FarmlandSearchError ? err.message : `Ошибка поиска: ${err}`
      );
    } finally {
      setSearching(false);
    }
  };

  const handlePickContour = useCallback(
    (contour: FarmlandContour) => {
      focusGeometry(contour.geometry);
      setSearchMessage(`Выбран контур: ${contour.name} (${formatArea(contour.areaHa)})`);
    },
    [focusGeometry]
  );

  const handleSaveCurrent = () => {
    if (!geometry) return;

    // Когда страница умеет сохранять разбор целиком — сохраняет она
    if (onSaveCurrent) {
      onSaveCurrent();
      setManagerOpen(true);
      return;
    }

    setSavedPolygons(addSavedPolygon(savedPolygons, geometry));
    setManagerOpen(true);
  };

  const handleRemoveSaved = (id: string) => {
    setSavedPolygons(removeSavedPolygon(savedPolygons, id));
  };

  const handleOpenSaved = (entry: SavedPolygon) => {
    if (onPickSaved) {
      // Геометрию проставляет страница — карте остаётся показать участок
      setPoints([]);
      selfEmittedRef.current = null;
      onPickSaved(entry);
      flyToGeometry(entry.geometry);
      return;
    }
    focusGeometry(entry.geometry);
  };

  /** Клик по периметру поля на карте: полная карточка, если её есть чем набить. */
  const handleOpenFieldFromMap = useCallback(
    (entry: SavedPolygon) => {
      setPoints([]);
      selfEmittedRef.current = null;

      if (onOpenSavedField) {
        onOpenSavedField(entry);
      } else {
        focusGeometry(entry.geometry);
      }

      flyToGeometry(entry.geometry);

      if (!entry.analysis) {
        setSearchMessage(
          `«${entry.name}» выбрано, но разбора по нему нет — задайте параметры справа и запустите расчёт`
        );
      }
    },
    [onOpenSavedField, focusGeometry, flyToGeometry]
  );

  const hasContour = points.length >= MIN_POINTS || lockedGeometry !== null;

  // Активный контур не дублируем в слое сохранённых: он и так нарисован
  const activePolygon = toPolygon(geometry);
  const savedWithAnalysis = savedPolygons.filter((p) => p.analysis).length;

  return (
    <div className="relative w-full h-full overflow-hidden">
      {/* Верхняя плавающая панель: подсказка и действия над участком */}
      <div
        className={`absolute top-4 right-4 z-[1000] flex flex-col gap-2 transition-all duration-300 pointer-events-auto xl:right-auto xl:max-w-[calc(100%-480px)] ${sideOffset}`}
      >
        <div className="flex flex-wrap items-center gap-2 bg-black/65 backdrop-blur-md px-3.5 py-2 rounded-2xl shadow-2xl border border-white/10 text-white">
          <div className="flex items-center gap-2">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-black transition-colors shrink-0 ${
                hasContour
                  ? 'bg-blue-600 text-white shadow-blue-500/30 shadow-md'
                  : 'bg-white/15 text-white border border-white/20'
              }`}
            >
              {lockedGeometry ? '✓' : points.length}
            </span>
            <span className="text-xs font-semibold text-white/90 truncate">
              {lockedGeometry && 'Контур выбран. Задайте параметры справа →'}
              {!lockedGeometry && points.length === 0 && 'Кликайте по карте, чтобы обвести поле (нужно от 3 точек)'}
              {!lockedGeometry && points.length === 1 && 'Точка 1. Нужно ещё минимум две'}
              {!lockedGeometry && points.length === 2 && 'Точка 2. Ещё одна — и контур замкнётся'}
              {!lockedGeometry && points.length >= MIN_POINTS &&
                `Точек: ${points.length}. Можно добавить ещё или задать параметры справа →`}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0 ml-auto">
            <button
              type="button"
              onClick={handleFindFarmland}
              disabled={searching}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-white bg-blue-600/30 hover:bg-blue-600/50 disabled:opacity-60 rounded-lg border border-blue-400/40 transition-all shadow-sm"
              title="Найти сельхозугодья в текущих границах карты по данным OpenStreetMap"
            >
              {searching ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-300" />
              ) : (
                <Search className="w-3.5 h-3.5 text-blue-300" />
              )}
              <span>{searching ? 'Ищем…' : 'Найти поля'}</span>
            </button>

            <label className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-white/80 bg-white/5 hover:bg-white/10 rounded-lg border border-white/15 cursor-pointer transition-all shadow-sm">
              <Upload className="w-3 h-3 text-white/60" />
              <span>GeoJSON</span>
              <input
                type="file"
                accept=".json,.geojson"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>

            {hasContour && (
              <button
                type="button"
                onClick={handleSaveCurrent}
                className={`flex items-center gap-1 px-2 py-1 text-xs font-semibold rounded-lg border transition-all shadow-sm ${
                  saveLabel
                    ? 'text-white bg-blue-600/40 hover:bg-blue-600/60 border-blue-400/50'
                    : 'text-white bg-white/10 hover:bg-white/20 border-white/15'
                }`}
                title={
                  saveLabel
                    ? 'Сохранить готовый разбор в закладки: откроется без пересчёта'
                    : 'Сохранить участок в список'
                }
              >
                {saveLabel ? <Bookmark className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                <span>{saveLabel ?? 'В список'}</span>
              </button>
            )}

            {(hasContour || points.length > 0) && (
              <button
                type="button"
                onClick={handleResetPoints}
                className="flex items-center gap-1 px-2 py-1 text-xs font-semibold text-rose-300 bg-rose-500/15 hover:bg-rose-500/25 rounded-lg border border-rose-500/25 transition-all shadow-sm"
                title="Очистить текущий контур"
              >
                <Trash2 className="w-3.5 h-3.5 text-rose-400" />
                <span>Очистить</span>
              </button>
            )}
          </div>
        </div>

        {/* Итог поиска или загрузки файла */}
        {searchMessage && (
          <div className="bg-black/65 backdrop-blur-md px-3 py-2 rounded-xl shadow-2xl border border-white/10 text-[11px] text-white/80 flex items-start gap-2">
            <MapPin className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
            <span className="flex-1">{searchMessage}</span>
            <button
              type="button"
              onClick={() => {
                setSearchMessage(null);
                setContours([]);
              }}
              className="text-white/40 hover:text-white font-semibold shrink-0"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* Список сохранённых участков */}
      <div
        className={`absolute bottom-20 z-[1000] w-72 pointer-events-auto transition-all duration-300 ${sideOffset}`}
      >
        <button
          type="button"
          onClick={() => setManagerOpen((v) => !v)}
          className="w-full flex items-center justify-between gap-2 bg-black/65 backdrop-blur-md px-3 py-2 rounded-xl shadow-2xl border border-white/10 text-xs font-bold text-white hover:bg-black/80 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-blue-400" />
            Мои участки ({savedPolygons.length})
          </span>
          <span className="text-white/40">{managerOpen ? '▾' : '▸'}</span>
        </button>

        {managerOpen && (
          <div className="mt-1.5 bg-black/75 backdrop-blur-md rounded-xl shadow-2xl border border-white/10 max-h-64 overflow-y-auto divide-y divide-white/10">
            {savedPolygons.length === 0 ? (
              <div className="p-3 text-[11px] text-white/60 leading-relaxed">
                Пока пусто. Обведите поле или найдите его через «Найти поля», затем
                нажмите «В список». После расчёта кнопка сохранит разбор целиком —
                закладка откроется без повторного ожидания. Всё лежит в этом браузере.
              </div>
            ) : (
              savedPolygons.map((poly) => (
                <div
                  key={poly.id}
                  className="flex items-center gap-2 p-2.5 hover:bg-white/[0.07] transition-colors group"
                >
                  <button
                    type="button"
                    onClick={() => handleOpenSaved(poly)}
                    className="flex-1 min-w-0 text-left"
                    title={
                      poly.analysis
                        ? `Открыть готовый разбор: ${poly.analysis.cropType}, сезоны ` +
                          `${poly.analysis.years[0]}–${poly.analysis.years[poly.analysis.years.length - 1]}`
                        : 'Перейти к участку'
                    }
                  >
                    <div className="text-xs font-semibold text-white truncate">
                      {poly.name}
                    </div>
                    <div className="text-[10px] text-white/50 flex items-center gap-1.5 flex-wrap">
                      <span>{formatArea(poly.areaHa)}</span>
                      {poly.analysis && (
                        <span className="inline-flex items-center gap-1 text-blue-300 bg-blue-500/15 border border-blue-400/30 px-1.5 rounded">
                          <BarChart3 className="w-2.5 h-2.5" />
                          разбор • {poly.analysis.anomalyCount} аном.
                        </span>
                      )}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleRemoveSaved(poly.id)}
                    className="p-1 rounded text-white/30 group-hover:text-rose-400 hover:bg-rose-500/15 transition-colors shrink-0"
                    title={`Удалить участок «${poly.name}»`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      <MapContainer
        center={center}
        zoom={8}
        scrollWheelZoom={true}
        zoomControl={false}
        className="w-full h-full cursor-crosshair"
      >
        <ZoomControl position="bottomright" />
        <MapRefBridge mapRef={mapRef} />
        <MapResizeController />

        {/* Подложка. key заставляет Leaflet заменить слой, а не наложить второй */}
        {baseLayer === 'satellite' ? (
          <TileLayer
            key="satellite"
            attribution='Снимки &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            maxZoom={19}
          />
        ) : (
          <TileLayer
            key="osm"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        )}

        {/* 1. Административная граница Ростовской области */}
        {showRostovBoundary && (
          <Polygon
            positions={rostovPolygon}
            pathOptions={{
              color: '#2563eb',
              weight: 2.5,
              dashArray: '8, 6',
              fillColor: '#3b82f6',
              fillOpacity: 0.05,
            }}
          />
        )}

        {/* 2. Соседние сельхозрегионы: Кубань и Волгоградская область */}
        {showNeighbors && (
          <>
            <Polygon
              positions={krasnodarPolygon}
              pathOptions={{
                color: '#60a5fa',
                weight: 1.5,
                dashArray: '5, 5',
                fillColor: '#60a5fa',
                fillOpacity: 0.02,
              }}
            />
            <Polygon
              positions={volgogradPolygon}
              pathOptions={{
                color: '#60a5fa',
                weight: 1.5,
                dashArray: '5, 5',
                fillColor: '#60a5fa',
                fillOpacity: 0.02,
              }}
            />
          </>
        )}

        <ContourLayer contours={contours} onPick={handlePickContour} />

        {/* 4. Периметры сохранённых полей: клик по линии открывает карточку */}
        {showSavedFields && (
          <SavedFieldsLayer
            polygons={savedPolygons}
            activePolygon={activePolygon}
            onOpen={handleOpenFieldFromMap}
          />
        )}

        <StaticGeometryLayer geometry={lockedGeometry} isOutsideRegion={isOutsideRegion} />

        <PointPlacementController
          points={points}
          setPoints={setPoints}
          onChangeGeometry={emitFromPoints}
          isOutsideRegion={isOutsideRegion}
          enabled={lockedGeometry === null}
        />
      </MapContainer>

      {/* Легенда и переключатели границ */}
      <div
        className={`absolute bottom-4 z-[1000] bg-black/65 backdrop-blur-md px-3.5 py-2 rounded-xl border border-white/10 text-[11px] font-medium text-white shadow-2xl flex flex-wrap items-center gap-2.5 pointer-events-auto transition-all duration-300 ${sideOffset}`}
      >
        {/* Подложка карты */}
        <div className="flex items-center gap-0.5 shrink-0 bg-white/[0.07] border border-white/15 rounded-lg p-0.5">
          <button
            type="button"
            onClick={() => setBaseLayer('map')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold transition-all ${
              baseLayer === 'map' ? 'bg-white text-slate-900 shadow-sm' : 'text-white/60 hover:text-white'
            }`}
            title="Схематическая карта OpenStreetMap"
          >
            <Map className="w-3 h-3" />
            <span>Схема</span>
          </button>
          <button
            type="button"
            onClick={() => setBaseLayer('satellite')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold transition-all ${
              baseLayer === 'satellite' ? 'bg-white text-slate-900 shadow-sm' : 'text-white/60 hover:text-white'
            }`}
            title="Спутниковые снимки Esri World Imagery: по ним видно сами поля"
          >
            <Satellite className="w-3 h-3" />
            <span>Спутник</span>
          </button>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.8)] animate-pulse inline-block" />
          <span className="font-bold text-white/90">Границы:</span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
          <button
            type="button"
            onClick={() => setShowRostovBoundary((v) => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold transition-all ${
              showRostovBoundary
                ? 'bg-blue-600/40 text-blue-300 border-blue-400/60 shadow-sm'
                : 'bg-white/5 text-white/40 border-white/10 hover:text-white/70'
            }`}
            title="Административная граница Ростовской области — регион обучения модели"
          >
            <span className="w-2.5 h-2.5 border border-blue-400 border-dashed bg-blue-500/30 rounded-sm inline-block shrink-0" />
            <span>Ростовская область</span>
          </button>

          <button
            type="button"
            onClick={() => setShowNeighbors((v) => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
              showNeighbors
                ? 'bg-blue-600/20 text-blue-300 border-blue-400/40 shadow-sm'
                : 'bg-white/5 text-white/40 border-white/10 hover:text-white/70'
            }`}
            title="Сопредельные регионы: Краснодарский край и Волгоградская область"
          >
            <span className="w-2.5 h-2.5 border border-blue-400/60 border-dotted bg-blue-500/10 rounded-sm inline-block shrink-0" />
            <span>Соседние регионы (Кубань, Поволжье)</span>
          </button>

          <button
            type="button"
            onClick={() => setShowSavedFields((v) => !v)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold transition-all ${
              showSavedFields
                ? 'bg-blue-500/25 text-blue-200 border-blue-300/50 shadow-sm'
                : 'bg-white/5 text-white/40 border-white/10 hover:text-white/70'
            }`}
            title="Периметры моих полей. Клик по линии открывает карточку поля"
          >
            <span className="w-2.5 h-2.5 border-2 border-blue-300 rounded-sm inline-block shrink-0" />
            <span>
              Мои поля ({savedPolygons.length}
              {savedWithAnalysis > 0 ? ` · ${savedWithAnalysis} с разбором` : ''})
            </span>
          </button>
        </div>
      </div>
    </div>
  );
};
