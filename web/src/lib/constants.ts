import {
  Droplets,
  ThermometerSun,
  Flame,
  AlertTriangle,
  HelpCircle,
  LucideIcon,
  ShieldCheck,
  AlertOctagon,
} from 'lucide-react';

export interface CauseMeta {
  label: string;
  icon: LucideIcon;
  bgColor: string;
  textColor: string;
  borderColor: string;
}

export const CAUSE_MAP: Record<string, CauseMeta> = {
  'дефицит осадков': {
    label: 'Дефицит осадков',
    icon: Droplets,
    bgColor: 'bg-blue-50',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200',
  },
  'температурный стресс': {
    label: 'Температурный стресс',
    icon: ThermometerSun,
    bgColor: 'bg-amber-50',
    textColor: 'text-amber-700',
    borderColor: 'border-amber-200',
  },
  'засуха: осадки ниже нормы и жара': {
    label: 'Засуха: осадки ниже нормы и жара',
    icon: Flame,
    bgColor: 'bg-orange-50',
    textColor: 'text-orange-700',
    borderColor: 'border-orange-200',
  },
  'устойчивое угнетение без явного погодного сигнала': {
    label: 'Устойчивое угнетение (без погодного сигнала)',
    icon: AlertTriangle,
    bgColor: 'bg-purple-50',
    textColor: 'text-purple-700',
    borderColor: 'border-purple-200',
  },
  'краткое отклонение, погодой не объясняется (вероятно агрооперация или ошибка данных)': {
    label: 'Краткое отклонение (агрооперация / ошибка данных)',
    icon: HelpCircle,
    bgColor: 'bg-slate-100',
    textColor: 'text-slate-700',
    borderColor: 'border-slate-300',
  },
};

export const DEFAULT_CAUSE_META: CauseMeta = {
  label: 'Аномалия вегетации',
  icon: AlertTriangle,
  bgColor: 'bg-slate-100',
  textColor: 'text-slate-700',
  borderColor: 'border-slate-300',
};

export function getCauseMeta(cause: string): CauseMeta {
  return CAUSE_MAP[cause] ?? { ...DEFAULT_CAUSE_META, label: cause };
}

export interface SeverityMeta {
  label: string;
  icon: LucideIcon;
  badgeClass: string;
  chartColor: string;
}

export const SEVERITY_MAP: Record<string, SeverityMeta> = {
  'Критическая аномалия': {
    label: 'Критическая аномалия',
    icon: AlertOctagon,
    badgeClass: 'bg-red-100 text-red-800 border border-red-300',
    chartColor: 'rgba(239, 68, 68, 0.25)',
  },
  'Угнетение биомассы': {
    label: 'Угнетение биомассы',
    icon: AlertTriangle,
    badgeClass: 'bg-amber-100 text-amber-800 border border-amber-300',
    chartColor: 'rgba(245, 158, 11, 0.25)',
  },
  'Штатное развитие': {
    label: 'Штатное развитие',
    icon: ShieldCheck,
    badgeClass: 'bg-blue-50 text-blue-800 border border-blue-200',
    chartColor: 'rgba(37, 99, 235, 0.2)',
  },
  'нет данных': {
    label: 'Нет данных',
    icon: HelpCircle,
    badgeClass: 'bg-gray-100 text-gray-700 border border-gray-300',
    chartColor: 'rgba(156, 163, 175, 0.2)',
  },
};

export function getSeverityMeta(severity: string): SeverityMeta {
  return (
    SEVERITY_MAP[severity] ?? {
      label: severity,
      icon: AlertTriangle,
      badgeClass: 'bg-slate-100 text-slate-800 border border-slate-300',
      chartColor: 'rgba(148, 163, 184, 0.25)',
    }
  );
}
