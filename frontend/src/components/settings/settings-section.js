import SettingsField from "@/components/settings/settings-field";
import SubsectionHeader from "@/components/ui/subsection-header";
import { sectionMeta } from "@/lib/settings";

export default function SettingsSection({
  group,
  section,
  leaves,
  onChange,
}) {
  const meta = sectionMeta(group, section);
  return (
    <section className={`grid content-start gap-5 ${group === "cameras" ? "min-w-0 border-r border-white/10 pr-4 last:border-r-0" : "min-w-0"}`}>
      <SubsectionHeader
        title={meta.title}
        description={meta.description}
      />
      <div className="grid gap-3">
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
