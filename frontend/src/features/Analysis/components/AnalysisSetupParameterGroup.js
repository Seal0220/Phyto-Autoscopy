import InnerPanel from "@/components/panels/InnerPanel";
import SubsectionHeader from "@/components/headers/SubsectionHeader";
import { NumericInput } from "@/components/inputs/Input";

export default function AnalysisSetupParameterGroup({
  title,
  description,
  fields,
  parameters,
  onChange,
  children,
}) {
  return (
    <InnerPanel>
      <SubsectionHeader
        title={title}
        description={description}
        titleMode={1}
      />
      <div className="grid gap-3 min-[520px]:grid-cols-2 min-[900px]:grid-cols-3">
        {fields.map((field) => (
          <NumericInput
            id={`analysis-parameter-${field.key}`}
            key={field.key}
            label={field.label}
            value={parameters[field.key]}
            onValueChange={(value) => onChange(
              field.key,
              value,
            )}
            min={field.min}
            max={field.max}
            step={field.step}
            suffix={field.suffix}
            description={field.description}
            disabled={field.enabledBy
              ? !parameters[field.enabledBy]
              : false
            }
            required={!field.optional && (
              !field.enabledBy || Boolean(parameters[field.enabledBy])
            )}
          />
        ))}
      </div>
      {children}
    </InnerPanel>
  );
}
