import { ANALYSIS_SETUP_STEPS } from "../analysisConfig";

export default function AnalysisSetupProgress({
  currentStep,
  highestStep,
  locked = false,
  onStepChange,
}) {
  const current = ANALYSIS_SETUP_STEPS.find((step) => step.id === currentStep);

  return (
    <nav
      className="min-w-0"
      aria-label="新增分析步驟"
    >
      <div className="grid gap-2 min-[720px]:hidden">
        <div className="flex items-center justify-between gap-3 text-xs font-black">
          <span className="text-emerald-200">第 {currentStep} / {ANALYSIS_SETUP_STEPS.length} 步</span>
          <span className="text-neutral-200">{current?.label}</span>
        </div>
        <div
          className="h-1.5 overflow-hidden rounded-full bg-black/25"
          role="progressbar"
          aria-label="建立分析步驟"
          aria-valuemin={1}
          aria-valuemax={ANALYSIS_SETUP_STEPS.length}
          aria-valuenow={currentStep}
        >
          <div
            className="h-full rounded-full bg-emerald-300 transition-[width] duration-200 motion-reduce:transition-none"
            style={{ width: `${currentStep / ANALYSIS_SETUP_STEPS.length * 100}%` }}
          />
        </div>
      </div>
      <ol className="hidden grid-cols-4 gap-2 min-[720px]:grid">
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
                      : "border-white/15 bg-black/15 text-neutral-500"
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
