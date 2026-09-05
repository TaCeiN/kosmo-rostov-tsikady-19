import React from 'react';
import { SeriesView } from '../../adapters/series';
import { AnomalyRecord } from '../../types/domain';
import { FileJson, FileSpreadsheet, Image } from 'lucide-react';

interface ExportButtonsProps {
  series: SeriesView;
  anomalies: AnomalyRecord[];
  rawResult?: unknown;
  getChartDataUrl?: () => string | null;
}

export const ExportButtons: React.FC<ExportButtonsProps> = ({
  series,
  anomalies,
  rawResult,
  getChartDataUrl,
}) => {
  const filePrefix = `ndvi_${series.id}_${series.years[0] ?? ''}-${series.years[series.years.length - 1] ?? ''}`;

  const downloadFile = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // 1. Выгрузка графика в PNG
  const exportPng = () => {
    if (!getChartDataUrl) {
      alert('Экспорт изображения недоступен');
      return;
    }
    const dataUrl = getChartDataUrl();
    if (!dataUrl) {
      alert('Не удалось получить изображение графика');
      return;
    }
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = `${filePrefix}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // 2. Выгрузка ряда в CSV: BOM и точка с запятой нужны, чтобы Excel открыл файл без плясок с кодировкой
  const exportSeriesCsv = () => {
    const headers = [
      'date',
      'ndvi_obs',
      'ndvi_filled',
      'ndvi_smooth',
      'clim_mean',
      'clim_std',
      'z',
      'status',
      'precip_30d',
      'temp_30d',
    ];

    const rows: string[] = [];
    rows.push(headers.join(';'));

    for (let i = 0; i < series.n; i++) {
      const row = [
        series.date[i] ?? '',
        series.ndviObs[i] !== null && series.ndviObs[i] !== undefined ? String(series.ndviObs[i]) : '',
        series.ndviFilled[i] !== null && series.ndviFilled[i] !== undefined ? String(series.ndviFilled[i]) : '',
        series.ndviSmooth[i] !== null && series.ndviSmooth[i] !== undefined ? String(series.ndviSmooth[i]) : '',
        series.climMean[i] !== null && series.climMean[i] !== undefined ? String(series.climMean[i]) : '',
        series.climStd[i] !== null && series.climStd[i] !== undefined ? String(series.climStd[i]) : '',
        series.z[i] !== null && series.z[i] !== undefined ? String(series.z[i]) : '',
        `"${series.status[i] ?? ''}"`,
        series.precip30d[i] !== null && series.precip30d[i] !== undefined ? String(series.precip30d[i]) : '',
        series.temp30d[i] !== null && series.temp30d[i] !== undefined ? String(series.temp30d[i]) : '',
      ];
      rows.push(row.join(';'));
    }

    // Дописываем BOM в начало
    const content = '\uFEFF' + rows.join('\r\n');
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    downloadFile(blob, `${filePrefix}_series.csv`);
  };

  // 3. Выгрузка аномалий в CSV, тем же способом
  const exportAnomaliesCsv = () => {
    const headers = [
      'anon_polygon_id',
      'year',
      'start',
      'end',
      'days',
      'z_min',
      'z_mean',
      'ndvi_mean',
      'clim_mean',
      'drop_vs_norm',
      'severity',
      'crop_type',
      'precip_30d',
      'precip_30d_norm',
      'temp_anom',
      'precip_ratio',
      'cause',
      'comment',
    ];

    const rows: string[] = [];
    rows.push(headers.join(';'));

    for (const a of anomalies) {
      const row = [
        a.anon_polygon_id,
        String(a.year),
        a.start,
        a.end,
        String(a.days),
        String(a.z_min),
        String(a.z_mean),
        String(a.ndvi_mean),
        String(a.clim_mean),
        String(a.drop_vs_norm),
        `"${a.severity}"`,
        `"${a.crop_type}"`,
        a.precip_30d !== null ? String(a.precip_30d) : '',
        a.precip_30d_norm !== null ? String(a.precip_30d_norm) : '',
        a.temp_anom !== null ? String(a.temp_anom) : '',
        a.precip_ratio !== null ? String(a.precip_ratio) : '',
        `"${a.cause}"`,
        `"${a.comment.replace(/"/g, '""')}"`,
      ];
      rows.push(row.join(';'));
    }

    const content = '\uFEFF' + rows.join('\r\n');
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    downloadFile(blob, `${filePrefix}_anomalies.csv`);
  };

  // 4. Выгрузка исходного ответа в JSON
  const exportJson = () => {
    const data = rawResult ?? {
      id: series.id,
      crop_type: series.cropType,
      years: series.years,
      date: series.date,
      ndvi_smooth: series.ndviSmooth,
      anomalies,
    };
    const content = JSON.stringify(data, null, 2);
    const blob = new Blob([content], { type: 'application/json;charset=utf-8;' });
    downloadFile(blob, `${filePrefix}_result.json`);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={exportPng}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 transition-colors"
        title="Скачать график в высоком разрешении (PNG)"
      >
        <Image className="w-3.5 h-3.5 text-brand-600" />
        <span>PNG графика</span>
      </button>

      <button
        type="button"
        onClick={exportSeriesCsv}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 transition-colors"
        title="Экспорт ряда в CSV (совместим с Excel, разделитель ';', кодировка UTF-8 с BOM)"
      >
        <FileSpreadsheet className="w-3.5 h-3.5 text-blue-600" />
        <span>CSV ряда</span>
      </button>

      {anomalies.length > 0 && (
        <button
          type="button"
          onClick={exportAnomaliesCsv}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 transition-colors"
          title="Экспорт списка аномалий в CSV"
        >
          <FileSpreadsheet className="w-3.5 h-3.5 text-red-600" />
          <span>CSV аномалий</span>
        </button>
      )}

      <button
        type="button"
        onClick={exportJson}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 transition-colors"
        title="Скачать полный сырой JSON ответа"
      >
        <FileJson className="w-3.5 h-3.5 text-blue-800" />
        <span>JSON разбора</span>
      </button>
    </div>
  );
};
