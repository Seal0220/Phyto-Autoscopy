import { ANALYSIS_SETUP_STEPS } from "../analysisConfig";

export default function AnalysisSetupProgress({
  currentStep,
  highestStep,
  locked = false,
  onStepChange,
}) {
  return (
    <nav
      className="min-w-0 overflow-x-auto"
      aria-label="新增分析步驟"
    >
      <ol className="grid min-w-180 grid-cols-5 gap-2">
        {ANALYSIS_SETUP_STEPS.map((step) => {
          const current = step.id === currentStep;
          const reached = step.id <= highestStep;

          return (
            <li key={step.id}>
              <button
                type="button"
                className={`flex min-h-12 w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs font-black transition-[background-color,border-color,color,opacity] duration-150 focus-visible:outline-2 focus-visible:outline-emerald-300 disabled:cursor-not-allowed disabled:opacity-45 ${
                  current
                    ? "border-emerald-200/75 bg-emerald-500/20 text-emerald-100"
                    : reached
                      ? "cursor-pointer border-white/15 bg-white/[0.07] text-neutral-200 hover:border-emerald-200/45 hover:bg-white/[0.12]"
                      : "border-white/10 bg-black/10 text-neutral-500"
                }`}
                aria-current={current ? "step" : undefined}
                disabled={locked || !reached}
                onClick={() => onStepChange(step.id)}
              >
                <span
                  className={`grid size-6 shrink-0 place-items-center rounded-full border ${
                    current
                      ? "border-emerald-200/75 bg-emerald-400/20"
                      : "border-white/15 bg-black/15"
                  }`}
                  aria-hidden="true"
                >
                  {step.id}
                </span>
                <span>{step.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
