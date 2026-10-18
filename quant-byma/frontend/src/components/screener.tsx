"use client";

import { Plus, Play, Save, Trash2, X } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { RankingsTable } from "@/components/rankings-table";
import { ErrorState } from "@/components/state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  api,
  fetcher,
  type Condition,
  type FieldInfo,
  type FilterDefinition,
  type Op,
  type RankingsResponse,
  type SavedFilter,
} from "@/lib/api";

const OPS: Record<FieldInfo["type"], { op: Op; label: string }[]> = {
  num: [
    { op: "gte", label: "≥" },
    { op: "lte", label: "≤" },
    { op: "gt", label: ">" },
    { op: "lt", label: "<" },
    { op: "between", label: "entre" },
    { op: "eq", label: "=" },
  ],
  str: [
    { op: "eq", label: "es" },
    { op: "neq", label: "no es" },
    { op: "in", label: "uno de" },
  ],
  bool: [{ op: "eq", label: "es" }],
};

const PRESETS: { name: string; definition: FilterDefinition }[] = [
  {
    name: "Momentum sano + tendencia",
    definition: {
      conditions: [
        { field: "rsi14", op: "between", value: [40, 60] },
        { field: "above_sma200", op: "eq", value: true },
        { field: "technical_score", op: "gte", value: 60 },
      ],
      sort_by: "composite_score",
      sort_dir: "desc",
      limit: 50,
    },
  },
  {
    name: "CEDEARs con CCL barato",
    definition: {
      conditions: [
        { field: "kind", op: "eq", value: "CEDEAR" },
        { field: "ccl_dev_pct", op: "lte", value: -1.5 },
      ],
      sort_by: "ccl_dev_pct",
      sort_dir: "asc",
      limit: 50,
    },
  },
  {
    name: "Value de calidad",
    definition: {
      conditions: [
        { field: "pe", op: "between", value: [0, 15] },
        { field: "roe", op: "gte", value: 0.12 },
        { field: "fundamental_score", op: "gte", value: 55 },
      ],
      sort_by: "fundamental_score",
      sort_dir: "desc",
      limit: 50,
    },
  },
];

const EMPTY: FilterDefinition = { conditions: [], sort_by: "composite_score", sort_dir: "desc", limit: 100 };

function defaultCondition(f: FieldInfo): Condition {
  if (f.type === "bool") return { field: f.key, op: "eq", value: true };
  if (f.type === "str") return { field: f.key, op: "eq", value: "" };
  return { field: f.key, op: "gte", value: 0 };
}

export function Screener() {
  const fields = useSWR<FieldInfo[]>("/api/screener/fields", fetcher);
  const saved = useSWR<SavedFilter[]>("/api/filters", fetcher);
  const [def, setDef] = useState<FilterDefinition>(PRESETS[0].definition);
  const [name, setName] = useState("");
  const [result, setResult] = useState<RankingsResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);

  const fieldMap = new Map((fields.data ?? []).map((f) => [f.key, f]));

  function update(i: number, patch: Partial<Condition>) {
    setDef((d) => ({ ...d, conditions: d.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) }));
  }

  function changeField(i: number, key: string) {
    const f = fieldMap.get(key);
    if (f) update(i, defaultCondition(f));
  }

  function changeOp(i: number, op: Op) {
    const c = def.conditions[i];
    let value = c.value;
    if (op === "between" && !Array.isArray(value)) value = [Number(value) || 0, 100];
    if (op === "in" && !Array.isArray(value)) value = value === "" ? [] : [String(value)];
    if (op !== "between" && op !== "in" && Array.isArray(value)) value = value[0] ?? 0;
    update(i, { op, value });
  }

  async function run(d: FilterDefinition = def) {
    setRunning(true);
    setError(null);
    try {
      setResult(await api.runScreener(d));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }

  async function save() {
    if (!name.trim()) return;
    try {
      await api.saveFilter(name.trim(), def);
      setName("");
      await saved.mutate();
    } catch (e) {
      setError(e);
    }
  }

  async function remove(id: number) {
    await api.deleteFilter(id);
    await saved.mutate();
  }

  function load(d: FilterDefinition) {
    setDef(d);
    void run(d);
  }

  if (fields.error) return <ErrorState error={fields.error} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Screener cuantitativo</h1>
        <p className="text-sm text-muted-foreground">
          Combiná condiciones (AND) sobre indicadores técnicos, ratios fundamentales y CCL. Guardá tus filtros para
          reutilizarlos.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <Card>
          <CardHeader>
            <CardTitle>Condiciones</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {def.conditions.map((c, i) => {
              const f = fieldMap.get(c.field);
              const type = f?.type ?? "num";
              return (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <Select value={c.field} onChange={(e) => changeField(i, e.target.value)} className="w-56">
                    {(fields.data ?? []).map((fi) => (
                      <option key={fi.key} value={fi.key}>
                        {fi.label}
                      </option>
                    ))}
                  </Select>
                  <Select value={c.op} onChange={(e) => changeOp(i, e.target.value as Op)} className="w-24">
                    {OPS[type].map((o) => (
                      <option key={o.op} value={o.op}>
                        {o.label}
                      </option>
                    ))}
                  </Select>
                  <ValueInput condition={c} type={type} onChange={(value) => update(i, { value })} />
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Quitar condición"
                    onClick={() => setDef((d) => ({ ...d, conditions: d.conditions.filter((_, j) => j !== i) }))}
                  >
                    <X />
                  </Button>
                </div>
              );
            })}
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setDef((d) => ({ ...d, conditions: [...d.conditions, { field: "composite_score", op: "gte", value: 50 }] }))
                }
              >
                <Plus /> Condición
              </Button>
              <span className="ml-2 text-sm text-muted-foreground">Ordenar por</span>
              <Select value={def.sort_by} onChange={(e) => setDef({ ...def, sort_by: e.target.value })} className="w-52">
                {(fields.data ?? [])
                  .filter((f) => f.type === "num")
                  .map((f) => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
              </Select>
              <Select
                value={def.sort_dir}
                onChange={(e) => setDef({ ...def, sort_dir: e.target.value as "asc" | "desc" })}
                className="w-28"
              >
                <option value="desc">Desc.</option>
                <option value="asc">Asc.</option>
              </Select>
              <Button size="sm" onClick={() => run()} disabled={running} className="ml-auto">
                <Play /> {running ? "Ejecutando…" : "Ejecutar"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Filtros</CardTitle>
            <CardDescription>Predefinidos y guardados</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="space-y-1 text-sm">
              {PRESETS.map((p) => (
                <li key={p.name}>
                  <button type="button" className="text-left hover:text-primary" onClick={() => load(p.definition)}>
                    {p.name}
                  </button>
                </li>
              ))}
              {(saved.data ?? []).map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2">
                  <button type="button" className="truncate text-left font-medium hover:text-primary" onClick={() => load(s.definition)}>
                    {s.name}
                  </button>
                  <Button variant="ghost" size="icon" className="size-7" aria-label={`Borrar ${s.name}`} onClick={() => remove(s.id)}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
            <div className="flex gap-2 border-t pt-3">
              <Input placeholder="Nombre del filtro" value={name} onChange={(e) => setName(e.target.value)} />
              <Button size="icon" variant="secondary" onClick={save} disabled={!name.trim()} aria-label="Guardar filtro">
                <Save />
              </Button>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setDef(EMPTY)}>
              Limpiar condiciones
            </Button>
          </CardContent>
        </Card>
      </div>

      {error !== null && <ErrorState error={error} />}
      {result && (
        <Card>
          <CardHeader>
            <CardTitle>{result.count} resultados</CardTitle>
            <CardDescription>Snapshot del {result.as_of}</CardDescription>
          </CardHeader>
          <CardContent className="p-0 pb-2">
            <RankingsTable items={result.items} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ValueInput({
  condition,
  type,
  onChange,
}: {
  condition: Condition;
  type: FieldInfo["type"];
  onChange: (v: Condition["value"]) => void;
}) {
  const { op, value } = condition;
  if (type === "bool") {
    return (
      <Select value={String(value)} onChange={(e) => onChange(e.target.value === "true")} className="w-28">
        <option value="true">Sí</option>
        <option value="false">No</option>
      </Select>
    );
  }
  if (op === "between" && Array.isArray(value)) {
    return (
      <div className="flex items-center gap-1">
        <Input type="number" className="w-24" value={value[0]} onChange={(e) => onChange([Number(e.target.value), value[1]])} />
        <span className="text-muted-foreground">y</span>
        <Input type="number" className="w-24" value={value[1]} onChange={(e) => onChange([value[0], Number(e.target.value)])} />
      </div>
    );
  }
  if (op === "in") {
    return (
      <Input
        className="w-56"
        placeholder="AAPL, GGAL, …"
        value={Array.isArray(value) ? value.join(", ") : ""}
        onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
      />
    );
  }
  if (type === "str") {
    return <Input className="w-40" value={String(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  return <Input type="number" step="any" className="w-28" value={Number(value)} onChange={(e) => onChange(Number(e.target.value))} />;
}
