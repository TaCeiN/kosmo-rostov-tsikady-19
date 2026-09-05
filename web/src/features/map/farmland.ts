import { calculateAreaHa } from './validation';

/**
 * Сельхоз-контур, найденный в OpenStreetMap.
 * Служит подсказкой: границы полей в OSM рисуют люди, они бывают
 * устаревшими, поэтому найденный контур можно править точками вручную.
 */
export interface FarmlandContour {
  id: string;
  name: string;
  landuse: string;
  geometry: GeoJSON.Polygon;
  areaHa: number;
}

/** Публичный Overpass — ключей не требует, лимит порядка пары запросов в минуту. */
const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

/** Что в OSM считаем сельхозугодьями. */
const LANDUSE_LABELS: Record<string, string> = {
  farmland: 'пашня',
  farmyard: 'хозяйственный двор',
  orchard: 'сад',
  vineyard: 'виноградник',
  meadow: 'луг',
  greenhouse_horticulture: 'теплицы',
};

export interface FarmlandSearchBbox {
  south: number;
  west: number;
  north: number;
  east: number;
}

export class FarmlandSearchError extends Error {}

/**
 * Прямоугольник больше этого искать не даём: Overpass на область в пол-страны
 * отвечает минутами и часто обрывается по таймауту. Порог в градусах —
 * примерно 110×110 км по широте Ростовской области.
 */
const MAX_BBOX_DEGREES = 1.0;

/** Разумный потолок, чтобы карта не превратилась в кашу из тысяч контуров. */
const MAX_CONTOURS = 120;

function buildQuery(bbox: FarmlandSearchBbox): string {
  const box = `${bbox.south},${bbox.west},${bbox.north},${bbox.east}`;
  const classes = Object.keys(LANDUSE_LABELS).join('|');

  // out geom отдаёт координаты прямо внутри way — иначе пришлось бы вторым
  // запросом разрешать ссылки на узлы.
  return `[out:json][timeout:25];
(
  way["landuse"~"^(${classes})$"](${box});
);
out geom ${MAX_CONTOURS};`;
}

interface OverpassWay {
  type: string;
  id: number;
  tags?: Record<string, string>;
  geometry?: Array<{ lat: number; lon: number }>;
}

/**
 * Ищет сельхоз-контуры в границах текущего вида карты.
 * Работает в любой точке мира: именно это снимает привязку сервиса
 * к заранее заданному набору полей.
 */
export async function findFarmlandContours(
  bbox: FarmlandSearchBbox,
  signal?: AbortSignal
): Promise<FarmlandContour[]> {
  const height = bbox.north - bbox.south;
  const width = bbox.east - bbox.west;

  if (height > MAX_BBOX_DEGREES || width > MAX_BBOX_DEGREES) {
    throw new FarmlandSearchError(
      'Область поиска слишком велика: приблизьте карту к нужному району и повторите'
    );
  }

  let res: Response;
  try {
    res = await fetch(OVERPASS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: buildQuery(bbox),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new FarmlandSearchError(
      'Не удалось связаться с OpenStreetMap. Проверьте подключение или обведите поле вручную'
    );
  }

  if (res.status === 429 || res.status === 504) {
    throw new FarmlandSearchError(
      'OpenStreetMap сейчас ограничивает частоту запросов. Подождите полминуты и повторите'
    );
  }

  if (!res.ok) {
    throw new FarmlandSearchError(`OpenStreetMap ответил ошибкой HTTP ${res.status}`);
  }

  const data = (await res.json()) as { elements?: OverpassWay[] };
  const elements = data.elements ?? [];
  const contours: FarmlandContour[] = [];

  for (const el of elements) {
    if (el.type !== 'way' || !el.geometry || el.geometry.length < 4) continue;

    const ring: [number, number][] = el.geometry.map((p) => [p.lon, p.lat]);

    // Замыкаем кольцо, если OSM отдал его незамкнутым
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first && last && (first[0] !== last[0] || first[1] !== last[1])) {
      ring.push([first[0], first[1]]);
    }

    const polygon: GeoJSON.Polygon = { type: 'Polygon', coordinates: [ring] };
    const areaHa = calculateAreaHa(polygon);

    // Совсем мелкие обрезки — это межи и постройки, а не поля
    if (areaHa < 0.5) continue;

    const landuse = el.tags?.landuse ?? 'farmland';
    const label = LANDUSE_LABELS[landuse] ?? landuse;

    contours.push({
      id: `osm-${el.id}`,
      name: el.tags?.name || `${label} №${el.id}`,
      landuse,
      geometry: polygon,
      areaHa,
    });
  }

  // Крупные поля выносим наверх: с ними и работают в первую очередь
  contours.sort((a, b) => b.areaHa - a.areaHa);
  return contours;
}
