import React, { useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { SeriesView } from '../../adapters/series';
import { AnomalyRecord } from '../../types/domain';
import {
  formatDateRu,
  formatNdvi,
  formatPrecip,
  formatTemp,
  formatZScore,
} from '../../lib/formatters';
import { getSeverityMeta } from '../../lib/constants';

interface NdviChartProps {
  series: SeriesView;
  anomalies: AnomalyRecord[];
  comparisonSeries?: SeriesView | null;
  onAnomalyClick?: (anomaly: AnomalyRecord) => void;
  selectedAnomaly?: AnomalyRecord | null;
  highlightRange?: [string, string] | null;
}

export const NdviChart: React.FC<NdviChartProps> = ({
  series,
  anomalies,
  comparisonSeries,
  onAnomalyClick,
  selectedAnomaly,
  highlightRange,
}) => {
  const chartRef = useRef<ReactECharts>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [showControlPoints, setShowControlPoints] = useState(true);
  const [showWeather, setShowWeather] = useState(false);

  // Собирает ряд с разрывами там, где между соседними датами больше суток
  const buildLineDataWithGaps = (
    dates: string[],
    values: (number | null)[]
  ): Array<[string, number | null]> => {
    const result: Array<[string, number | null]> = [];

    for (let i = 0; i < dates.length; i++) {
      const d = dates[i];
      const v = values[i] ?? null;
      if (!d) continue;

      if (i > 0) {
        const prevD = dates[i - 1];
        if (prevD) {
          const diffDays = Math.round(
            (new Date(d + 'T00:00:00Z').getTime() - new Date(prevD + 'T00:00:00Z').getTime()) /
              (1000 * 60 * 60 * 24)
          );
          if (diffDays > 1) {
            // Пара null рвёт линию: иначе зимний пропуск соединится прямой через полгода
            result.push([prevD + 'T23:59:59', null]);
            result.push([d + 'T00:00:00', null]);
          }
        }
      }

      result.push([d, v]);
    }

    return result;
  };

  // Подготовка рядов для графика
  const smoothData = useMemo(
    () => buildLineDataWithGaps(series.date, series.ndviSmooth),
    [series.date, series.ndviSmooth]
  );

  const filledData = useMemo(
    () => buildLineDataWithGaps(series.date, series.ndviFilled),
    [series.date, series.ndviFilled]
  );

  const climMeanData = useMemo(
    () => buildLineDataWithGaps(series.date, series.climMean),
    [series.date, series.climMean]
  );

  // Коридор нормы рисуем стопкой: нижняя граница плюс высота 2σ
  const corridorLowerData = useMemo(() => {
    const vals = series.climMean.map((mean, i) => {
      const std = series.climStd[i];
      if (mean === null || std === null || mean === undefined || std === undefined) return null;
      return Math.max(-0.2, mean - std);
    });
    return buildLineDataWithGaps(series.date, vals);
  }, [series.date, series.climMean, series.climStd]);

  const corridorWidthData = useMemo(() => {
    const vals = series.climMean.map((mean, i) => {
      const std = series.climStd[i];
      if (mean === null || std === null || mean === undefined || std === undefined) return null;
      return 2 * std;
    });
    return buildLineDataWithGaps(series.date, vals);
  }, [series.date, series.climMean, series.climStd]);

  // Наблюдения спутников: точки, пропуски выбрасываем
  const obsData = useMemo(() => {
    const result: Array<[string, number]> = [];
    for (let i = 0; i < series.date.length; i++) {
      const d = series.date[i];
      const val = series.ndviObs[i];
      if (d && val !== null && val !== undefined) {
        result.push([d, val]);
      }
    }
    return result;
  }, [series.date, series.ndviObs]);

  // Контрольные точки — по ним жюри сверяет качество восстановления
  const controlPointsData = useMemo(() => {
    if (!series.isControlPoint) return [];
    const result: Array<[string, number]> = [];
    for (let i = 0; i < series.date.length; i++) {
      const d = series.date[i];
      const isCtrl = series.isControlPoint[i];
      const val = series.ndviSmooth[i] ?? series.ndviFilled[i];
      if (d && isCtrl && val !== null && val !== undefined) {
        result.push([d, val]);
      }
    }
    return result;
  }, [series.date, series.isControlPoint, series.ndviSmooth, series.ndviFilled]);

  // Погодные ряды
  const precipData = useMemo(
    () => buildLineDataWithGaps(series.date, series.precip30d),
    [series.date, series.precip30d]
  );
  const tempData = useMemo(
    () => buildLineDataWithGaps(series.date, series.temp30d),
    [series.date, series.temp30d]
  );

  // Ряд для сравнения, если в демо выбран второй полигон
  const compSmoothData = useMemo(() => {
    if (!comparisonSeries) return [];
    return buildLineDataWithGaps(comparisonSeries.date, comparisonSeries.ndviSmooth);
  }, [comparisonSeries]);

  // Подсветка аномальных периодов
  const markAreaData = useMemo(() => {
    return anomalies.map((anom) => {
      const isSelected = selectedAnomaly && selectedAnomaly.start === anom.start && selectedAnomaly.end === anom.end;
      const isHighlighted = highlightRange && highlightRange[0] === anom.start && highlightRange[1] === anom.end;
      const sev = getSeverityMeta(anom.severity);

      return [
        {
          name: anom.cause,
          xAxis: anom.start,
          itemStyle: {
            color: isSelected || isHighlighted ? 'rgba(239, 68, 68, 0.45)' : sev.chartColor,
            borderWidth: isSelected || isHighlighted ? 2 : 1,
            borderColor: isSelected || isHighlighted ? '#b91c1c' : sev.chartColor,
          },
          label: {
            show: isSelected || isHighlighted,
            position: 'top',
            formatter: `${anom.days} дн. (z = ${anom.z_min.toFixed(1)})`,
            color: '#b91c1c',
            fontSize: 11,
            fontWeight: 'bold',
          },
        },
        {
          xAxis: anom.end,
        },
      ];
    });
  }, [anomalies, selectedAnomaly, highlightRange]);

  // Быстрый переход к сезону
  const handleYearSelect = (year: number | null) => {
    setSelectedYear(year);
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;

    if (year === null) {
      instance.dispatchAction({
        type: 'dataZoom',
        start: 0,
        end: 100,
      });
    } else {
      instance.dispatchAction({
        type: 'dataZoom',
        startValue: `${year}-04-01`,
        endValue: `${year}-10-30`,
      });
    }
  };

  // Опции ECharts
  const option: EChartsOption = useMemo(() => {
    const isLarge = series.n > 2000;

    // Набор серий графика
    const chartSeries: any[] = [];

    // 1. Коридор климатнормы: нижняя граница стопки
    if (series.hasClimateNorm) {
      chartSeries.push({
        name: 'Климатнорма: коридор ±1σ (нижняя)',
        type: 'line',
        data: corridorLowerData,
        stack: 'clim_band',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        connectNulls: false,
        silent: true,
      });

      chartSeries.push({
        name: 'Коридор климатнормы (±1σ)',
        type: 'line',
        data: corridorWidthData,
        stack: 'clim_band',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: {
          color: 'rgba(203, 213, 225, 0.45)', // pale blue-slate
        },
        connectNulls: false,
        silent: true,
      });

      // 2. Линия климатнормы, пунктиром
      chartSeries.push({
        name: 'Климатнорма (среднее)',
        type: 'line',
        data: climMeanData,
        symbol: 'none',
        lineStyle: {
          color: '#94a3b8',
          width: 1.5,
          type: 'dashed',
        },
        connectNulls: false,
      });
    }

    // 3. Восстановленный ряд
    chartSeries.push({
      name: 'Восстановленный ряд (NDVI)',
      type: 'line',
      data: filledData,
      symbol: 'none',
      lineStyle: {
        color: '#60a5fa', // blue 400
        width: 1.2,
      },
      connectNulls: false,
      large: isLarge,
      sampling: 'lttb',
    });

    // 4. Сглаженный ряд — основная кривая, по ней считаются z и аномалии
    chartSeries.push({
      name: 'Сглаженный ряд (по нему считается z и аномалии)',
      type: 'line',
      data: smoothData,
      symbol: 'none',
      lineStyle: {
        color: '#2563eb', // blue 600
        width: 2.5,
      },
      connectNulls: false,
      markArea: {
        silent: false,
        label: { show: false },
        data: markAreaData,
      },
      large: isLarge,
      sampling: 'lttb',
    });

    // 5. Наблюдения спутников
    chartSeries.push({
      name: 'Наблюдения спутников (без облаков)',
      type: 'scatter',
      data: obsData,
      symbolSize: 5,
      itemStyle: {
        color: '#0f172a',
        opacity: 0.8,
      },
    });

    // 6. Контрольные точки, если есть и включены
    if (showControlPoints && controlPointsData.length > 0) {
      chartSeries.push({
        name: 'Контрольные точки (оценка жюри)',
        type: 'scatter',
        data: controlPointsData,
        symbol: 'diamond',
        symbolSize: 8,
        itemStyle: {
          color: '#d97706', // amber
          borderColor: '#ffffff',
          borderWidth: 1,
        },
        z: 10,
      });
    }

    // 7. Ряд второго полигона для сравнения
    if (comparisonSeries && compSmoothData.length > 0) {
      chartSeries.push({
        name: `Сравнение: ${comparisonSeries.id} (${comparisonSeries.cropType})`,
        type: 'line',
        data: compSmoothData,
        symbol: 'none',
        lineStyle: {
          color: '#2563eb', // blue
          width: 2,
        },
        connectNulls: false,
      });
    }

    // 8. Погода на своих правых осях: мм и °C несопоставимы, общая шкала прижимает температуру к нулю
    if (showWeather) {
      chartSeries.push({
        name: 'Осадки за 30 дней (мм)',
        type: 'line',
        yAxisIndex: 1,
        data: precipData,
        symbol: 'none',
        lineStyle: { color: '#0284c7', width: 1.2, type: 'dotted' },
        areaStyle: { color: 'rgba(2, 132, 199, 0.08)' },
        connectNulls: false,
      });
      chartSeries.push({
        name: 'Температура за 30 дней (°C)',
        type: 'line',
        yAxisIndex: 2,
        data: tempData,
        symbol: 'none',
        lineStyle: { color: '#ea580c', width: 1.2, type: 'dashed' },
        connectNulls: false,
      });
    }

    return {
      animation: false,
      grid: {
        left: '4%',
        right: showWeather ? '9%' : '2%',
        top: '12%',
        bottom: '15%',
        containLabel: true,
      },
      legend: {
        top: 0,
        type: 'scroll',
        textStyle: { fontSize: 12 },
        selected: {
          'Климатнорма: коридор ±1σ (нижняя)': false,
          'Восстановленный ряд (NDVI)': true,
          'Сглаженный ряд (по нему считается z и аномалии)': true,
          'Коридор климатнормы (±1σ)': true,
          'Климатнорма (среднее)': true,
          'Наблюдения спутников (без облаков)': true,
          'Контрольные точки (оценка жюри)': showControlPoints,
        },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          lineStyle: { color: '#94a3b8', type: 'dashed' },
        },
        backgroundColor: 'rgba(255, 255, 255, 0.96)',
        borderColor: '#cbd5e1',
        borderWidth: 1,
        textStyle: { color: '#0f172a', fontSize: 12 },
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return '';
          const first = params[0];
          const dateStr = first.axisValueLabel || (Array.isArray(first.data) ? first.data[0] : '');

          const index = series.date.indexOf(dateStr);
          if (index === -1) {
            return `<b>${dateStr}</b>`;
          }

          const obs = series.ndviObs[index];
          const filled = series.ndviFilled[index];
          const smooth = series.ndviSmooth[index];
          const norm = series.climMean[index];
          const std = series.climStd[index];
          const z = series.z[index];
          const status = series.status[index];
          const precip = series.precip30d[index];
          const temp = series.temp30d[index];
          const precipNorm = series.precip30dNorm?.[index];
          const tempNorm = series.temp30dNorm?.[index];
          const tempAnom = series.tempAnom?.[index];

          let html = `<div class="p-1 space-y-1 text-xs">`;
          html += `<div class="font-bold text-slate-800 border-b pb-1 text-sm">${formatDateRu(dateStr)}</div>`;

          // Значения
          html += `<div class="grid grid-cols-2 gap-x-3 gap-y-0.5 pt-1">`;
          html += `<span class="text-slate-500">Спутник (наблюдение):</span> <span class="font-semibold text-right">${obs !== null ? formatNdvi(obs) : 'Облачно'}</span>`;
          html += `<span class="text-slate-500">Восстановленный NDVI:</span> <span class="font-semibold text-right text-blue-600">${formatNdvi(filled)}</span>`;
          html += `<span class="text-slate-500">Сглаженный NDVI:</span> <span class="font-bold text-right text-blue-800">${formatNdvi(smooth)}</span>`;

          if (norm !== null && norm !== undefined && std !== null && std !== undefined) {
            html += `<span class="text-slate-500">Климатнорма:</span> <span class="text-right text-slate-700">${formatNdvi(norm)} ± ${formatNdvi(std)}</span>`;
          } else {
            html += `<span class="text-slate-500">Климатнорма:</span> <span class="text-right text-slate-400 italic">не построена (&lt;3 сезонов)</span>`;
          }

          if (z !== null && z !== undefined) {
            const zColor = z < -2 ? 'text-red-600 font-bold' : z < -1 ? 'text-amber-600 font-bold' : 'text-slate-700';
            html += `<span class="text-slate-500">Отклонение (z-score):</span> <span class="text-right ${zColor}">${formatZScore(z)} σ</span>`;
          }

          if (status) {
            html += `<span class="text-slate-500">Статус развития:</span> <span class="text-right font-medium text-slate-800">${status}</span>`;
          }

          if (precip !== null || temp !== null) {
            html += `<div class="col-span-2 border-t pt-1 mt-1 text-[11px] text-slate-600">`;
            if (precip !== null) {
              const precipNormText = precipNorm ? ` (норма: ${formatPrecip(precipNorm)})` : '';
              html += `<div>Осадки за 30 дней: <b>${formatPrecip(precip)}</b>${precipNormText}</div>`;
            }
            if (temp !== null) {
              const tempNormText = tempNorm ? ` (норма: ${formatTemp(tempNorm)})` : '';
              const anomText = tempAnom ? ` [${formatTemp(tempAnom)}]` : '';
              html += `<div>Температура за 30 дней: <b>${formatTemp(temp)}</b>${tempNormText}${anomText}</div>`;
            }
            html += `</div>`;
          }

          html += `</div></div>`;
          return html;
        },
      },
      xAxis: {
        type: 'time',
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { color: '#64748b' },
      },
      yAxis: [
        {
          type: 'value',
          min: -0.2,
          max: 1.0,
          interval: 0.2,
          name: 'NDVI',
          nameTextStyle: { color: '#475569', fontWeight: 'bold' },
          axisLine: { show: true, lineStyle: { color: '#cbd5e1' } },
          axisLabel: { color: '#64748b', formatter: '{value}' },
          splitLine: { lineStyle: { color: '#f1f5f9' } },
        },
        {
          type: 'value',
          show: showWeather,
          position: 'right',
          name: 'Осадки, мм',
          nameTextStyle: { color: '#0284c7' },
          axisLine: { show: true, lineStyle: { color: '#0284c7' } },
          axisLabel: { color: '#0284c7' },
          splitLine: { show: false },
        },
        {
          type: 'value',
          show: showWeather,
          position: 'right',
          offset: 58,
          name: 'T, °C',
          nameTextStyle: { color: '#ea580c' },
          axisLine: { show: true, lineStyle: { color: '#ea580c' } },
          axisLabel: { color: '#ea580c', formatter: '{value}°' },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        {
          type: 'slider',
          show: true,
          bottom: 5,
          height: 24,
          borderColor: '#cbd5e1',
          fillerColor: 'rgba(37, 99, 235, 0.15)',
          handleStyle: { color: '#2563eb' },
          textStyle: { color: '#64748b' },
        },
        {
          type: 'inside',
        },
      ],
      series: chartSeries,
    };
  }, [
    series,
    corridorLowerData,
    corridorWidthData,
    climMeanData,
    filledData,
    smoothData,
    obsData,
    controlPointsData,
    compSmoothData,
    comparisonSeries,
    showControlPoints,
    showWeather,
    precipData,
    tempData,
    markAreaData,
  ]);

  // Клик по элементам графика: подсветка аномалии открывает её карточку
  const onChartClick = (params: any) => {
    if (params.componentType === 'markArea' && onAnomalyClick) {
      const match = anomalies.find(
        (a) => a.start === params.data?.coord?.[0]?.[0] || a.cause === params.data?.name
      );
      if (match) {
        onAnomalyClick(match);
      }
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 space-y-3">
      {/* Quick year chips & toggles header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-slate-500 mr-1">Сезон:</span>
          <button
            type="button"
            onClick={() => handleYearSelect(null)}
            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
              selectedYear === null
                ? 'bg-brand-600 text-white shadow-sm'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            Все ({series.years[0]}–{series.years[series.years.length - 1]})
          </button>
          {series.years.map((y) => (
            <button
              key={y}
              type="button"
              onClick={() => handleYearSelect(y)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                selectedYear === y
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {y}
            </button>
          ))}
        </div>

        {/* Toggles */}
        <div className="flex items-center gap-3 text-xs">
          {series.isControlPoint && series.isControlPoint.some(Boolean) && (
            <label className="flex items-center gap-1.5 cursor-pointer text-slate-600 select-none">
              <input
                type="checkbox"
                checked={showControlPoints}
                onChange={(e) => setShowControlPoints(e.target.checked)}
                className="rounded text-brand-600 focus:ring-brand-500"
              />
              <span>Контрольные точки</span>
            </label>
          )}

          <label className="flex items-center gap-1.5 cursor-pointer text-slate-600 select-none">
            <input
              type="checkbox"
              checked={showWeather}
              onChange={(e) => setShowWeather(e.target.checked)}
              className="rounded text-brand-600 focus:ring-brand-500"
            />
            <span>Погода (осадки / темп.)</span>
          </label>
        </div>
      </div>

      {/* Warning if climate norm not built (< 3 seasons) */}
      {!series.hasClimateNorm && (
        <div className="bg-amber-50 border-l-4 border-amber-400 p-3 rounded text-xs text-amber-800">
          <b>Климатнорма не построена:</b> в ряду меньше трёх сезонов (leave-one-year-out требует минимум 3 года). Ряд NDVI восстановлен, но коридор нормы и z-score отсутствуют.
        </div>
      )}

      {/* Chart container */}
      <div className="w-full h-[450px]">
        <ReactECharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
          onEvents={{
            click: onChartClick,
          }}
          opts={{ renderer: 'canvas' }}
        />
      </div>

      {/* Footnote */}
      <div className="text-[11px] text-slate-400 flex flex-wrap justify-between items-center px-1">
        <div>Ось Y зафиксирована на [−0.2, 1.0] для корректной сравнимости полей. Зимний период не соединяется линией.</div>
        <div className="italic">Колесико мыши: зум / сдвиг</div>
      </div>
    </div>
  );
};
