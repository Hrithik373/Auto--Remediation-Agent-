import { useEffect, useMemo, useState } from "react";
import type { ActionSpec, IncidentEntities, ScenarioRequest } from "@/api/types";
import { useAssistantInfo, useIncidentEntities, useScenario } from "@/api/assistant";
import { useIncidents } from "@/api/incidents";
import type { VerifierChoice } from "@/store/ui";
import Card from "@/features/shared/Card";
import VerdictCard from "@/features/triage/VerdictCard";
import ExplanationCard from "./ExplanationCard";
import EntitySelect, { type SelectOption } from "./EntitySelect";

const OTHER = "__other__";
const VARIANTS: { value: VerifierChoice; label: string }[] = [
  { value: "learned", label: "Learned" },
  { value: "envelope", label: "Envelope only" },
  { value: "combined", label: "Combined" },
  { value: "llm_judge", label: "LLM-judge" },
  { value: "none", label: "Ungated" },
];
/** Params that name the thing being acted on: their dropdown defaults to "same as target". */
const TARGET_PARAMS = ["service", "deployment", "pod_name", "node_name", "configmap"];
/** Common destructive action types that are NOT on the allow-list, to show the envelope blocking them. */
const KNOWN_OUT_OF_ENVELOPE = ["delete_namespace", "delete_pvc", "drain_node"];

const fieldClass =
  "w-full rounded border border-console-border bg-console-bg px-2.5 py-1.5 font-mono text-xs text-console-text focus:border-accent focus:outline-none";
const labelClass = "mb-1 block text-2xs uppercase tracking-wider text-console-text-muted";

function coerce(value: string, type: string): unknown {
  if (type === "integer" && /^-?\d+$/.test(value.trim())) return Number(value);
  if (type === "number" && value.trim() !== "" && !Number.isNaN(Number(value))) return Number(value);
  if (type === "boolean") return value === "true";
  return value;
}

const toOptions = (values: unknown[] | undefined): SelectOption[] =>
  (values ?? []).map((v) => ({ value: String(v) }));

/** The param that names the action's subject (pod_name for restart_pod, node_name for cordon_node...). */
function targetParam(spec: ActionSpec | undefined): string | undefined {
  const names = Object.keys(spec?.params ?? {});
  return names.find((n) => TARGET_PARAMS.includes(n));
}

function targetOptions(spec: ActionSpec | undefined, entities: IncidentEntities | undefined): SelectOption[] {
  const param = targetParam(spec);
  const specific = param ? toOptions(entities?.params?.[param]) : [];
  if (specific.length === 0) return toOptions(entities?.targets);
  // Same relevance order as `targets` (alert targets first), not alphabetical.
  const rank = (v: string) => {
    const i = entities?.targets?.indexOf(v) ?? -1;
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  return [...specific].sort((a, b) => rank(a.value) - rank(b.value));
}

function paramOptions(name: string, required: boolean, type: string, entities: IncidentEntities | undefined): SelectOption[] {
  let values = toOptions(entities?.params?.[name]);
  if (values.length === 0 && type === "boolean") values = [{ value: "false" }, { value: "true" }];
  if (TARGET_PARAMS.includes(name)) return [{ value: "", label: "(same as target)" }, ...values];
  return required ? values : [{ value: "", label: "(not set)" }, ...values];
}

/** "What would the verifier say if the agent proposed THIS?" -- runs the real policy, verify only.
 * Every field is a dropdown of the selected incident's entities, with "custom…" for anything else. */
export default function ScenarioPanel() {
  const info = useAssistantInfo();
  const incidents = useIncidents();
  const scenario = useScenario();

  const [incidentId, setIncidentId] = useState("");
  const [actionType, setActionType] = useState("restart_pod");
  const [otherType, setOtherType] = useState("drain_node");
  const [target, setTarget] = useState("");
  const [params, setParams] = useState<Record<string, string>>({});
  const [variant, setVariant] = useState<VerifierChoice>("learned");
  const [tau, setTau] = useState(0.5);
  const entities = useIncidentEntities(incidentId);

  useEffect(() => {
    if (!incidentId && incidents.data?.length) setIncidentId(incidents.data[0].incident_id);
  }, [incidents.data, incidentId]);
  useEffect(() => {
    if (info.data?.default_variant) setVariant(info.data.default_variant);
  }, [info.data?.default_variant]);

  const spec: ActionSpec | undefined = useMemo(
    () => info.data?.actions?.find((a) => a.action_type === actionType),
    [info.data, actionType],
  );
  const paramSpecs = Object.entries(spec?.params ?? {});
  const targets = useMemo(() => targetOptions(spec, entities.data), [spec, entities.data]);
  const otherTypes = useMemo(
    () => toOptions([...new Set([...(entities.data?.other_action_types ?? []), ...KNOWN_OUT_OF_ENVELOPE])].sort()),
    [entities.data],
  );

  // New incident or action type: pick the first matching entity as the target and sensible param defaults.
  useEffect(() => {
    if (!entities.data) return;
    setTarget(targets[0]?.value ?? "");
    const defaults: Record<string, string> = {};
    for (const [name, p] of Object.entries(spec?.params ?? {})) {
      const options = paramOptions(name, Boolean(p.required), p.type ?? "string", entities.data);
      defaults[name] = TARGET_PARAMS.includes(name) ? "" : (options[0]?.value ?? "");
    }
    setParams(defaults);
  }, [entities.data, spec, targets]);

  const submit = () => {
    const built: Record<string, unknown> = {};
    for (const [name, p] of paramSpecs) {
      const raw = params[name] || (TARGET_PARAMS.includes(name) ? target : "");
      if (raw !== "") built[name] = coerce(raw, p.type ?? "string");
    }
    const body: ScenarioRequest = {
      incident_id: incidentId,
      action_type: actionType === OTHER ? otherType.trim() : actionType,
      target: target.trim(),
      params: built,
      variant,
      tau,
      compare_variants: true,
    };
    scenario.mutate(body);
  };

  const result = scenario.data;
  const canSubmit = incidentId && target.trim() && (actionType !== OTHER || otherType.trim());

  return (
    <div className="space-y-4">
      <Card title="Try a scenario">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) submit();
          }}
        >
          <div>
            <label htmlFor="sc-incident" className={labelClass}>
              Incident
            </label>
            <EntitySelect
              id="sc-incident"
              value={incidentId}
              onChange={setIncidentId}
              options={(incidents.data ?? []).map((i) => ({ value: i.incident_id }))}
              allowCustom={false}
              className={fieldClass}
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="min-w-0">
              <label htmlFor="sc-action" className={labelClass}>
                Action type
              </label>
              <EntitySelect
                id="sc-action"
                value={actionType}
                onChange={setActionType}
                options={[
                  ...(info.data?.actions ?? []).map((a) => ({ value: a.action_type })),
                  { value: OTHER, label: "not allow-listed…" },
                ]}
                allowCustom={false}
                className={fieldClass}
              />
            </div>
            <div className="min-w-0">
              <label htmlFor="sc-target" className={labelClass}>
                Target
              </label>
              <EntitySelect
                key={`target:${incidentId}:${actionType}`}
                id="sc-target"
                value={target}
                onChange={setTarget}
                options={targets}
                customPlaceholder="e.g. checkout-service"
                className={fieldClass}
              />
            </div>
          </div>

          {actionType === OTHER && (
            <div>
              <label htmlFor="sc-other" className={labelClass}>
                Not allow-listed action type
              </label>
              <EntitySelect
                id="sc-other"
                value={otherType}
                onChange={setOtherType}
                options={otherTypes}
                customPlaceholder="e.g. delete_deployment"
                className={fieldClass}
              />
            </div>
          )}

          {paramSpecs.length > 0 && (
            <fieldset className="space-y-2 rounded border border-console-border p-2.5">
              <legend className="px-1 text-2xs uppercase tracking-wider text-console-text-muted">
                Params {spec?.blast_radius && <span className="normal-case">· blast radius {spec.blast_radius}</span>}
              </legend>
              {paramSpecs.map(([name, p]) => (
                <div key={name} className="grid grid-cols-[8rem_minmax(0,1fr)] items-start gap-2">
                  <label htmlFor={`sc-param-${name}`} className="truncate pt-1.5 font-mono text-2xs text-console-text-muted">
                    {name}
                    {p.required ? "" : "?"}
                  </label>
                  <EntitySelect
                    key={`${incidentId}:${actionType}:${name}`}
                    id={`sc-param-${name}`}
                    value={params[name] ?? ""}
                    onChange={(v) => setParams((prev) => ({ ...prev, [name]: v }))}
                    options={paramOptions(name, Boolean(p.required), p.type ?? "string", entities.data)}
                    customPlaceholder={p.type ?? "string"}
                    className={fieldClass}
                  />
                </div>
              ))}
            </fieldset>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div className="min-w-0">
              <label htmlFor="sc-variant" className={labelClass}>
                Verifier
              </label>
              <EntitySelect
                id="sc-variant"
                value={variant}
                onChange={(v) => setVariant(v as VerifierChoice)}
                options={VARIANTS}
                allowCustom={false}
                className={fieldClass}
              />
            </div>
            <div className="min-w-0">
              <label htmlFor="sc-tau" className={labelClass}>
                τ = <span className="font-mono text-console-text">{tau.toFixed(2)}</span>
              </label>
              <input
                id="sc-tau"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={tau}
                onChange={(e) => setTau(Number(e.target.value))}
                className="w-full accent-accent"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!canSubmit || scenario.isPending}
            className="w-full rounded bg-accent px-4 py-2 text-sm font-semibold text-console-bg transition-opacity disabled:opacity-40"
          >
            {scenario.isPending ? "Asking the verifier…" : "Judge this action"}
          </button>
          <p className="text-2xs text-console-text-muted">
            Choices come from this incident&apos;s telemetry and candidate actions. Verify only: nothing is executed.
          </p>
          {scenario.isError && (
            <p className="text-xs text-decision-block">
              {scenario.error instanceof Error ? scenario.error.message : "The scenario could not be evaluated."}
            </p>
          )}
        </form>
      </Card>

      {result && (
        <>
          <VerdictCard verdict={result.verdict} tau={result.scenario.tau ?? tau} />
          <ExplanationCard explanation={result.explanation} />
        </>
      )}
    </div>
  );
}
