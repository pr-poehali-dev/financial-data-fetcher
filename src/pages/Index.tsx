import { useState, useRef, useEffect, useCallback } from "react";
import Icon from "@/components/ui/icon";

// ─── API URLs ──────────────────────────────────────────────────────────────────

const API = {
  searchCompany: "https://functions.poehali.dev/5e410c54-9c7f-4d75-8358-2fa7f2241336",
  extractMetrics: "https://functions.poehali.dev/85428a9a-38cb-4114-ba2e-89091669ed2d",
};

// ─── Types ─────────────────────────────────────────────────────────────────────

type Step = "search" | "metrics" | "results" | "history" | "help";

interface Company {
  id: string;
  name: string;
  inn: string;
  ticker?: string;
  url: string;
  source?: string;
}

interface Document {
  name: string;
  type: string;
  url: string;
  source: string;
  size: string;
}

interface SearchResult {
  company: string;
  companyId: string;
  companyUrl: string;
  inn: string;
  period: string;
  year: string;
  documents: Document[];
}

interface MetricRow {
  name: string;
  value: string;
  unit: string;
  period: string;
  source: string;
  found: boolean;
  context?: string;
}

interface HistoryEntry {
  company: string;
  period: string;
  docs: number;
  date: string;
  metrics: number;
  result: SearchResult;
  rows: MetricRow[];
}

// ─── Constants ─────────────────────────────────────────────────────────────────

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: CURRENT_YEAR - 1990 + 1 }, (_, i) => String(CURRENT_YEAR - i));
const PERIODS = ["Годовой отчёт", "1 квартал", "6 месяцев (1П)", "9 месяцев (3К)"];

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

// ─── NavItem ───────────────────────────────────────────────────────────────────

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

// ─── Search Section ────────────────────────────────────────────────────────────

function SearchSection({ onFound }: { onFound: (r: SearchResult) => void }) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Company[]>([]);
  const [selected, setSelected] = useState<Company | null>(null);
  const [year, setYear] = useState("2023");
  const [period, setPeriod] = useState("Годовой отчёт");
  const [loadingSuggest, setLoadingSuggest] = useState(false);
  const [searching, setSearching] = useState(false);
  const [docs, setDocs] = useState<Document[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [error, setError] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced autocomplete
  const handleQuery = (v: string) => {
    setQuery(v);
    setSelected(null);
    setDocs([]);
    setError("");
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (v.length < 2) { setSuggestions([]); setShowDropdown(false); return; }
    debounceRef.current = setTimeout(async () => {
      setLoadingSuggest(true);
      try {
        const res = await fetch(`${API.searchCompany}?query=${encodeURIComponent(v)}&year=${year}`);
        const data = await res.json();
        const list: Company[] = data.companies || [];
        setSuggestions(list);
        setShowDropdown(list.length > 0);
      } catch {
        setSuggestions([]);
      } finally {
        setLoadingSuggest(false);
      }
    }, 400);
  };

  const selectCompany = (c: Company) => {
    setSelected(c);
    setQuery(c.name);
    setShowDropdown(false);
  };

  const handleSearch = async () => {
    if (!selected && !query.trim()) return;
    setSearching(true);
    setError("");
    setDocs([]);
    try {
      const q = selected ? selected.name : query.trim();
      const res = await fetch(`${API.searchCompany}?query=${encodeURIComponent(q)}&year=${year}&period=${encodeURIComponent(period)}`);
      const data = await res.json();

      const foundDocs: Document[] = data.documents || [];
      const companies: Company[] = data.companies || [];
      const top: Company = data.selected || companies[0] || selected || { id: "", name: q, inn: "", url: "" };

      setDocs(foundDocs);
      if (!selected && companies[0]) setSelected(companies[0]);

      onFound({
        company: top.name,
        companyId: top.id,
        companyUrl: top.url,
        inn: top.inn,
        period,
        year,
        documents: foundDocs,
      });

      if (foundDocs.length === 0) {
        setError("Документы за выбранный период не найдены. Попробуйте другой год или период.");
      }
    } catch (e) {
      setError("Ошибка соединения с сервером. Проверьте интернет и попробуйте снова.");
    } finally {
      setSearching(false);
    }
  };

  // Закрыть дропдаун при клике вне
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!(e.target as Element).closest(".search-dropdown-wrap")) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-1">Поиск компании</h2>
        <p className="text-sm text-dim">Введите название, ИНН или тикер. Источники: e-disclosure.ru и сайт компании</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-1">
          <label className="text-xs text-dim font-medium uppercase tracking-wider">Компания</label>
          <div className="relative search-dropdown-wrap">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-dim pointer-events-none">
              {loadingSuggest
                ? <Icon name="Loader2" size={15} className="animate-spin" />
                : <Icon name="Search" size={15} />}
            </div>
            <input
              type="text"
              value={query}
              onChange={e => handleQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="Газпром, Лукойл, SBER, 7707083893..."
              className="w-full bg-surface-2 border border-surface-3 rounded text-sm pl-9 pr-3 py-2.5 text-foreground placeholder:text-dim focus:outline-none focus:border-gold transition-colors"
            />
            {showDropdown && suggestions.length > 0 && (
              <div className="absolute top-full mt-1 w-full bg-surface-1 border border-surface-3 rounded z-50 overflow-hidden shadow-2xl">
                {suggestions.map((c, i) => (
                  <button key={c.id || i} onClick={() => selectCompany(c)}
                    className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-surface-2 text-left transition-colors gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-foreground truncate">{c.name}</div>
                      {c.inn && <div className="text-xs text-dim">ИНН {c.inn}</div>}
                    </div>
                    {c.ticker && (
                      <span className="font-mono text-xs text-gold bg-gold/10 px-1.5 py-0.5 rounded shrink-0">{c.ticker}</span>
                    )}
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
        <button onClick={handleSearch} disabled={(!selected && !query.trim()) || searching}
          className="flex items-center gap-2 px-5 py-2.5 bg-gold text-background font-semibold text-sm rounded hover:bg-gold/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
          {searching
            ? <><Icon name="Loader2" size={15} className="animate-spin" />Поиск документов...</>
            : <><Icon name="FileSearch" size={15} />Найти отчётность</>}
        </button>
        {!searching && docs.length > 0 && (
          <span className="text-xs font-mono px-2 py-0.5 rounded text-emerald-400 bg-emerald-400/10">
            Найдено {docs.length}
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-3 bg-rose-400/5 border border-rose-400/20 rounded px-4 py-3">
          <Icon name="AlertCircle" size={15} className="text-rose-400 mt-0.5 shrink-0" />
          <p className="text-sm text-rose-300">{error}</p>
        </div>
      )}

      {docs.length > 0 && (
        <div className="animate-fade-in space-y-3">
          <div className="flex items-center gap-2">
            <div className="gold-line flex-1" />
            <span className="text-xs text-dim uppercase tracking-wider px-2">Найденные документы</span>
            <div className="gold-line flex-1" />
          </div>
          <div className="space-y-2">
            {docs.map((doc, i) => (
              <a key={i} href={doc.url} target="_blank" rel="noopener noreferrer"
                className={`flex items-center justify-between rounded px-4 py-3 border transition-colors hover:border-gold/60 group ${
                  doc.type === "LINK"
                    ? "bg-gold/5 border-gold/20"
                    : "bg-surface-2 border-surface-3"
                }`}>
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`font-mono text-xs px-1.5 py-0.5 rounded shrink-0 ${
                    doc.type === "PDF"  ? "text-rose-400 bg-rose-400/10"
                    : doc.type === "ZIP" || doc.type === "RAR" ? "text-amber-400 bg-amber-400/10"
                    : doc.type === "LINK" ? "text-gold bg-gold/10"
                    : "text-emerald-400 bg-emerald-400/10"
                  }`}>{doc.type === "LINK" ? "САЙТ" : doc.type}</span>
                  <div className="min-w-0">
                    <div className="text-sm text-foreground truncate">{doc.name}</div>
                    {(doc as Document & { description?: string }).description && (
                      <div className="text-xs text-dim">{(doc as Document & { description?: string }).description}</div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-2">
                  {doc.size && <span className="text-xs text-dim hidden sm:block">{doc.size}</span>}
                  <span className="text-gold group-hover:text-gold/70 transition-colors">
                    <Icon name="ExternalLink" size={14} />
                  </span>
                </div>
              </a>
            ))}
          </div>
          <p className="text-xs text-dim">Источник: Московская биржа + e-disclosure.ru · Нажмите для открытия</p>
        </div>
      )}

      {!searching && docs.length === 0 && !error && (
        <div className="bg-surface-2 border border-surface-3 rounded px-4 py-4 space-y-2">
          <p className="text-xs text-dim font-medium uppercase tracking-wider">Популярные компании</p>
          <div className="flex flex-wrap gap-2">
            {["Газпром", "Лукойл", "Сбербанк", "Роснефть", "Норникель", "МТС", "Новатэк"].map(name => (
              <button key={name} onClick={() => { setQuery(name); handleQuery(name); }}
                className="text-xs px-2.5 py-1 bg-surface-3 text-dim hover:text-foreground rounded transition-colors">
                {name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Metrics Section ───────────────────────────────────────────────────────────

function MetricsSection({ result, onExtract }: {
  result: SearchResult | null;
  onExtract: (rows: MetricRow[], docUrl: string) => void;
}) {
  const [metricsList, setMetricsList] = useState(DEFAULT_METRICS_LIST);
  const [selectedDocUrl, setSelectedDocUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const lineCount = metricsList.split("\n").filter(l => l.trim()).length;

  useEffect(() => {
    if (result?.documents?.length) {
      // По умолчанию выбираем первый PDF или XLSX
      const preferred = result.documents.find(d => d.type === "PDF" || d.type === "XLSX") || result.documents[0];
      setSelectedDocUrl(preferred?.url || "");
    }
  }, [result]);

  const handleExtract = async () => {
    if (!selectedDocUrl) { setError("Выберите документ для извлечения данных"); return; }
    const metrics = metricsList.split("\n").map(l => l.trim()).filter(Boolean).slice(0, 20);
    if (!metrics.length) return;

    setLoading(true);
    setError("");
    setProgress("Загружаю документ...");

    try {
      setProgress("Парсинг документа...");
      const res = await fetch(API.extractMetrics, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: selectedDocUrl,
          metrics,
          company: result?.company || "",
          year: result?.year || "",
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Ошибка при извлечении данных");
        return;
      }

      if (data.warning) {
        setError(data.warning);
      }

      const rows: MetricRow[] = (data.metrics || []).map((m: MetricRow) => ({
        name: m.name,
        value: m.value || "—",
        unit: m.unit || "",
        period: result?.year || "",
        source: m.found ? "Документ" : "Не найдено",
        found: m.found,
        context: m.context,
      }));

      onExtract(rows, selectedDocUrl);
    } catch {
      setError("Ошибка соединения. Проверьте интернет и попробуйте снова.");
    } finally {
      setLoading(false);
      setProgress("");
    }
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
          <div className="text-xs text-dim uppercase tracking-wider mb-0.5">Документов</div>
          <div className="text-sm font-medium">{result.documents.length}</div>
        </div>
      </div>

      {result.documents.length > 0 && (
        <div className="space-y-2">
          <label className="text-xs text-dim font-medium uppercase tracking-wider">Документ для извлечения</label>
          <div className="space-y-2">
            {result.documents.map((doc, i) => (
              <label key={i}
                className={`flex items-center gap-3 px-3 py-2.5 rounded border cursor-pointer transition-all ${
                  selectedDocUrl === doc.url
                    ? "border-gold bg-gold/5"
                    : "border-surface-3 hover:border-muted-foreground"
                }`}>
                <input type="radio" name="doc" value={doc.url} checked={selectedDocUrl === doc.url}
                  onChange={() => setSelectedDocUrl(doc.url)} className="accent-gold" />
                <span className={`font-mono text-xs px-1.5 py-0.5 rounded shrink-0 ${
                  doc.type === "PDF" ? "text-rose-400 bg-rose-400/10"
                  : doc.type === "ZIP" ? "text-amber-400 bg-amber-400/10"
                  : "text-emerald-400 bg-emerald-400/10"
                }`}>{doc.type}</span>
                <span className="text-sm truncate">{doc.name}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs text-dim font-medium uppercase tracking-wider">Показатели</label>
          <span className={`font-mono text-xs ${lineCount > 20 ? "text-rose-400" : "text-dim"}`}>{lineCount}/20</span>
        </div>
        <textarea
          value={metricsList}
          onChange={e => setMetricsList(e.target.value)}
          rows={12}
          placeholder={"Выручка\nEBITDA\nЧистая прибыль\n..."}
          className="w-full bg-surface-2 border border-surface-3 rounded text-sm px-4 py-3 text-foreground placeholder:text-dim focus:outline-none focus:border-gold transition-colors resize-none font-mono leading-relaxed"
        />
        <p className="text-xs text-dim">Поддерживаются финансовые и нефинансовые показатели, включая ESG-метрики</p>
      </div>

      {error && (
        <div className="flex items-start gap-3 bg-amber-400/5 border border-amber-400/20 rounded px-4 py-3">
          <Icon name="AlertTriangle" size={15} className="text-amber-400 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-300">{error}</p>
        </div>
      )}

      <button onClick={handleExtract} disabled={lineCount === 0 || lineCount > 20 || loading}
        className="flex items-center gap-2 px-5 py-2.5 bg-gold text-background font-semibold text-sm rounded hover:bg-gold/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
        {loading
          ? <><Icon name="Loader2" size={15} className="animate-spin" />{progress || "Извлекаю данные..."}</>
          : <><Icon name="Zap" size={15} />Извлечь показатели</>}
      </button>
    </div>
  );
}

// ─── Results Section ───────────────────────────────────────────────────────────

function ResultsSection({ result, rows }: { result: SearchResult | null; rows: MetricRow[] }) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    const header = ["Показатель", "Значение", "Единица", "Период", "Источник"].join("\t");
    const data = rows.map(r => [r.name, r.value, r.unit, r.period, r.source].join("\t"));
    navigator.clipboard.writeText([header, ...data].join("\n")).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!result || !rows.length) {
    return (
      <div className="animate-fade-in flex flex-col items-center justify-center h-64 text-center">
        <Icon name="Table2" size={36} className="text-dim mb-3" />
        <p className="text-dim text-sm">Данные появятся после извлечения показателей</p>
      </div>
    );
  }

  const foundCount = rows.filter(r => r.found).length;

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

      <div className="flex items-center gap-3 text-xs text-dim">
        <span className="text-emerald-400">{foundCount} найдено</span>
        <span>·</span>
        <span>{rows.length - foundCount} не найдено</span>
        {rows.length - foundCount > 0 && (
          <span className="text-dim">— возможно, показатели названы иначе в документе</span>
        )}
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
              {rows.map((row, i) => (
                <tr key={i}
                  className={`border-b border-surface-3 last:border-0 transition-colors hover:bg-surface-2 ${
                    i % 2 === 0 ? "bg-transparent" : "bg-surface-1/50"
                  }`}>
                  <td className="px-4 py-2.5 font-medium text-foreground">{row.name}</td>
                  <td className={`px-4 py-2.5 text-right font-mono ${row.found ? "text-gold" : "text-dim"}`}>
                    {row.value}
                  </td>
                  <td className="px-4 py-2.5 text-dim">{row.unit}</td>
                  <td className="px-4 py-2.5 text-dim font-mono">{row.period}</td>
                  <td className="px-4 py-2.5 text-xs">
                    <span className={row.found ? "text-emerald-400" : "text-dim"}>{row.source}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={copyToClipboard}
          className="flex items-center gap-2 px-4 py-2 text-sm border border-surface-3 text-dim rounded hover:border-gold hover:text-gold transition-all">
          <Icon name="Download" size={14} />
          Копировать в Excel / Google Таблицы
        </button>
        {result.companyUrl && (
          <a href={result.companyUrl} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 text-sm border border-surface-3 text-dim rounded hover:border-gold hover:text-gold transition-all">
            <Icon name="ExternalLink" size={14} />
            Страница компании
          </a>
        )}
      </div>

      <div className="bg-gold/5 border border-gold/20 rounded px-4 py-3">
        <div className="flex items-start gap-2">
          <Icon name="Info" size={14} className="text-gold mt-0.5 shrink-0" />
          <p className="text-xs text-foreground/60">
            Данные извлечены автоматически из текста документа. Рекомендуем сверить значения с оригиналом.
            Если показатель не найден — попробуйте уточнить его название (например «Revenue» вместо «Выручка»).
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── History Section ───────────────────────────────────────────────────────────

function HistorySection({ history, onRestore }: {
  history: HistoryEntry[];
  onRestore: (e: HistoryEntry) => void;
}) {
  if (!history.length) {
    return (
      <div className="animate-fade-in space-y-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">История поисков</h2>
          <p className="text-sm text-dim">Ранее загруженные отчёты и извлечённые данные</p>
        </div>
        <div className="flex flex-col items-center justify-center h-48 text-center">
          <Icon name="Clock" size={36} className="text-dim mb-3" />
          <p className="text-dim text-sm">История пуста — выполните первый поиск</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-1">История поисков</h2>
        <p className="text-sm text-dim">Ранее загруженные отчёты и извлечённые данные</p>
      </div>
      <div className="space-y-2">
        {history.map((item, i) => (
          <button key={i} onClick={() => onRestore(item)}
            className="w-full flex items-center justify-between bg-surface-2 border border-surface-3 rounded px-4 py-3 hover:border-gold/40 transition-colors text-left">
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
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Help Section ──────────────────────────────────────────────────────────────

function HelpSection() {
  const sources = [
    { name: "e-disclosure.ru", desc: "Федеральный центр раскрытия корпоративной информации. МСФО, РСБУ, годовые отчёты, проспекты.", icon: "Globe" },
    { name: "Сайт компании", desc: "Раздел «Инвесторам» / «Акционерам». Databooks, Excel-приложения, презентации.", icon: "Building2" },
    { name: "Форматы файлов", desc: "PDF (годовые отчёты), XLSX/XLS (databooks, финмодели), ZIP/RAR (архивы).", icon: "FileArchive" },
  ];
  const steps = [
    "Введите название компании, ИНН или биржевой тикер",
    "Выберите год и отчётный период (годовой / квартальный)",
    "Нажмите «Найти отчётность» — сервис ищет документы на e-disclosure.ru",
    "Перейдите на вкладку «Показатели» и выберите нужный документ",
    "Введите список метрик (до 20) и нажмите «Извлечь показатели»",
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
            Сервис ищет документы на e-disclosure.ru и сайте компании. Поддерживаются финансовые (МСФО/РСБУ), нефинансовые и ESG-метрики. До 20 показателей за один запрос. Если показатель не найден — попробуйте альтернативное название (например на английском).
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export default function Index() {
  const [activeStep, setActiveStep] = useState<Step>("search");
  const [searchResult, setSearchResult] = useState<SearchResult | null>(null);
  const [metricRows, setMetricRows] = useState<MetricRow[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const handleFound = (r: SearchResult) => {
    setSearchResult(r);
  };

  const handleExtract = useCallback((rows: MetricRow[], docUrl: string) => {
    setMetricRows(rows);
    setActiveStep("results");
    if (searchResult) {
      const entry: HistoryEntry = {
        company: searchResult.company,
        period: `${searchResult.period} ${searchResult.year}`,
        docs: searchResult.documents.length,
        date: new Date().toLocaleDateString("ru-RU"),
        metrics: rows.length,
        result: searchResult,
        rows,
      };
      setHistory(prev => [entry, ...prev.filter(h => h.company !== entry.company || h.period !== entry.period)].slice(0, 20));
    }
  }, [searchResult]);

  const handleRestore = (entry: HistoryEntry) => {
    setSearchResult(entry.result);
    setMetricRows(entry.rows);
    setActiveStep("results");
  };

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
              <span className="text-xs text-foreground font-medium truncate max-w-48">{searchResult.company}</span>
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
            <div className={`flex items-center gap-2 text-xs ${metricRows.length ? "text-emerald-400" : "text-dim"}`}>
              <Icon name={metricRows.length ? "CheckCircle2" : "Circle"} size={12} />
              Данные извлечены
            </div>
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6 sm:p-8 pb-20 sm:pb-8">
          <div className="max-w-3xl">
            {activeStep === "search" && <SearchSection onFound={handleFound} />}
            {activeStep === "metrics" && <MetricsSection result={searchResult} onExtract={handleExtract} />}
            {activeStep === "results" && <ResultsSection result={searchResult} rows={metricRows} />}
            {activeStep === "history" && <HistorySection history={history} onRestore={handleRestore} />}
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