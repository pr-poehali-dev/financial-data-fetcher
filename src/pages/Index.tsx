import { useState } from "react";
import Icon from "@/components/ui/icon";

// ─── Types ────────────────────────────────────────────────────────────────────

type Step = "search" | "metrics" | "results" | "history" | "help";

interface SearchResult {
  company: string;
  inn: string;
  period: string;
  year: string;
  source: string;
  docType: string;
}

interface MetricRow {
  name: string;
  value: string;
  unit: string;
  period: string;
  source: string;
}

// ─── Mock data ────────────────────────────────────────────────────────────────

const MOCK_COMPANIES = [
  { name: "ПАО Газпром", inn: "7736050003", ticker: "GAZP" },
  { name: "ПАО Лукойл", inn: "7708004767", ticker: "LKOH" },
  { name: "ПАО Сбербанк", inn: "7707083893", ticker: "SBER" },
  { name: "ПАО Норильский никель", inn: "8401005730", ticker: "GMKN" },
  { name: "ПАО Роснефть", inn: "7706107510", ticker: "ROSN" },
  { name: "ПАО МТС", inn: "7740000076", ticker: "MTSS" },
  { name: "ПАО Новатэк", inn: "8905000980", ticker: "NVTK" },
  { name: "ПАО Магнит", inn: "2309085638", ticker: "MGNT" },
];

const MOCK_METRICS: MetricRow[] = [
  { name: "Выручка", value: "8 541 964", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Операционная прибыль (EBIT)", value: "1 823 441", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "EBITDA", value: "2 341 872", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Чистая прибыль", value: "1 230 044", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Совокупные активы", value: "27 851 964", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Собственный капитал", value: "16 543 219", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Долгосрочный долг", value: "4 218 766", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Капитальные затраты (CAPEX)", value: "1 543 219", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Операционный денежный поток", value: "2 108 543", unit: "млн руб.", period: "2023", source: "МСФО Консолидированная" },
  { name: "Рентабельность по EBITDA", value: "27,4", unit: "%", period: "2023", source: "Расчётный" },
  { name: "Чистый долг / EBITDA", value: "1,8", unit: "x", period: "2023", source: "Расчётный" },
  { name: "Численность сотрудников", value: "476 300", unit: "чел.", period: "2023", source: "Годовой отчёт" },
];

const HISTORY = [
  { company: "ПАО Газпром", period: "2023 (годовой)", docs: 3, date: "28.05.2026", metrics: 12 },
  { company: "ПАО Лукойл", period: "2022 (годовой)", docs: 2, date: "20.05.2026", metrics: 8 },
  { company: "ПАО Сбербанк", period: "1П 2023", docs: 1, date: "12.05.2026", metrics: 15 },
];

const YEARS = ["2024", "2023", "2022", "2021", "2020", "2019"];
const PERIODS = ["Годовой отчёт", "1 квартал", "6 месяцев (1П)", "9 месяцев (3К)", "1П + 9 месяцев"];

const DEFAULT_METRICS_LIST = `Выручка
Операционная прибыль (EBIT)
EBITDA
Чистая прибыль
Совокупные активы
Собственный капитал
Долгосрочный долг
Капитальные затраты (CAPEX)
Операционный денежный поток
Рентабельность по EBITDA
Чистый долг / EBITDA
Численность сотрудников`;

// ─── Subcomponents ────────────────────────────────────────────────────────────

function NavItem({ id, label, icon, active, onClick }: {
  id: Step; label: string; icon: string; active: boolean; onClick: (s: Step) => void;
}) {
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex items-center gap-3 px-4 py-2.5 w-full text-left text-sm transition-all duration-150 ${
        active
          ? "text-gold border-l-2 border-gold bg-surface-2"
          : "text-dim border-l-2 border-transparent hover:text-foreground hover:bg-surface-2"
      }`}
    >
      <Icon name={icon} size={15} />
      <span className="font-medium">{label}</span>
    </button>
  );
}

// ─── Search Section ───────────────────────────────────────────────────────────

function SearchSection({ onFound }: { onFound: (r: SearchResult) => void }) {
  const [query, setQuery] = useState("");
  const [filtered, setFiltered] = useState(MOCK_COMPANIES);
  const [selected, setSelected] = useState<(typeof MOCK_COMPANIES)[0] | null>(null);
  const [year, setYear] = useState("2023");
  const [period, setPeriod] = useState("Годовой отчёт");
  const [searching, setSearching] = useState(false);
  const [found, setFound] = useState(false);
  const [docs, setDocs] = useState<{ name: string; type: string; size: string }[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);

  const handleQuery = (v: string) => {
    setQuery(v);
    setFound(false);
    setSelected(null);
    if (v.length > 0) {
      setFiltered(MOCK_COMPANIES.filter(c =>
        c.name.toLowerCase().includes(v.toLowerCase()) ||
        c.inn.includes(v) ||
        c.ticker.toLowerCase().includes(v.toLowerCase())
      ));
      setShowDropdown(true);
    } else {
      setShowDropdown(false);
    }
  };

  const selectCompany = (c: (typeof MOCK_COMPANIES)[0]) => {
    setSelected(c);
    setQuery(c.name);
    setShowDropdown(false);
  };

  const handleSearch = () => {
    if (!selected) return;
    setSearching(true);
    setTimeout(() => {
      setSearching(false);
      setFound(true);
      setDocs([
        { name: `${selected.ticker}_IFRS_${year}_Annual.pdf`, type: "PDF", size: "4.2 МБ" },
        { name: `${selected.ticker}_Databook_${year}.xlsx`, type: "XLSX", size: "1.8 МБ" },
        { name: `${selected.ticker}_Annual_Report_${year}.pdf`, type: "PDF", size: "12.1 МБ" },
      ]);
      onFound({ company: selected.name, inn: selected.inn, period, year, source: "e-disclosure.ru", docType: "МСФО + Годовой отчёт" });
    }, 1800);
  };

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-1">Поиск компании</h2>
        <p className="text-sm text-dim">Введите название, ИНН или тикер. Источники: e-disclosure.ru и сайт компании</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-1">
          <label className="text-xs text-dim font-medium uppercase tracking-wider">Компания</label>
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-dim pointer-events-none">
              <Icon name="Search" size={15} />
            </div>
            <input
              type="text"
              value={query}
              onChange={e => handleQuery(e.target.value)}
              placeholder="Газпром, Лукойл, SBER, 7707083893..."
              className="w-full bg-surface-2 border border-surface-3 rounded text-sm pl-9 pr-3 py-2.5 text-foreground placeholder:text-dim focus:outline-none focus:border-gold transition-colors"
            />
            {showDropdown && filtered.length > 0 && (
              <div className="absolute top-full mt-1 w-full bg-surface-1 border border-surface-3 rounded z-50 overflow-hidden shadow-2xl">
                {filtered.map(c => (
                  <button key={c.inn} onClick={() => selectCompany(c)}
                    className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-surface-2 text-left transition-colors">
                    <div>
                      <div className="text-sm font-medium text-foreground">{c.name}</div>
                      <div className="text-xs text-dim">ИНН {c.inn}</div>
                    </div>
                    <span className="font-mono text-xs text-gold">{c.ticker}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-dim font-medium uppercase tracking-wider">Год</label>
          <select value={year} onChange={e => setYear(e.target.value)}
            className="w-full bg-surface-2 border border-surface-3 rounded text-sm px-3 py-2.5 text-foreground focus:outline-none focus:border-gold transition-colors appearance-none cursor-pointer">
            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs text-dim font-medium uppercase tracking-wider">Отчётный период</label>
        <div className="flex flex-wrap gap-2">
          {PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`text-xs px-3 py-1.5 rounded border transition-all ${
                period === p ? "border-gold text-gold bg-gold/10" : "border-surface-3 text-dim hover:border-muted-foreground"
              }`}>
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button onClick={handleSearch} disabled={!selected || searching}
          className="flex items-center gap-2 px-5 py-2.5 bg-gold text-background font-semibold text-sm rounded hover:bg-gold/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
          {searching ? (
            <><Icon name="Loader2" size={15} className="animate-spin" />Поиск документов...</>
          ) : (
            <><Icon name="FileSearch" size={15} />Найти отчётность</>
          )}
        </button>
        {found && (
          <span className="text-xs font-mono px-2 py-0.5 rounded text-emerald-400 bg-emerald-400/10">Найдено</span>
        )}
      </div>

      {found && docs.length > 0 && (
        <div className="animate-fade-in space-y-3">
          <div className="flex items-center gap-2">
            <div className="gold-line flex-1" />
            <span className="text-xs text-dim uppercase tracking-wider px-2">Найденные документы</span>
            <div className="gold-line flex-1" />
          </div>
          <div className="space-y-2">
            {docs.map((doc, i) => (
              <div key={i} className="flex items-center justify-between bg-surface-2 border border-surface-3 rounded px-4 py-3 hover:border-gold/40 transition-colors">
                <div className="flex items-center gap-3">
                  <span className={`font-mono text-xs px-1.5 py-0.5 rounded ${
                    doc.type === "PDF" ? "text-rose-400 bg-rose-400/10" : "text-emerald-400 bg-emerald-400/10"
                  }`}>{doc.type}</span>
                  <span className="text-sm text-foreground">{doc.name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-dim">{doc.size}</span>
                  <a href="https://www.e-disclosure.ru/" target="_blank" rel="noopener noreferrer"
                    className="text-gold hover:text-gold/70 transition-colors">
                    <Icon name="ExternalLink" size={14} />
                  </a>
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-dim">Источник: e-disclosure.ru · Обновлено сегодня</p>
        </div>
      )}
    </div>
  );
}

// ─── Metrics Section ──────────────────────────────────────────────────────────

function MetricsSection({ result, onExtract }: { result: SearchResult | null; onExtract: () => void }) {
  const [metricsList, setMetricsList] = useState(DEFAULT_METRICS_LIST);
  const [loading, setLoading] = useState(false);
  const lineCount = metricsList.split("\n").filter(l => l.trim()).length;

  const handleExtract = () => {
    setLoading(true);
    setTimeout(() => { setLoading(false); onExtract(); }, 2000);
  };

  if (!result) {
    return (
      <div className="animate-fade-in flex flex-col items-center justify-center h-64 text-center">
        <Icon name="ArrowLeftCircle" size={36} className="text-dim mb-3" />
        <p className="text-dim text-sm">Сначала найдите компанию и период на вкладке «Поиск»</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-1">Список показателей</h2>
        <p className="text-sm text-dim">Введите до 20 показателей — каждый с новой строки</p>
      </div>

      <div className="bg-surface-2 border border-surface-3 rounded px-4 py-3 flex flex-wrap gap-4">
        <div>
          <div className="text-xs text-dim uppercase tracking-wider mb-0.5">Компания</div>
          <div className="text-sm font-semibold text-gold">{result.company}</div>
        </div>
        <div className="w-px bg-surface-3" />
        <div>
          <div className="text-xs text-dim uppercase tracking-wider mb-0.5">Период</div>
          <div className="text-sm font-medium">{result.period} {result.year}</div>
        </div>
        <div className="w-px bg-surface-3" />
        <div>
          <div className="text-xs text-dim uppercase tracking-wider mb-0.5">Документ</div>
          <div className="text-sm font-medium">{result.docType}</div>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs text-dim font-medium uppercase tracking-wider">Показатели</label>
          <span className={`font-mono text-xs ${lineCount > 20 ? "text-rose-400" : "text-dim"}`}>{lineCount}/20</span>
        </div>
        <textarea
          value={metricsList}
          onChange={e => setMetricsList(e.target.value)}
          rows={14}
          placeholder={"Выручка\nEBITDA\nЧистая прибыль\n..."}
          className="w-full bg-surface-2 border border-surface-3 rounded text-sm px-4 py-3 text-foreground placeholder:text-dim focus:outline-none focus:border-gold transition-colors resize-none font-mono leading-relaxed"
        />
        <p className="text-xs text-dim">Поддерживаются финансовые и нефинансовые показатели, включая ESG-метрики</p>
      </div>

      <button onClick={handleExtract} disabled={lineCount === 0 || lineCount > 20 || loading}
        className="flex items-center gap-2 px-5 py-2.5 bg-gold text-background font-semibold text-sm rounded hover:bg-gold/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
        {loading ? (
          <><Icon name="Loader2" size={15} className="animate-spin" />Извлекаю данные...</>
        ) : (
          <><Icon name="Zap" size={15} />Извлечь показатели</>
        )}
      </button>
    </div>
  );
}

// ─── Results Section ──────────────────────────────────────────────────────────

function ResultsSection({ result }: { result: SearchResult | null }) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    const header = ["Показатель", "Значение", "Единица", "Период", "Источник"].join("\t");
    const rows = MOCK_METRICS.map(r => [r.name, r.value, r.unit, r.period, r.source].join("\t"));
    const tsv = [header, ...rows].join("\n");
    navigator.clipboard.writeText(tsv).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!result) {
    return (
      <div className="animate-fade-in flex flex-col items-center justify-center h-64 text-center">
        <Icon name="Table2" size={36} className="text-dim mb-3" />
        <p className="text-dim text-sm">Данные появятся после извлечения показателей</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold mb-1">Результаты</h2>
          <p className="text-sm text-dim">{result.company} · {result.period} {result.year}</p>
        </div>
        <button onClick={copyToClipboard}
          className={`flex items-center gap-2 px-4 py-2 text-sm rounded border transition-all ${
            copied
              ? "border-emerald-500 text-emerald-400 bg-emerald-400/10"
              : "border-surface-3 text-dim hover:border-gold hover:text-gold"
          }`}>
          <Icon name={copied ? "Check" : "Copy"} size={14} />
          {copied ? "Скопировано!" : "Копировать для Excel"}
        </button>
      </div>

      <div className="rounded border border-surface-3 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2 border-b border-surface-3">
                <th className="text-left px-4 py-2.5 text-xs text-dim font-medium uppercase tracking-wider">Показатель</th>
                <th className="text-right px-4 py-2.5 text-xs text-dim font-medium uppercase tracking-wider">Значение</th>
                <th className="text-left px-4 py-2.5 text-xs text-dim font-medium uppercase tracking-wider">Ед. изм.</th>
                <th className="text-left px-4 py-2.5 text-xs text-dim font-medium uppercase tracking-wider">Период</th>
                <th className="text-left px-4 py-2.5 text-xs text-dim font-medium uppercase tracking-wider">Источник</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_METRICS.map((row, i) => (
                <tr key={i}
                  className={`border-b border-surface-3 last:border-0 transition-colors hover:bg-surface-2 ${
                    i % 2 === 0 ? "bg-transparent" : "bg-surface-1/50"
                  }`}>
                  <td className="px-4 py-2.5 font-medium text-foreground">{row.name}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-gold">{row.value}</td>
                  <td className="px-4 py-2.5 text-dim">{row.unit}</td>
                  <td className="px-4 py-2.5 text-dim font-mono">{row.period}</td>
                  <td className="px-4 py-2.5 text-dim text-xs">{row.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button className="flex items-center gap-2 px-4 py-2 text-sm border border-surface-3 text-dim rounded hover:border-gold hover:text-gold transition-all">
          <Icon name="Download" size={14} />
          Скачать .xlsx
        </button>
        <button className="flex items-center gap-2 px-4 py-2 text-sm border border-surface-3 text-dim rounded hover:border-gold hover:text-gold transition-all">
          <Icon name="FileText" size={14} />
          Скачать .csv
        </button>
        <p className="text-xs text-dim ml-auto">* Данные демонстрационные. Подключите парсер для реальных значений.</p>
      </div>
    </div>
  );
}

// ─── History Section ──────────────────────────────────────────────────────────

function HistorySection() {
  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-1">История поисков</h2>
        <p className="text-sm text-dim">Ранее загруженные отчёты и извлечённые данные</p>
      </div>
      <div className="space-y-2">
        {HISTORY.map((item, i) => (
          <div key={i} className="flex items-center justify-between bg-surface-2 border border-surface-3 rounded px-4 py-3 hover:border-gold/40 transition-colors cursor-pointer">
            <div className="flex items-center gap-4">
              <div className="w-8 h-8 rounded bg-gold/10 flex items-center justify-center shrink-0">
                <Icon name="Building2" size={16} className="text-gold" />
              </div>
              <div>
                <div className="text-sm font-semibold">{item.company}</div>
                <div className="text-xs text-dim">{item.period} · {item.docs} документа · {item.metrics} показателей</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-dim font-mono">{item.date}</span>
              <Icon name="ChevronRight" size={14} className="text-dim" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Help Section ─────────────────────────────────────────────────────────────

function HelpSection() {
  const sources = [
    { name: "e-disclosure.ru", desc: "Федеральный центр раскрытия корпоративной информации. МСФО, РСБУ, годовые отчёты, проспекты.", icon: "Globe" },
    { name: "Сайт компании", desc: "Раздел «Инвесторам» / «Акционерам». Databooks, Excel-приложения, презентации.", icon: "Building2" },
    { name: "Форматы файлов", desc: "PDF (годовые отчёты), XLSX/XLS (databooks), ZIP/RAR (архивы с таблицами).", icon: "FileArchive" },
  ];
  const steps = [
    "Введите название компании, ИНН или биржевой тикер",
    "Выберите год и отчётный период (годовой / квартальный)",
    "Нажмите «Найти отчётность» — сервис найдёт документы",
    "Перейдите на вкладку «Показатели» и введите список нужных метрик",
    "Нажмите «Извлечь показатели» — данные появятся в таблице",
    "Скопируйте таблицу в Excel или Google Таблицы одной кнопкой",
  ];

  return (
    <div className="animate-fade-in space-y-8">
      <div>
        <h2 className="text-xl font-semibold mb-1">Справка</h2>
        <p className="text-sm text-dim">Как пользоваться сервисом и откуда берутся данные</p>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-dim">Порядок работы</h3>
        <ol className="space-y-2">
          {steps.map((s, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="font-mono text-xs text-gold mt-0.5 w-5 shrink-0">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-sm text-foreground/80">{s}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-dim">Источники данных</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          {sources.map((src, i) => (
            <div key={i} className="bg-surface-2 border border-surface-3 rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <Icon name={src.icon} size={16} className="text-gold" />
                <span className="text-sm font-semibold">{src.name}</span>
              </div>
              <p className="text-xs text-dim leading-relaxed">{src.desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-gold/5 border border-gold/20 rounded p-4">
        <div className="flex items-start gap-3">
          <Icon name="Info" size={16} className="text-gold mt-0.5 shrink-0" />
          <p className="text-sm text-foreground/70 leading-relaxed">
            Сервис ищет документы на e-disclosure.ru и сайте компании. Поддерживаются финансовые (МСФО/РСБУ), нефинансовые и ESG-метрики. До 20 показателей за один запрос.
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function Index() {
  const [activeStep, setActiveStep] = useState<Step>("search");
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [hasResults, setHasResults] = useState(false);

  const handleFound = (r: SearchResult) => setSearchResult(r);
  const handleExtract = () => { setHasResults(true); setActiveStep("results"); };

  const nav: { id: Step; label: string; icon: string }[] = [
    { id: "search", label: "Поиск компании", icon: "Search" },
    { id: "metrics", label: "Показатели", icon: "ListChecks" },
    { id: "results", label: "Результаты", icon: "Table2" },
    { id: "history", label: "История", icon: "Clock" },
    { id: "help", label: "Справка", icon: "HelpCircle" },
  ];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-surface-3 bg-surface-1 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded bg-gold flex items-center justify-center shrink-0">
            <Icon name="BarChart3" size={15} className="text-background" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-display font-semibold text-foreground tracking-tight">ФинОтчёт</span>
            <span className="text-dim text-xs hidden sm:inline">/ Аналитика консолидированной отчётности</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {searchResult && (
            <div className="hidden sm:flex items-center gap-2 bg-surface-2 border border-surface-3 rounded px-3 py-1.5">
              <Icon name="Building2" size={12} className="text-gold" />
              <span className="text-xs text-foreground font-medium">{searchResult.company}</span>
              <span className="text-xs text-dim">· {searchResult.year}</span>
            </div>
          )}
          <a href="https://www.e-disclosure.ru/" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-dim hover:text-gold transition-colors">
            <Icon name="ExternalLink" size={12} />
            <span className="hidden sm:inline">e-disclosure.ru</span>
          </a>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-52 shrink-0 border-r border-surface-3 bg-surface-1 py-4 flex-col hidden sm:flex">
          <nav className="space-y-0.5 px-2">
            {nav.map(item => (
              <NavItem key={item.id} {...item} active={activeStep === item.id} onClick={setActiveStep} />
            ))}
          </nav>
          <div className="mt-auto px-4 py-4 border-t border-surface-3 space-y-2">
            <div className={`flex items-center gap-2 text-xs ${searchResult ? "text-emerald-400" : "text-dim"}`}>
              <Icon name={searchResult ? "CheckCircle2" : "Circle"} size={12} />
              Компания найдена
            </div>
            <div className={`flex items-center gap-2 text-xs ${hasResults ? "text-emerald-400" : "text-dim"}`}>
              <Icon name={hasResults ? "CheckCircle2" : "Circle"} size={12} />
              Данные извлечены
            </div>
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6 sm:p-8 pb-20 sm:pb-8">
          <div className="max-w-3xl">
            {activeStep === "search" && <SearchSection onFound={handleFound} />}
            {activeStep === "metrics" && <MetricsSection result={searchResult} onExtract={handleExtract} />}
            {activeStep === "results" && <ResultsSection result={hasResults ? searchResult : null} />}
            {activeStep === "history" && <HistorySection />}
            {activeStep === "help" && <HelpSection />}
          </div>
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="sm:hidden fixed bottom-0 left-0 right-0 bg-surface-1 border-t border-surface-3 flex z-20">
        {nav.map(item => (
          <button key={item.id} onClick={() => setActiveStep(item.id)}
            className={`flex-1 flex flex-col items-center gap-1 py-2 text-xs transition-colors ${
              activeStep === item.id ? "text-gold" : "text-dim"
            }`}>
            <Icon name={item.icon} size={16} />
            <span className="text-[10px] leading-none">{item.label.split(" ")[0]}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
