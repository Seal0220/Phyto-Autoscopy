import SubsectionHeader from "@/components/headers/SubsectionHeader";

import Field from "./Field";
import { sectionMeta } from "../lib/settingsUtils";

export default function Section({
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
      <div className="grid gap-3">
        {leaves.map((leaf) => (
          <Field
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
