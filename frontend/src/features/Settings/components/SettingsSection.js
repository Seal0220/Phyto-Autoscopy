import SubsectionHeader from "@/components/headers/SubsectionHeader";

import SettingsField from "./SettingsField";
import { sectionMeta } from "../lib/settingsUtils";

export default function SettingsSection({
  group,
  section,
  leaves,
  onChange,
}) {
  const meta = sectionMeta(group, section);
  return (
    <section className="grid min-w-0 content-start gap-5">
      <SubsectionHeader
        title={meta.title}
        description={meta.description}
      />
      <div className={`grid gap-3 ${meta.fieldsClassName || ""}`}>
        {leaves.map((leaf) => (
          <SettingsField
            key={leaf.path.join(".")}
            group={group}
            leaf={leaf}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  );
}
