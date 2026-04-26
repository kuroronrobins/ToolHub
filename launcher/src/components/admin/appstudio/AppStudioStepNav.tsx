export type AppStudioImportStep = "selectEntry" | "aiProposal" | "review" | "register";

export const IMPORT_STEPS: Array<{ key: AppStudioImportStep; index: string; label: string }> = [
  { key: "selectEntry", index: "1", label: "アプリ選択" },
  { key: "aiProposal", index: "2", label: "AI提案" },
  { key: "review", index: "3", label: "内容確認" },
  { key: "register", index: "4", label: "登録・承認" },
];

interface Props {
  currentStep: AppStudioImportStep;
  onStepChange: (step: AppStudioImportStep) => void;
}

export function AppStudioStepNav({ currentStep, onStepChange }: Props) {
  return (
    <nav className="studio-step-nav" aria-label="アプリ登録ステップ">
      {IMPORT_STEPS.map((step) => (
        <button
          key={step.key}
          type="button"
          className={currentStep === step.key ? "active" : ""}
          aria-current={currentStep === step.key ? "step" : undefined}
          onClick={() => onStepChange(step.key)}
        >
          <span>{step.index}</span>
          {step.label}
        </button>
      ))}
    </nav>
  );
}

export function importStepLabel(step: AppStudioImportStep): string {
  return IMPORT_STEPS.find((item) => item.key === step)?.label ?? "未選択";
}
